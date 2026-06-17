# Recorded Model Identity — Decouple Routing Name from Recorded Name

**Date:** 2026-06-17
**Status:** Design (rev 2 — post document-reviewer; awaiting plan)
**Scope:** `bench_cli/run`, `bench_cli/pricing`, `bench_cli/results`, `bench_cli/compare`, `bench_cli/show`, `bench_cli/dashboard`, `bench_cli/score`, `bench_cli/inspect`, `bench_cli/discriminative`, `scorers`

## Problem

Models route through a LiteLLM proxy under role-based aliases (`openai/thinking`,
`openai/default`, `openai/heavy`). Those monikers rebind over time — today
`thinking` → `minimaxai/minimax-m3`, tomorrow something else — so recording the
moniker in an eval log produces unrecognizable, time-varying, and easily
mis-attributed subject identities. The SB Operating Rule already warns against
treating router monikers as fixed subjects.

The user wants:

- Route through whatever alias the proxy exposes (e.g. `openai/thinking`).
- **Record a recognizable identity** in logs / resume / compare / cards /
  pricing — by default the real OpenRouter id (e.g. `minimaxai/minimax-m3`),
  which carries the creating entity and is stable across proxy reshuffles.
- Override the recorded name with a custom label when the auto-resolved OR id is
  wrong or undesirable (`--as nemotron-ultra-550b`).
- One mechanism for the "what is the recognizable name" question, reusing the
  resolver pricing already uses (`resolve_openrouter_id`) — not a parallel
  system.
- Stop leaking the `openai/` LiteLLM-routing prefix into recorded identity. The
  `openai/` prefix is a proxy artifact; subsystems that assume it must be
  reworked (unless super hard — it isn't, see below).

Today's only override, the `[openrouter_id]` bracket suffix on `--model`, is a
**pricing-only** mechanism (forces a price lookup ID for models missing from the
cache). It does not touch the recorded identity. This feature is orthogonal and
composes with it.

## Non-Goals

- Changing how pricing is computed (the price scorer reads `state.model` during
  eval and resolves via the same `resolve_openrouter_id`; the cost *value* it
  stores is name-independent USD, so pricing is unaffected by recorded-name
  changes).
- Migrating or rewriting existing logs. Old logs keep their recorded names; new
  runs record OR ids. Resume-continuity across the name change is handled by
  `--as` (see Decisions).
- Altering the `[bracket]` pricing override.
- Touching agent eval (`--agent`) identity handling in this pass.

## Design

### CLI surface

```
bench run --model openai/<routing-alias>            [--as <recorded-name>]
bench run --model openai/<recognizable-alias>       [--as <recorded-name>]
```

- `--model` = **routing** name, sent to the proxy. Unchanged from today.
  `bench run` passes `--model` through `parse_model_arg` directly to
  `inspect_eval(model=…)` — it does **not** call `resolve_model()` (that resolver
  is used only by `show`/`score`), so `--model` must already be `openai/<alias>`
  (or bare — Inspect's openai provider treats `openai/<bare>` as the model id).
- **Recorded name** (written to `el.eval.model`, used by resume / compare /
  cards / price-gate / slug) = derived from `routed_name` (`--model`) and the
  optional `--as`:
  1. If `--as` is given → the literal `--as` value, **as-is, no prefix applied**
     (e.g. `--as nemotron-ultra-550b` records `nemotron-ultra-550b`).
  2. Else if `is_managed_model(routed_name)` (local/managed models) →
     `routed_name` **unchanged**. **MUST short-circuit before the resolver**:
     verified `resolve_openrouter_id("openai/qwen-local")` returns a non-None
     LiteLLM id (`huihui-qwen3.5-35b-a3b-claude-4.6-opus-abliterated`), so
     without this short-circuit local-model identity gets silently corrupted.
     (`is_managed_model` checks `-local` suffix or the managed allowlist.)
  3. Else `resolve_openrouter_id(routed_name)` → the raw OpenRouter id
     (e.g. `minimaxai/minimax-m3`, `nvidia/nemotron-3-ultra-550b-a55b`).
  4. Else (resolver returns None — unknown alias with no managed match) →
     `routed_name` unchanged.
- `--as` accepts bare names (`nemotron-ultra-550b`) or full names
  (`nvidia/nemotron-3-ultra-550b-a55b`); stored literally either way.

### Auto-resolution applies to all aliases

Recognizable aliases are normalized too: `--model openai/nemotron-ultra-550b`
records `nvidia/nemotron-3-ultra-550b-a55b`; `--model openai/glm-plan-5.2`
records `z-ai/glm-5.2`. Managed/local models are **exempt** (short-circuit, see
rule 2 above) so `openai/qwen-local` records `openai/qwen-local`, not a
nonsensical LiteLLM id. One rule, uniformly applied. This is more accurate (the
recorded id is the real, cache-keyed, price-resolvable identity) and removes the
need for special-casing monikers vs recognizable aliases.

### `openai/` prefix removal — single normalization helper

Introduce one function in `bench_cli/resolver.py`:

```python
def bare_model_name(model: str) -> str:
    """Everything after the first '/' segment, or the whole string if none.

    'openai/thinking'          -> 'thinking'
    'minimaxai/minimax-m3'     -> 'minimax-m3'
    'nvidia/nemotron-3-ultra-550b-a55b' -> 'nemotron-3-ultra-550b-a55b'
    'nemotron-ultra-550b'      -> 'nemotron-ultra-550b'
    """
    return model.split("/", 1)[1] if "/" in model else model
```

Used everywhere a *display / moniker-check / slug* name is derived. The existing
ad-hoc `.removeprefix("openai/")` and `.replace("openai/", "")` sites are routed
through it. **Pricing, resume, and identity-matching key on the full recorded
string** (`el.eval.model`), so they are unaffected by the prefix change.

Sites to update (display/moniker/slug only — see Blast Radius):

- `resolver.py:60` `bare_name` — delegate to `bare_model_name`. **Ripples to 4
  consumers** that import `bare_name` for display: `show.py`, `dashboard.py`,
  `score.py`, `compare/core.py`. Intended (OR-id names display as their bare
  segment), but all four are in scope.
- `compare/core.py:376` `_short_model` (body :378) — delegate to `bare_model_name`.
- `discriminative/subject.py:84` `_normalize_model` — delegate to `bare_model_name`
  (the function is already byte-identical in behavior, so delegation is a
  no-op refactor; the real discriminative fix is B4 below).
- `results/core.py` `_slug_from_alias` / `_real_model_name` — **explicit rule**:
  slug = recorded full name with `/`→`-` (e.g. `minimaxai-minimax-m3`);
  display name = `bare_model_name(recorded)` (e.g. `minimax-m3`). These two
  transforms differ — do not conflate them. Note: current code deliberately
  derives slug/name from the **static `MODEL_ALIAS_MAP`** keyed by bench alias
  and does NOT call `resolve_openrouter_id` (a recently-landed NVIDIA-sweep
  fix, `docs/PRD-NVIDIA-SWEEP-READINESS.md`). Once the input is the recorded OR
  id, that static map is redundant (its value equals the recorded name), so
  removing it is **intentional**, not a regression — state this in the plan.
  `is_moniker_alias` checks the bare name.
- `run/cli.py` resume (`_completed_tasks`: `el.eval.model == recorded_name`) —
  rewritten logs store `recorded_name`, and resume compares against the same
  `recorded_name`, so equality holds. (Note: `_completed_tasks` is *defined* in
  `run/core.py:47` but *called* from `run/cli.py:352`.)

### Discriminative subsystem — deeper fix (B4)

`bench_cli/discriminative/subject.py` resolves the subject model from
**`sample.model_usage` keys** (`subject.py:34-43`), which are **routed names**
(verified: keys are `['openai/glm-plan-5.2', 'openai/judge']`), NOT
`el.eval.model`. So even after the log rewrite, discriminative subjects would
still be monikers (`openai/thinking`), directly defeating this feature for that
subsystem. The `get_all_log_paths` dedup (`subject.py:113,127`) keys on
`el.eval.model` (the recorded id), so dedup and subject identity would also
diverge.

Fix: `resolve_subject_from_log` must read the model identity from
**`el.eval.model`** (the recorded name) as the primary source, keeping the
`model_usage` key only as a fallback for legacy logs. This makes discriminative
key off the recognizable identity and aligns dedup with subject identity.
Delegating `_normalize_model` to `bare_model_name` is necessary but not
sufficient on its own.

### Log rewrite (the actual relabeling mechanism)

After each task's `.eval` log is written by `inspect_eval`, if the recorded name
differs from the routed name, rewrite the log:

```python
def rewrite_log_model_name(log_path: Path, recorded_name: str) -> bool:
    """Read eval log, set eval.model = recorded_name, write back. Non-fatal."""
    el = read_eval_log(str(log_path))
    if el.eval.model == recorded_name:
        return True  # nothing to do
    el.eval.model = recorded_name
    write_eval_log(el, str(log_path))
    return True
```

Verified mechanics (2026-06-17): `read_eval_log → set log.eval.model →
write_eval_log` round-trips cleanly — samples and all four scorers
(`verify_sh`/`llm_judge`, `token_ratio_scorer`, `time_ratio_scorer`,
`price_ratio_scorer`) preserved. `inspect_eval()` returns `list[EvalLog]`; each
result carries `.location`.

`.location` is a **`file://` URI when read from disk**
(`file:///Users/rut/dev/bench/logs/….eval`) and a plain filesystem path after
`write_eval_log` to a fresh location. Strip a leading `file://` defensively so
both forms resolve to a real path.

Rewrite is **non-fatal**: on any exception (file not found, zip corruption,
permission), warn and continue with the routed name in the log. Rationale: a
3-hour sequential run must not be lost to a relabeling I/O hiccup.

### Terminology (used throughout the implementation)

- `routed_name` = what hits the proxy = the normalized `--model` value (e.g.
  `openai/thinking`). Passed to `inspect_eval(model=...)`.
- `recorded_name` = what gets written into `el.eval.model` and used by resume /
  compare / cards / price-gate / slug. = `--as` literal, else
  `resolve_openrouter_id(--model)`, else `--model` unchanged.

These are two distinct strings whenever routing and recording differ. Do not
reuse one variable name for both.

### Flow change (the eval hook lives in `run/cli.py`, not `run/core.py`)

**Verified locations:** `inspect_eval(...)` is *called* at `run/cli.py:389`
(one-by-one) and `run/cli.py:423` (batch), with `model=bench_alias` at `:391`/`:425`.
`_completed_tasks` is *defined* in `run/core.py:47` but *called* from
`run/cli.py:352`. `_check_price_gate` is called at `run/cli.py:332`. The status/
summary helpers (`_status_path`, `_write_run_summary`) are in `run/cli.py`.

1. `run/cli.py`: add `--as` option. Compute `recorded_name` (via the resolution
   rule above, including the managed-model short-circuit) right after parsing
   `--model`/`--as`. Set `routed_name = bench_alias` (the parsed `--model`).
2. `run/cli.py`: pass `routed_name` to both `inspect_eval(model=…)` call sites
   (`:391`, `:425`). After each result log is obtained, call
   `rewrite_log_model_name(log.location, recorded_name)` when
   `recorded_name != routed_name` (one-by-one: after each task; batch: iterate
   the returned list).
3. `run/cli.py`: resume (`_completed_tasks`), price gate (`_check_price_gate`),
   status/heartbeat paths, summary, and card generation all use
   **`recorded_name`** (what the logs actually store after rewrite), so they key
   on the recognizable identity. `bench_alias` as threaded through these today
   becomes `recorded_name`.

### `bench_cli/inspect` — exact-match regression (B2)

`inspect/core.py:131, 323, 347` filter logs with `if el.eval.model !=
model_alias: continue`. Callers pass a resolved **bench alias** (e.g.
`openai/thinking`) via `_resolve_alias(model_alias)` in `inspect/cli.py:49,143,242`.
After the log rewrite, `el.eval.model` holds the recorded OR id (or `--as`
value), so `bench inspect stats|compare|deep-check --model openai/thinking` finds
**zero logs**. Fix: `inspect/cli.py` (or `inspect/core.py`) must run the same
`recorded_name` resolution on the user-supplied `--model` before filtering, so a
user can query by either the routing alias or the recorded name. In scope; see
Blast Radius.

### Name-flow summary

```
--model openai/thinking                 --as nemotron-ultra-550b
        |                                      |
        v                                      v
  routed = "openai/thinking"           recorded = "nemotron-ultra-550b"
        |                                      |
        |   inspect_eval(model=routed)         |
        |   -> proxy hits minimax-m3           |
        v                                      v
  log.eval.model = "openai/thinking"   rewrite -> "nemotron-ultra-550b"
                                               |
                                               v
        resume / compare / card / slug / price-gate
        all read "nemotron-ultra-550b"
```

## Decisions

- **Recorded name = raw OR id (option b), not `openai/<bare>`.** Carries the
  creating entity. `--as` values stored literally as given (no prefix).
- **Auto-normalize all aliases, not monikers-only** — but managed/local models are
  short-circuited to preserve their identity. Single rule; more accurate.
- **Resume-continuity across the name change: handled by `--as`, not by fuzzy
  matching.** Re-running an existing model records a different name than its old
  logs (e.g. new `--model openai/glm-plan-5.2` → `z-ai/glm-5.2`, old logs say
  `openai/glm-plan-5.2`), so resume will re-run everything. To resume an old run
  in the old identity, pass `--as openai/glm-plan-5.2`. Documented in `--help`
  and the runbook. (Fuzzy matching on bare names was rejected as hacky.)
- **Log rewrite is non-fatal.** Warn-and-continue protects long runs.
- **Pricing scorer untouched.** It runs during eval against the routed name and
  stores a name-independent USD cost value; correctness/token/latency/cost all
  survive recorded-name changes. (Verified: `scorers/price_ratio.py:152` scores
  `str(state.model)`, the routed name, during eval.)
- **Reuses `resolve_openrouter_id`** as the single "recognizable name" resolver —
  same function pricing uses. No parallel system. The `[bracket]` pricing
  override remains a separate, composable concern.
- **Discriminative reads `el.eval.model` (recorded), not `model_usage` keys
  (routed).** See the Discriminative subsystem section.

## Edge Cases

| Case | Behavior |
|---|---|
| `--as` equals `--model` recorded form | No rewrite; identical to a normal run. |
| `--as` given for a managed/local model (`openai/qwen-local`) | Recorded as the `--as` literal. `is_managed_model` checks suffix/allowlist on the `--model` routed name (not the recorded name), so local pricing still applies as long as `--model` is the local alias; if `--as` is used purely to rename, pricing detection keys on `--model` and is unaffected. |
| `--as` None, managed/local model (`openai/qwen-local`) | Short-circuit (rule 2): records `openai/qwen-local` unchanged. NOT resolved to a LiteLLM id. |
| `resolve_openrouter_id` returns None (unknown alias) | Recorded name falls back to `--model` unchanged (today's behavior). No rewrite. |
| Rewrite throws (missing file / zip error) | Warn, leave routed name in log, continue. |
| `--model openai/thinking` and `thinking` later rebinds to a different backing model | The recorded OR id (`minimaxai/minimax-m3`) stays correct for *these* logs because it was resolved at run time; future runs under the same moniker get a different recorded id. This is the feature working as intended. |
| Batch (non-sequential) mode | Rewrite each result log in the returned list after the single `inspect_eval` call returns. |
| `inspect_eval` itself records the routed name and the proxy re-resolves per call | Intended — routing correctness is unchanged; only the *recorded* identity changes. |
| `bench inspect --model openai/thinking` after a rewritten run | `inspect` resolves the recorded name (OR id) and matches rewritten logs; querying by either routing alias or recorded name works. |
| Discriminative on a rewritten log | Subject id = recorded OR id (from `el.eval.model`); dedup aligns. Legacy logs (routed-name `el.eval.model`) fall back to `model_usage` key. |

## Testing

TDD, Red-Green-Refactor per the sp pipeline. Test locations: `tests/` (new file
or extend existing).

**Proxy-stability principle:** the recorded-model-identity feature touches a
moving target — the LiteLLM proxy (`~/dev/litellm/config.yaml`) rebinds router
monikers over time. Tests that hardcode "moniker X resolves to concrete model Y"
break every rebind. **Tests assert invariants and resolve live at setup time**
instead of pinning concrete model ids.

1. **`resolve_recorded_name(--model, --as)`** unit:
   - `--as` present → returns literal `--as`.
   - `--as` None, recognizable alias → returns `resolve_openrouter_id` result
     (e.g. `openai/nemotron-ultra-550b` → `nvidia/nemotron-3-ultra-550b-a55b`).
     Uses stable MODEL_ALIAS_MAP-backed aliases (which don't drift) — proxy-stable.
   - `--as` None, **managed/local** → returns `--model` unchanged (RED today:
     `resolve_openrouter_id("openai/qwen-local")` returns a non-None LiteLLM id).
     `openai/qwen-local` → `openai/qwen-local`.
   - `--as` None, unknown (no managed match, resolver None) → `--model` unchanged.
   - (Removed: the moniker→OR-id value test, since the proxy-routed path is
     covered end-to-end by test #8.)
2. **`bare_model_name`** unit: `openai/x`→`x`, `minimaxai/minimax-m3`→`minimax-m3`,
   `nemotron-ultra-550b`→`nemotron-ultra-550b` (no slash).
3. **`rewrite_log_model_name`** round-trip on a real (or fixture) `.eval`:
   - `eval.model` changed; samples preserved; all 4 scorer Score objects present
     and intact.
   - Idempotent (rewriting to the same name is a no-op).
   - Non-fatal: missing file / corrupt zip → returns False, raises nothing.
   - `.location` is `file://`-prefixed from disk and plain after write — both
     forms resolve correctly.
4. **Display/moniker sites** updated via `bare_model_name`:
   - `is_moniker_alias("minimaxai/minimax-m3")` → False (bare `minimax-m3` not a
     moniker); `is_moniker_alias("openai/thinking")` → True (bare `thinking`).
   - `compare` `_short_model("minimaxai/minimax-m3")` → `minimax-m3`.
   - `show`/`dashboard`/`score` display via delegated `bare_name`.
5. **Results card metadata (R1):** `generate_card("nvidia/nemotron-3-ultra-550b-a55b", …)`
   → `_get_model_metadata` sets provider=NVIDIA (not generic "API"); `is_managed_model`
   returns False (not free). And slug = `nvidia-nemotron-3-ultra-550b-a55b`, display =
   `nemotron-3-ultra-550b-a55b`, `is_moniker_alias` False.
6. **Discriminative subject identity (B4):** on a fixture log whose `el.eval.model`
   was rewritten but `model_usage` key is the routed name,
   `resolve_subject_from_log` returns the **recorded** model from `el.eval.model`.
7. **`bench inspect` resolution (B2):** given rewritten logs, `inspect` finds them
   whether queried by routing alias OR recorded OR id. The round-trip test uses
   **live resolution at setup** (`resolve_recorded_name("openai/thinking", None)`)
   so it follows the proxy by design — a proxy rebind does not break it.
8. **End-to-end (mocked `inspect_eval`):** `--model openai/thinking --as
   nemotron-ultra-550b` → `inspect_eval` called with `model="openai/thinking"`,
   and the resulting log's `eval.model` is `nemotron-ultra-550b`. Without
   `--as`: `inspect_eval` called with `model="openai/thinking"`, log records
   the live-resolved backing model. Both assertions are **live-resolution**:
   the expected recorded name is whatever `resolve_recorded_name` returns at
   test time, so the test passes across proxy rebinds (the invariant under test
   is "record-side = live-resolved backing model," not a specific model id).
9. **B4 invariant** (rewritten from value-test): for every alias with a pricing
   override entry where backing_id != pricing_id, `resolve_recorded_name(alias)`
   must equal backing_id and never equal pricing_id. Proxy-stable: walks the
   `model_overrides.json` at test time and asserts the invariant for every
   divergent override.

## Blast Radius

| File | Change | Risk |
|---|---|---|
| `bench_cli/run/cli.py` | Add `--as`; compute `recorded_name` (with managed short-circuit); thread `routed_name`/`recorded_name`; pass `routed_name` to both `inspect_eval` call sites (`:391`,`:425`); call `rewrite_log_model_name` after each log; switch resume(`:352`)/price-gate(`:332`)/status/summary/card to `recorded_name`. | Medium. Core eval path; covered by e2e test. |
| `bench_cli/run/core.py` | Add `rewrite_log_model_name` + `resolve_recorded_name` helpers (the eval hook is NOT here — it's in cli.py). | Low. Pure helpers. |
| `bench_cli/resolver.py` | Add `bare_model_name`; delegate `bare_name` to it. | Low. |
| `bench_cli/show.py`, `dashboard.py`, `score.py` | No code change, but display changes via delegated `bare_name` (in scope/known). | Low. |
| `bench_cli/compare/core.py` | `_short_model` → `bare_model_name`. Note cost-recalc fallback (`:172`) keys on `model_alias` vs `model_usage` routed-name keys — narrow, fires only when scorer missed cost; left as-is, documented residual. | Low. |
| `bench_cli/inspect/cli.py` + `inspect/core.py` | Resolve user `--model` to recorded name before the `el.eval.model != model_alias` filters (`core.py:131,323,347`). | Medium. User-facing CLI; covered by test #7. |
| `bench_cli/discriminative/subject.py` | `resolve_subject_from_log` reads `el.eval.model` (recorded) as primary, `model_usage` key as fallback; `_normalize_model` → `bare_model_name`. Aligns dedup with subject identity. | Medium. Covered by test #6. |
| `bench_cli/results/core.py` | `_slug_from_alias`/`_real_model_name`: slug=full `/`→`-`, display=`bare_model_name`; **redundant static `MODEL_ALIAS_MAP` lookup removed** (intentional); `is_moniker_alias` checks bare name. `_get_model_metadata` provider/free detection must key on recorded name correctly (R1) — likely already works via `litellm_model` substring; verify in impl. | Medium. Card generation; covered by test #5. |
| `scorers/*` | **None.** Pricing scorer reads routed name during eval; cost value is name-independent. | None. |
| `tests/` | New + extended tests (above). | — |

## Risks / Residual

- **Existing logs retain `openai/`-prefixed names.** `compare` and `results`
  must handle a *mix* of old (`openai/glm-plan-5.2`) and new (`z-ai/glm-5.2`)
  recorded names. `bare_model_name` handles both (strips first segment either
  way), so display is consistent; but the same model may appear as two distinct
  columns/subjects until old logs age out. Mitigation: `--as` lets a re-run
  deliberately adopt the old name if continuity matters. Documented.
- **`is_managed_model` keys on the routed name (`--model`), not recorded.** When
  `--as` renames a local model, local pricing detection still reads `--model`,
  so it works; if a future path reads the recorded name for managed detection,
  it would break. Keep managed detection on the routed name. Documented.
- **Compare cost-recalc fallback (R4, narrow).** `compare/core.py:172` matches
  `model_alias` (recorded OR id) against `model_usage` keys (routed names); for
  judge-bearing multi-model samples the recalc returns None when the scorer
  didn't capture cost. Left as-is; only affects a rare fallback path. Documented.
- **Inspect API drift.** Round-trip verified against `inspect-ai 0.3.210`.
  Future Inspect changes to the `.eval` binary format could break the rewrite.
  Mitigation: non-fatal rewrite + test against a fixture log.
