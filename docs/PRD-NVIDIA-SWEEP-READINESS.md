# PRD: NVIDIA-Sweep Readiness — Cross-Cutting Fixes

**Status:** draft
**Created:** 2026-06-16
**Project:** Bench
**Scope:** bugfix + refactor
**Tier:** standard

> Source of truth for this work is the Second Brain project `bench`.
> SB tasks referenced by ID: `02117f37`, `b7414d96`, `0c44366f`, `3ce63043`,
> `532e0ee4`, `08f19328`, `01cfd589`. The already-shipped P0 fix is task
> `a69a58d4` (commit `12f5f5b`, branch `fix/max-samples-programmatic-eval`,
> not yet merged to `main`).

## Problem Statement

The 10-model nvidia-NIM eval sweep is blocked by more than the (now-fixed)
sample-concurrency P0. A batch of independent defects together make the sweep
either unreliable (kills, redo-tax, unparseable progress), untrustworthy
(mis-attributed cards, incoherent ratio columns), or both. This PRD scopes a
single coherent batch that makes the sweep reliable and its output trustworthy,
with **no deferrals within scope**. Items genuinely out of scope are listed
explicitly.

## Goals

1. A killed/failed run resumes without re-doing completed tasks.
2. Backgrounded runs emit plain-text, parseable progress.
3. Manual prices survive a cache refresh.
4. Model cards are attributed to the correct model and are stable across cache refreshes.
5. The three ratio pillars use one shared reference model and one shared resolution chain; `ratio=1.0` means one thing per column and is labeled.
6. Judge identity is documented accurately in the Second Brain.
7. The test suite is fully green on a clean checkout.

## Non-Goals (explicit deferrals, by decision)

- **Detached-run manager (`429f68c8`, LOW):** superseded by the plain-progress work (W1b). Out of scope.
- **Full storage rework (`de5c9235`, HIGH):** its own spec. Only the minimal piece it shares with resume (W1a) is folded in here.
- **The 10 model evals themselves + discriminative-layer exercise + judge calibration + baseline recording** are measurement/run tasks, not bug fixes.

## Verified Root Causes (Phase 1 of systematic-debugging, completed during brainstorming)

1. **Resume (`02117f37`):** no skip-if-done check exists; every run dispatches every discovered task unconditionally.
2. **Progress (`b7414d96`):** bench relies on Inspect's default `full` (textual/TUI) display. Inspect **already ships** `DisplayType = Literal["full","conversation","rich","plain","log","none"]` (`inspect_ai/util/_display.py:11`) and `PlainDisplay` (`inspect_ai/_display/plain/display.py`); `eval()` accepts `display=`. Not a custom build — wiring only.
3. **Pricing (`0c44366f`):** `OpenRouterCache.fetch_and_cache_prices()` rebuilds the `models` dict from scratch and overwrites the whole file. Manual entries share that dict, so they vanish.
4. **Card mis-attribution (`3ce63043`) — the keystone:** `_slug_from_alias` and `_real_model_name` (`bench_cli/results/core.py`) derive card filename/name from `resolve_openrouter_id(bench_alias)`, a **volatile** reverse-lookup. **Verified live 2026-06-16: `resolve_openrouter_id` returns `None` for all three nvidia nemotron aliases** (`nemotron-30b`, `nemotron-3-super-120b`, `nemotron-30b-a3b`) after the cache refresh. When resolution flips between runs (cache refresh, config drift), the same model slugs to different filenames, cards split/merge, and on a reverse-lookup collision two models can map to one slug — the mechanism behind the deleted glm-5.1 card that was byte-identical to minimax-m2.7.
5. **Nemotron anomalies (`01cfd589`):** same root as #4. `nvidia-nemotron-3-super-120b cost_ratio=0.000` and `nvidia-nemotron-3-nano-30b token_ratio=0.030` are downstream of resolution/price-cache state at the time of those runs. The models are **currently MISSING from the refreshed cache (337 models)** and resolve to `None`.
6. **Ratio incoherence (`08f19328`):** tokens+latency use a 3-tier chain `resolve_baseline_reference()` in `scorers/protocol.py` → BaselineStore (empty) → task_budget → SYSTEM_DEFAULT, all calibrated to **qwen-local**. Cost uses a 2-tier chain (`price_ratio_scorer`) with **no BaselineStore tier**, calibrated to **minimax-m2.7** (cost was transcribed into `task_budgets.py`; token/latency for m2.7 were never persisted — no m2.7 `.eval` logs exist on disk). Net: `bench baseline record` swaps token/latency references but silently ignores cost. Additionally, `compare/core.py` recomputes only **price** ratio at view time (`:328`, comment: "the ratio stored in eval logs uses stale references from the time of the run"); token+latency ratios are baked at scoring time, so a reference change does not re-cohere old logs.
7. **Judge drift (`532e0ee4`):** **code is correct** — exactly one reference, `DEFAULT_JUDGE_MODEL = "openai/judge"` (`scorers/llm_judge.py:23`); nothing hardcodes glm-5.1. Live LiteLLM routes `judge → openai/qwen3.6-plus`. Defect is SB doc drift only.
8. **Stale tests (D):** 3 pre-existing failures from live config drift. `test_agent_card_name` is a symptom of root cause #4; the other two are genuinely stale expectations.

## Design

### Workstream W1 — Sweep reliability

**W1a · Cross-run resume (`02117f37`) — decision: default-on.**
Before dispatching each task, scan `--log-dir` for an existing `.eval` log whose
header matches `(bench_alias, task)` and whose `status == "success"`. If found,
skip dispatch with a one-line message. Errored/partial/`started` logs are
**never** skipped (a killed run recovers past its failure point).

- Add `--no-resume` flag (forces a fully fresh run; required after scoring fixes, scorer changes, verify.sh/judge.md edits, or reference-cost updates — the SB gotcha is already recorded).
- Match key: `bench_alias` (the eval `model`) + task name from the filename regex already used in `results/core.py` (`_FNAME_RE`).
- Minimal storage-rework fold (`de5c9235`): the resume check targets `--log-dir` as-is; no logs/baselines split required here.
- **Implementation site:** `bench_cli/run/cli.py`.

**W1b · Plain-text progress (`b7414d96`).**
No custom progress bar. Use Inspect's built-in `PlainDisplay`:

- Pass `display="plain"` to `inspect_eval` when stdout is **not** a TTY (auto), or unconditionally when `--no-tui` is passed. Leave TTY behavior (default `full`) unchanged for interactive runs.
- Heartbeat for programmatic monitoring — **one-by-one mode only** (batch mode is a single blocking `inspect_eval` call with no per-task Python loop to hook; attempting an in-batch heartbeat would require filesystem-watching or Inspect internals, both out of scope). In one-by-one mode the existing per-task loop in `bench_cli/run/cli.py` appends one small JSON object per completed task to `logs/_runs/<model>.<ts>.status.json` — `{task, status, score, tokens, ts}`. Batch mode gets plain-text progress (same as one-by-one) plus a single post-run JSON summary written after the `inspect_eval` call returns (not a live heartbeat). This keeps the heartbeat implementable as written without Inspect internals or filesystem-watching.
- **Implementation site:** `bench_cli/run/cli.py`.

**W1c · Pricing merge-on-refresh (`0c44366f`) — decision: merge.**
Change `fetch_and_cache_prices()` to read existing `models`, then write `{**existing, **new}` instead of replacing. ~3 lines. Manual prices survive refresh.

- Edge case: if OpenRouter later lists a model that was manually priced, refresh overwrites the manual value. Acceptable (manual price was a stand-in for an unknown); document in the PRD `Gotchas` section and in SB.
- **Implementation site:** `bench_cli/pricing/price_cache.py`.

### Workstream W2 — Alias & card-identity stabilization (keystone)

**W2a · Deterministic card identity.**
Card filename slug and human name derive **from `bench_alias`**, not from the volatile `resolve_openrouter_id` reverse-lookup. The OpenRouter ID is used only for **price lookups**, never for card identity.

- `_slug_from_alias(bench_alias)`: deterministic mapping from bench alias to slug. Define the mapping once (e.g. `openai/<x>` → `<x>`, with a single explicit override table for any alias whose slug must differ from its bare form). Same input → same slug forever, independent of cache/config state.
- `_real_model_name`: derive from the same table or a parallel display-name table.
- **Implementation site:** `bench_cli/results/core.py`; the mapping table co-located or in `model_aliases.py`.
- **Migration note:** existing cards (13 files) keep their current slugs only if the new deterministic table reproduces them; otherwise the rename is a one-time, expected churn documented here.

**W2b · Skip router-tier monikers in `results generate`.**
`generate_card_for_model` and the bulk `results generate` path skip `default`, `thinking`, `heavy`, `background`, `smart-router` (meta-monikers per SB Operating Rules). No cards emitted for monikers.

**W2c · Regression tests.**
- Two distinct bench aliases never produce identical card data (filename + name + score block), guarding the original glm-5.1≡m2.7 bug. (The original card is deleted and cannot be diffed; the durable fix is the stabilized path + this test, not a forensic reproduction.)
- Identity stability: slug/name is invariant across a simulated cache refresh (mock `resolve_openrouter_id` returning different/`None` values).
- Naming test (`test_agent_card_name`) is **fixed by W2a** and moved into this regression group.

**W2d · Nemotron resolution (`01cfd589`).**
Per-model decision per NIM model: if resolvable, add the price-cache entry and alias-map mapping so `resolve_openrouter_id` returns the correct OpenRouter ID; if genuinely unpriced/unlisted, the cost pillar returns NaN by design (soft stop) — document as NaN-correct, not a bug. Confirm the historical `0.000`/`0.030` anomalies do not reproduce under the stabilized path.

### Workstream W3 — Scoring coherence (decision: A′)

**W3a · Recompute all three ratios at view time.**
Extend `compare/core.py` so token_ratio and time_ratio are recomputed from actuals + current reference, mirroring the existing price recompute (`:328`). Old logs re-cohere automatically; nothing is mutated on disk.

**W3b · Cost joins the BaselineStore chain.**
Add a `reference_cost_usd: float | None` field to `Baseline` (`scorers/baseline_store.py`); add a Tier-1 cost path in `price_ratio_scorer` (use `BaselineStore` entry if valid, else fall through to `task_budget.reference_cost_usd`); have `bench baseline record` (`bench_cli/baseline.py`) capture per-task cost from the run. All three pillars then share one 3-tier chain.

**W3c · Labeled ratio columns.**
Each ratio column header in `compare` output states its reference model inline ("efficiency vs `<ref>`", "cost vs `<ref>`", "latency vs `<ref>`").

**W3d · Populate the unified reference (run-time, Phase 2).**
Run minimax-m3 (`282a1c2e`) first, then `bench baseline record --model openai/minimax-m3` → it becomes the unified Tier-1 reference for all three pillars. Then run the other 9 models. (This is a run step, not code; included here so the coherence goal is concretely achievable.)

### Workstream W4 — Judge doc drift (`532e0ee4`)

SB Decisions + Gotchas updated via `brain-ctl`: judge model is `openai/judge → openai/qwen3.6-plus` (not GLM-5.1). No code change.

### Workstream W5 — Test health (D)

- Fix the 2 genuinely-stale expectation tests: `test_gate_blocks_without_api_key_when_price_missing`, `test_resolve_openrouter_id_litellm_name_without_prefix` (`rut → glm-5.2`).
- `test_agent_card_name` is fixed by W2a (folds into W2c).

## Success Criteria

1. `bench run` (default) skips `(model, task)` pairs that have a `status="success"` log; `--no-resume` re-runs everything.
2. Backgrounded `bench run` (redirected stdout) emits plain-text, grep-able progress; one-by-one mode additionally updates `logs/_runs/<model>.<ts>.status.json` per task (batch mode writes a post-run summary, not a live heartbeat).
3. Seed the 3 manual prices via `bench prices add` (each alias is configured in `~/dev/litellm/config.yaml`; values from SB handoff 2026-06-16): `bench prices add openai/mistral-large-3-675b 0.50 1.50`, `bench prices add openai/nemotron-nano-omni-30b 0.25 0.50`, `bench prices add openai/diffusiongemma-26b-a4b 0.06 0.33`. Then run `bench prices refresh`, then assert the 3 remain in the cache. (They are currently absent from repo and cache — verified — having been wiped by the bug W1c fixes.)
4. Two distinct models never produce identical card data; card slug/name is invariant across a cache refresh (regression test).
5. `bench results generate` emits no cards for router-tier monikers.
6. `bench compare` recomputes all three ratio columns from current references; each ratio column header names its reference model.
7. `bench baseline record --model X` records cost alongside tokens/latency; `price_ratio_scorer` uses the Tier-1 cost entry when present.
8. SB context (`brain-ctl context bench`) states judge → `qwen3.6-plus`.
9. `.venv/bin/pytest` is fully green — all currently-green tests (547) plus the 3 previously-failing config-drift tests now green, 0 failures, on a clean checkout, with no new failures introduced.
10. **(W2d)** Each nemotron model under test resolves to a correct OpenRouter ID with a price, or is documented NaN-correct. Audit inventory (concrete aliases, not invented): the `01cfd589` anomaly subjects (`openai/nvidia-nemotron-3-super-120b-a12b`, `openai/nvidia-nemotron-3-nano-30b-a3b`), the test alias (`openai/nvidia-nemotron-30b` from `tests/test_results.py:445`), and the LiteLLM-configured `openai/nemotron-nano-omni-30b` + `openai/nemotron-ultra-550b`. The historical `0.000`/`0.030` anomalies (`01cfd589`) do not reproduce under the stabilized path.

## Implementation Order

W2 (keystone; unblocks clean tests) → W1 → W3 → W5 + W4 → sweep (W3d: minimax-m3 first).

## Risks & Open Questions

- **W2a migration churn:** changing the slug derivation may rename existing cards. Decision needed at implementation time: migrate old filenames or accept one-time churn. Mitigation: choose the deterministic table to reproduce existing slugs where possible.
- **W3a blast radius:** recomputing token/latency ratios changes displayed numbers for all historical logs (this is the intended coherence fix). Document the before/after in the runbook; no on-disk mutation.
- **W2d ambiguity:** some nemotron NIM models may have no OpenRouter listing at all. Starting inventory to audit (from `results/`): `nvidia-nemotron-3-nano-30b-a3b`, `nvidia-nemotron-3-super-120b-a12b`, plus the `nemotron-30b`/`nemotron-30b-a3b` aliases in `tests`. Resolution per model: NaN-correct documentation vs. manual price — decided during implementation, default NaN-correct unless manually priceable.
- **Original #5 not forensically reproducible:** the corrupt glm-5.1 card was deleted. W2a + W2c is the durable prevention, not a diff-verified reproduction of the original bug.

## Verification

- `.venv/bin/pytest` fully green (no new failures; the 3 pre-existing failures resolved by W2a/W5).
- Targeted regression tests for each workstream (see W2c; resume, pricing-merge, progress, recompute, cost-tier, moniker-skip).
- Manual smoke: a short `bench run --tier quick` that is killed mid-way resumes on re-run, logs plain progress, and produces a correctly-attributed card.
