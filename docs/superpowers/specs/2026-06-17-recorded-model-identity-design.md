# Recorded Model Identity — Decouple Routing Name from Recorded Name

**Date:** 2026-06-17
**Status:** Design (awaiting plan)
**Scope:** `bench_cli/run`, `bench_cli/pricing`, `bench_cli/results`, `bench_cli/compare`, `bench_cli/discriminative`, `scorers`

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

- `--model` = **routing** name, sent to the proxy. Unchanged from today. Accepts
  bare names via the existing `resolve_model()` resolver (which prepends
  `openai/`), or full `openai/<alias>`.
- **Recorded name** (written to `el.eval.model`, used by resume / compare /
  cards / price-gate / slug) = derived automatically:
  1. If `--as` is given → the literal `--as` value, **as-is, no prefix applied**
     (e.g. `--as nemotron-ultra-550b` records `nemotron-ultra-550b`).
  2. Else `resolve_openrouter_id(--model)` → the raw OpenRouter id
     (e.g. `minimaxai/minimax-m3`, `nvidia/nemotron-3-ultra-550b-a55b`).
  3. Else (resolver returns None — managed/local model, or unknown alias) →
     `--model` unchanged (preserves today's behavior for local models).
- `--as` accepts bare names (`nemotron-ultra-550b`) or full names
  (`nvidia/nemotron-3-ultra-550b-a55b`); stored literally either way.

### Auto-resolution applies to all aliases

Recognizable aliases are normalized too: `--model openai/nemotron-ultra-550b`
records `nvidia/nemotron-3-ultra-550b-a55b`; `--model openai/glm-plan-5.2`
records `zai/glm-5.2`. One rule, uniformly applied. This is more accurate (the
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

- `resolver.py:62` `bare_name` — delegate to `bare_model_name`.
- `compare/core.py:378` `_short_model` — delegate to `bare_model_name`.
- `discriminative/subject.py` `_normalize_model` — delegate to `bare_model_name`.
- `results/core.py` `_slug_from_alias` / `_real_model_name` — derive from the
  *recorded* (full) name via `bare_model_name`, so a recorded `minimaxai/minimax-m3`
  slugs to `minimaxai-minimax-m3` and displays as `minimax-m3`. `is_moniker_alias`
  checks against the bare name.
- `run/core.py` resume (`el.eval.model == recorded_name`) — rewritten logs store
  `recorded_name`, and resume compares against the same `recorded_name`, so
  equality holds.

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
`price_ratio_scorer`) preserved. `EvalLog.location` is a `file://` URI; strip the
prefix to get the filesystem path. `inspect_eval()` returns `list[EvalLog]`; each
result carries `.location`.

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

### Flow change (single module: `bench_cli/run`)

1. `run/cli.py`: add `--as` option. Compute `recorded_name` (via the resolution
   rule above) right after parsing `--model`/`--as`. Pass both `routed_name`
   (= normalized `--model`) and `recorded_name` into the run function.
2. `run/core.py`: pass `routed_name` to `inspect_eval(model=...)` in both batch
   and one-by-one branches. After each log writes, call
   `rewrite_log_model_name(log.location, recorded_name)` when
   `recorded_name != routed_name`.
3. Resume check (`el.eval.model == recorded_name`), price gate, status/heartbeat
   paths, summary, and card generation all use **`recorded_name`** (what the
   logs actually store after rewrite), so they key on the recognizable identity.

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
- **Auto-normalize all aliases, not monikers-only.** Single rule; more accurate.
- **Resume-continuity across the name change: handled by `--as`, not by fuzzy
  matching.** Re-running an existing model records a different name than its old
  logs (e.g. new `--model openai/glm-plan-5.2` → `zai/glm-5.2`, old logs say
  `openai/glm-plan-5.2`), so resume will re-run everything. To resume an old run
  in the old identity, pass `--as openai/glm-plan-5.2`. Documented in `--help`
  and the runbook. (Fuzzy matching on bare names was rejected as hacky.)
- **Log rewrite is non-fatal.** Warn-and-continue protects long runs.
- **Pricing scorer untouched.** It runs during eval against the routed name and
  stores a name-independent USD cost value; correctness/token/latency/cost all
  survive recorded-name changes.
- **Reuses `resolve_openrouter_id`** as the single "recognizable name" resolver —
  same function pricing uses. No parallel system. The `[bracket]` pricing
  override remains a separate, composable concern.

## Edge Cases

| Case | Behavior |
|---|---|
| `--as` equals `--model` recorded form | No rewrite; identical to a normal run. |
| `--as` given for a managed/local model (`openai/qwen-local`) | Recorded as the `--as` literal. Local pricing (`is_managed_model`) still applies via resolver fallback; if `--as` breaks local detection, pricing NaNs — documented as user's choice. |
| `resolve_openrouter_id` returns None (unknown alias) | Recorded name falls back to `--model` unchanged (today's behavior). No rewrite. |
| Rewrite throws (missing file / zip error) | Warn, leave routed name in log, continue. |
| `--model openai/thinking` and `thinking` later rebinds to a different backing model | The recorded OR id (`minimaxai/minimax-m3`) stays correct for *these* logs because it was resolved at run time; future runs under the same moniker get a different recorded id. This is the feature working as intended. |
| Batch (non-sequential) mode | Rewrite each result log in the returned list after the single `inspect_eval` call returns. |
| `inspect_eval` itself records the routed name and the proxy re-resolves per call | Intended — routing correctness is unchanged; only the *recorded* identity changes. |

## Testing

TDD, Red-Green-Refactor per the sp pipeline. Test locations: `tests/` (new file
or extend existing).

1. **`resolve_recorded_name(--model, --as)`** unit:
   - `--as` present → returns literal `--as`.
   - `--as` None, recognizable alias → returns `resolve_openrouter_id` result
     (e.g. `openai/nemotron-ultra-550b` → `nvidia/nemotron-3-ultra-550b-a55b`).
   - `--as` None, moniker → returns OR id of current backing model
     (`openai/thinking` → `minimaxai/minimax-m3`).
   - `--as` None, unknown/local → returns `--model` unchanged.
2. **`bare_model_name`** unit: `openai/x`→`x`, `minimaxai/minimax-m3`→`minimax-m3`,
   `nemotron-ultra-550b`→`nemotron-ultra-550b` (no slash).
3. **`rewrite_log_model_name`** round-trip on a real (or fixture) `.eval`:
   - `eval.model` changed; samples preserved; all 4 scorer Score objects present
     and intact.
   - Idempotent (rewriting to the same name is a no-op).
   - Non-fatal: missing file / corrupt zip → returns False, raises nothing.
4. **Display/moniker sites** updated via `bare_model_name`:
   - `is_moniker_alias("minimaxai/minimax-m3")` → False (bare `minimax-m3` not a
     moniker); `is_moniker_alias("openai/thinking")` → True (bare `thinking`).
   - `compare` `_short_model("minimaxai/minimax-m3")` → `minimax-m3`.
5. **End-to-end (mocked `inspect_eval`):** `--model openai/thinking --as
   nemotron-ultra-550b` → `inspect_eval` called with `model="openai/thinking"`,
   and the resulting log's `eval.model` is `nemotron-ultra-550b`. Without
   `--as`: `inspect_eval` called with `model="openai/thinking"`, log records
   `minimaxai/minimax-m3`.

## Blast Radius

| File | Change | Risk |
|---|---|---|
| `bench_cli/run/cli.py` | Add `--as` option; compute & thread `routed_name` + `recorded_name`. | Low. Additive. |
| `bench_cli/run/core.py` | Pass `routed_name` to `inspect_eval`; add `rewrite_log_model_name`; call it after each log writes. Resume/price-gate/status/card-gen use `recorded_name`. | Medium. Core eval path; covered by e2e test. |
| `bench_cli/resolver.py` | Add `bare_model_name`; delegate `bare_name` to it. | Low. |
| `bench_cli/compare/core.py` | `_short_model` → `bare_model_name`. | Low. |
| `bench_cli/discriminative/subject.py` | `_normalize_model` → `bare_model_name`. | Low. |
| `bench_cli/results/core.py` | `_slug_from_alias`/`_real_model_name`/`is_moniker_alias` derive via `bare_model_name` from the recorded full name. | Medium. Card generation path; covered by slug/moniker tests. |
| `scorers/*` | **None.** Pricing scorer reads routed name during eval; cost value is name-independent. | None. |
| `tests/` | New + extended tests (above). | — |

## Risks / Residual

- **Existing logs retain `openai/`-prefixed names.** `compare` and `results`
  must handle a *mix* of old (`openai/glm-plan-5.2`) and new (`zai/glm-5.2`)
  recorded names. `bare_model_name` handles both (strips first segment either
  way), so display is consistent; but the same model may appear as two distinct
  columns/subjects until old logs age out. Mitigation: `--as` lets a re-run
  deliberately adopt the old name if continuity matters. Documented.
- **`is_managed_model` and `--as` interaction.** A local model given a custom
  `--as` may lose `-local` suffix detection and NaN on pricing. Documented as
  user's choice; not auto-handled.
- **Inspect API drift.** Round-trip verified against `inspect-ai 0.3.210`.
  Future Inspect changes to the `.eval` binary format could break the rewrite.
  Mitigation: non-fatal rewrite + test against a fixture log.
