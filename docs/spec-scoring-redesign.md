# Spec: Scoring & Discrimination Redesign

**Status:** draft
**PRD:** `docs/PRD-scoring-redesign.md` (validated, committed)
**Date:** 2026-07-11
**Scope:** All 5 phases — rescore migration, statistical honesty, harder tasks, IRT engine, preset router

---

## Architecture Overview

The redesign touches three layers:

```
┌─────────────────────────────────────────────────────┐
│  CLI layer (click commands)                          │
│  bench compare, bench rescore, bench irt, bench recommend-preset │
└──────────────┬──────────────────────────┬────────────┘
               │                          │
┌──────────────▼──────────────────────────▼────────────┐
│  Core logic (pure Python, testable without CLI)      │
│  compare/core.py, irt/fit.py, irt/items.py,          │
│  recommend/presets.py, rescore/core.py               │
└──────────────┬──────────────────────────┬────────────┘
               │                          │
┌──────────────▼──────────────────────────▼────────────┐
│  Data layer                                          │
│  .eval logs (read), rescored .eval logs (write),     │
│  task_budgets.py, pricing/                           │
└─────────────────────────────────────────────────────┘
```

**Key invariant:** Phases 0–1 modify only `compare/core.py`, `compare/cli.py`, and add `rescore/`. Phases 3–4 add new modules (`irt/`, `recommend/`). No phase modifies scorers — correctness stays pass@1.

---

## Phase 0 — Rescore Migration

**Goal:** Retire weighted formula from default view; add efficiency columns + sub-measures; offline rescore existing logs.

**Delivers:** SC 2, 3, 8, 11, 12.

### 0A — `bench rescore` command

**New files:**
- `bench_cli/rescore/__init__.py`
- `bench_cli/rescore/core.py` — rescore logic
- `bench_cli/rescore/cli.py` — click command
- `tests/test_rescore.py`

**Contract:**

```python
# bench_cli/rescore/core.py

@dataclass
class RescoreResult:
    total: int          # logs processed
    updated: int        # logs with score changes written back
    skipped: int        # logs skipped (corrupt/incompatible)
    skips: list[SkipInfo]  # per-skip detail

@dataclass
class SkipInfo:
    path: str
    reason: str  # "corrupt_zip", "missing_samples", "status_not_success", etc.

def rescore_logs(log_dir: str, *, dry_run: bool = False) -> RescoreResult:
    """Read all .eval logs, recompute absolute scores from logged usage,
    write updated logs. Zero API calls — reads existing model_usage only.

    Steps per log:
    1. Read EvalLog (zipfile)
    2. For each sample: recompute correctness from existing scores (pass@1)
    3. Compute per-sample cost from model_usage × market price
    4. Compute per-sample tokens, time from model_usage
    5. Write updated scores back to the log
    6. Report any log that can't be processed

    The rescore NEVER touches the correctness score — it only recomputes
    efficiency-derived values (cost, tokens, time) using the current
    pricing resolution pipeline.
    """
```

**CLI:**

```bash
bench rescore [--log-dir logs] [--dry-run] [--json]
```

Output:
```
Rescored 16 models × 34 tasks (544 logs):
  Updated: 502  Skipped: 42
  Skips:
    logs/2026-04-10_f12_surgical-fix_DEAD.eval: corrupt_zip
    logs/2026-03-22_q3-answer_question_X.eval: missing_samples
    ... (42 total)
```

**Test matrix:**
- `test_rescore_zero_api_calls` — mock HTTP, assert no calls
- `test_rescore_handles_corrupt_logs` — run against the 44 known-corrupt files, assert skip report
- `test_rescore_dry_run_no_write` — dry-run flag prevents log mutation
- `test_rescore_idempotent` — running twice produces no second update

### 0B — Retire weighted formula

**Modified files:**
- `bench_cli/compare/core.py`
- `bench_cli/compare/cli.py`
- `bench_cli/score.py` — delete or redirect to compare

**Changes to `compare/core.py`:**

1. Move `WEIGHT_CORRECTNESS`, `WEIGHT_PRICE_RATIO`, `WEIGHT_TIME_RATIO`, `WEIGHT_TOKEN_RATIO`, `_weighted_total()` behind a flag:

```python
def _weighted_total(agg: dict, *, legacy: bool = False) -> float | None:
    """Return weighted blend only when legacy=True. None otherwise."""
    if not legacy:
        return None
    # existing formula
```

2. `format_summary()` signature changes:

```python
def format_summary(
    data: CompareData,
    min_tasks: int = MIN_FULL_EVAL_TASKS,
    show_partial: bool = False,
    legacy_weighted: bool = False,  # NEW
) -> str:
```

When `legacy_weighted=False`:
- Header shows `Score: capability (pass@1 mean)` instead of the 4-weight formula line
- Models sorted by `correct_mean` descending
- Score column shows `correct_mean` as a percentage
- No "scores can exceed 1.0" note

When `legacy_weighted=True`:
- Preserves current behavior exactly (for backward comparison)

3. Same change in `format_compact_table()` and `format_pillar_table()`.

**`format_json()` contract:**

- Current behavior: emits per-model aggregates as JSON (no weighted total).
  SC2 is satisfied (no weighted score in default JSON output).
- New behavior: JSON output adds the new efficiency columns
  (cost_per_task, tokens_per_task, time_per_task, the 5 AA sub-measures,
  ci_low/ci_high). `legacy_weighted=True` adds a `legacy_weighted_total`
  field for backward-compatibility consumers; default is capability-only.
- CLI: `--legacy-weighted` flag in compare passes through to the JSON path
  too — `--json --legacy-weighted` produces the legacy JSON shape.

**Changes to `compare/cli.py`:**

```python
@click.option("--legacy-weighted", is_flag=True, default=False,
              help="Use deprecated weighted formula (0.5/0.2/0.15/0.15). Default is capability-only ranking.")
```

**`bench_cli/score.py`:** Delete. It reimplements a worse version of the weighted formula. `bench compare` is the single comparison surface.

**Register in `main.py`:** Remove `score_cmd` import and `cli.add_command(score_cmd)`.

### 0C — Efficiency columns

**Modified files:**
- `bench_cli/compare/core.py`

**New columns in `format_summary()` and `format_pillar_table()`:**

| Column | Source | Formula |
|--------|--------|---------|
| `cost/task` | `PillarScores.avg_cost_usd` | Σ per-sample cost / n_samples, per task, then mean across tasks |
| `tok/task` | `PillarScores.avg_tokens` | Σ per-sample total_tokens / n_samples, per task, then mean across tasks |
| `time/task` | `PillarScores.avg_time` | Σ per-sample working_time / n_samples, per task, then mean across tasks |

**Rendering rules:**
- `cost/task`: `$0.0024` format. `nan` → `n/a (unpriced)`
- `tok/task`: `2,619` format with thousands separator
- `time/task`: `40.6s` format

**New aggregation in `_aggregate_model_pillars()`:**

```python
return {
    ...,
    "cost_per_task": mean(avg_cost_usd across tasks where not nan),
    "tokens_per_task": mean(avg_tokens across tasks),     # total (reasoning + answer)
    "answer_tokens_per_task": mean(answer_tokens across tasks),   # NEW: visible-only
    "time_per_task": mean(avg_time across tasks),
}
```

**Reasoning vs answer token split (PRD gotcha):** Inspect `model_usage`
already carries per-token-type counts when reasoning models emit them
(`reasoning_tokens` / `answer_tokens`); older logs without the split
return `None` for the answer field. Both flow through.

### 0D — AA sub-measures

**Modified files:**
- `bench_cli/compare/core.py`

**New columns:**

| Column | Formula | Notes |
|--------|---------|-------|
| `$/suite` | Σ cost_per_task across all tasks | Total suite cost |
| `tok/suite` | Σ tokens_per_task across all tasks | Total suite tokens (incl. reasoning) |
| `tok-ans/suite` | Σ answer_tokens_per_task across all tasks | Visible-only tokens; `n/a` when not split |
| `s/suite` | Σ time_per_task across all tasks | Total suite wall time |
| `int/$` | capability / cost_per_task | `nan` if cost is nan → render `n/a` |
| `int/tok` | capability / answer_tokens_per_task | Answer-only when available, else total |
| `int/tok-total` | capability / tokens_per_task | Always computable, for comparison |

**In `_aggregate_model_pillars()`:**

```python
cap = agg["correct_mean"]
cost = agg["cost_per_task"]
toks_total = agg["tokens_per_task"]
toks_answer = agg.get("answer_tokens_per_task")  # None if split unavailable

if cost and not math.isnan(cost) and cost > 0:
    agg["intelligence_per_dollar"] = cap / cost
else:
    agg["intelligence_per_dollar"] = float("nan")

# Intelligence per token prefers answer-only (visible work) per PRD gotcha:
# "Reasoning models eat output budget invisibly... intelligence/token uses
#  answer tokens only, or both with a labeled split."
if toks_answer is not None and toks_answer > 0:
    agg["intelligence_per_token"] = cap / toks_answer
    agg["intelligence_per_token_total"] = cap / toks_total
elif toks_total > 0:
    agg["intelligence_per_token"] = cap / toks_total
    agg["intelligence_per_token_total"] = cap / toks_total
else:
    agg["intelligence_per_token"] = float("nan")
    agg["intelligence_per_token_total"] = float("nan")

agg["cost_per_suite"] = sum(per_task_costs)
agg["tokens_per_suite"] = sum(per_task_tokens)
agg["answer_tokens_per_suite"] = (
    sum(a for a in per_task_answer_tokens if a is not None) or None
)
agg["time_per_suite"] = sum(per_task_times)
```

**Rendering in `format_summary()`:**

Add a second line per model entry (or a separate section below the ranking):
```
  #1  kimi-k2.7-code        81.3%  ●●●●●●●●○○  cost=$0.03 tok=18,420 time=642s int/$=2,710 int/tok=0.0044
```

**Rendering in `format_pillar_table()`:**

Add columns to the table. The sub-measures go after the ratio columns.

### 0E — Test updates

**Modified files:**
- `tests/test_compare.py` — new tests for each SC
- `tests/test_rescore.py` — new file

**New tests:**
- `test_default_compare_has_capability_column_is_pass1_mean` (Phase 0 setup for SC1; verification under the CI-aware comparison is gated in `tests/test_compare.py::test_capability_with_ci_renders_correctly` which lands with SC6/SC7 in Phase 1 — see 1B rendering rules)
- `test_default_compare_has_no_weighted_score` (SC2)
- `test_efficiency_columns_raw_units` (SC3)
- `test_submeasures_match_manual` (SC8)
- `test_rescore_zero_api_calls` (SC11)
- `test_rescore_handles_corrupt_logs` (SC12)

**Existing tests:** Must remain green. The rescore and compare changes are additive; `--legacy-weighted` preserves old behavior.

---

## Phase 1 — Statistical Honesty

**Goal:** Bootstrap CIs on capability mean; pairwise tie badges.

**Delivers:** SC 1, 6, 7.

### 1A — Bootstrap CI computation

**New file:** `bench_cli/compare/bootstrap.py`

```python
def bootstrap_ci(
    per_task_scores: list[float],
    *,
    n_resample: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
    min_n: int = MIN_FULL_EVAL_TASKS,  # = 34; gate on full-eval only
) -> tuple[float, float] | None:
    """Bootstrap 95% CI on the mean of per-task correctness scores.

    Algorithm:
    1. If len(per_task_scores) < min_n: return None. Caller renders
       'insufficient data'. Per PRD Edge Cases: CI on partial-eval models
       is misleading; only >=34-task models get a CI.
    2. Resample per_task_scores with replacement, n_resample times
    3. Compute mean of each resample
    4. Return (2.5th percentile, 97.5th percentile) of resampled means

    Args:
        per_task_scores: list of per-task correctness values (0-1)
        n_resample: number of bootstrap iterations (default 1000)
        confidence: CI level (default 0.95)
        seed: random seed for reproducibility
        min_n: minimum task count to compute CI (default 34); below this returns None

    Returns:
        (ci_low, ci_high) tuple, OR None if per_task_scores has < min_n items.
    ```
</subject

**Implementation:** Pure Python + `random.Random(seed)`. No numpy dependency. The function is self-contained — takes a flat list of per-task scores, returns bounds.

**Integration in `compare/core.py`:**

```python
@dataclass
class ModelAgg:
    """Aggregated stats for one model."""
    n: int
    correct_mean: float
    ci_low: float | None    # None when n < MIN_FULL_EVAL_TASKS
    ci_high: float | None   # None when n < MIN_FULL_EVAL_TASKS
    cost_per_task: float
    tokens_per_task: float      # total (reasoning + answer)
    answer_tokens_per_task: float | None   # visible-only; None if split unavailable
    time_per_task: float
    # ... other fields
```

In `_aggregate_model_pillars()`, after computing `correct_mean`:

```python
per_task = [data.matrix[t][model].correctness for t in data.tasks
            if model in data.matrix[t] and not math.isnan(data.matrix[t][model].correctness)]
ci = bootstrap_ci(per_task, min_n=MIN_FULL_EVAL_TASKS)
ci_low, ci_high = (None, None) if ci is None else ci
```

### 1B — CI display in compare output

**Modified files:**
- `bench_cli/compare/core.py`

**`format_summary()` changes:**

```
  #1  kimi-k2.7-code        81.3% [74.2, 87.8]  ●●●●●●●●○○
  #2  deepseek-v4-pro       80.8% [73.1, 87.5]  ≈  (tied with #1)
  #3  minimax-m3            80.2% [72.9, 86.9]  ≈  (tied with #1)
  ...
```

**Column format:** `capability [CI_low, CI_high]` — square brackets, one decimal place.

**Partial-eval rendering:** models with `ci_low is None` render as
`81.3% [insufficient data]` instead of `81.3% [n/a, n/a]`. They are
still ranked but their tie badge is suppressed (no pairwise comparison
without CIs).

**Label distinct from IRT credible interval:** capability CI here is a
**performance CI** (bootstrap on pass@1 mean, resamples tasks). IRT
credible interval is an **ability CI** (θ posterior, from `bench irt fit`).
Different commands, different concepts; F3 mitigation is satisfied by
explicit labels `perf CI` vs `ability CI` in their respective outputs.

### 1C — Pairwise tie detection

**New file:** `bench_cli/compare/ties.py`

```python
def detect_ties(
    model_cis: dict[str, tuple[float, float]],
) -> list[set[str]]:
    """Pairwise CI overlap detection.

    Two models are tied if their CIs overlap (share any point).
    Returns list of tie groups (sets of model names).

    NOT transitive: if A ties B and B ties C, A and C are NOT
    automatically tied. Each pair is checked independently.

    This means a model can appear in multiple tie groups.
    """
```

**Rendering:** Models in the same tie group as the model above them get a `≈` badge instead of a rank increment. The rank number reflects capability ordering but the badge signals no statistical separation.

```python
def _assign_ranks_with_ties(
    sorted_models: list[tuple[str, float, tuple[float, float]]],
) -> list[tuple[int, str, str]]:
    """Assign display ranks with tie badges.

    Returns list of (rank, model, badge) where badge is:
    - "" for distinct models
    - "≈" for models tied with the model above
    """
```

**Test:**
- `test_tie_badge_on_overlapping_ci` (SC7) — synthetic overlapping CIs, assert badge renders
- `test_bootstrap_ci_reproducible` (SC6) — fixed seed, assert CI bounds match across runs
- `test_pairwise_not_transitive` — A ties B, B ties C, but A does NOT tie C

### 1D — CLI flag

**`compare/cli.py`:**

```python
@click.option("--no-ci", is_flag=True, default=False,
              help="Suppress bootstrap CI computation (faster).")
```

Default is CIs ON. `--no-ci` skips the bootstrap for faster iteration.

---

## Phase 2 — Harder Tasks (B2)

**Goal:** Source ~10 new tasks that discriminate in the cluster ability band.

**Delivers:** Feeds Phase 3; partial SC 10 (full verification needs IRT).

> ⚠️ **CRITICAL EXECUTION NOTE — `--no-resume` for ALL B2 runs.**
>
> The new tasks have no existing logs. `bench run`'s default resume
> behavior skips any (model, task) pair with a `status='success'` log;
> **this is the most likely silent failure mode for B2.** Every eval
> for every model in Phase 2 must include `--no-resume`. Per-model
> command template:
>
> ```bash
> bench run --model openai/<alias> --no-resume
> ```
>
> Verification step at the end of Phase 2: count new `.eval` files
> written (`*.eval` matching the new task names) and assert
> `count == N_models × N_new_tasks`. If short, the resume-skip
> hypothesis is the first thing to check.

### 2A — Task sourcing strategy

**Decision:** Port first (SWE-bench-Verified / MMLU-Pro coding subset), author only if porting doesn't yield clean fits.

**Porting pipeline:**

1. **Select candidates** from SWE-bench-Verified: pick tasks where the gold patch modifies 2+ files and the problem description maps to one of bench's 4 pillars.
2. **Decompose** into bench format: `task.py` (Inspect `@task`), `dataset.json` (samples with input/target/id), `verify.sh` or `judge.md`.
3. **Craft distractors** that are surface-correct but fail edge cases.
4. **Pilot test** on strong baseline (kimi) and weak baseline (gemma-local) to confirm separation.
5. **Verify** gold answer + distractor realism with blind expert check (you).

**New files per task:**

```
tasks/<pillar>/<task-name>/
├── task.py          # @task decorator, dataset loading
├── dataset.json     # samples: [{input, target, id}, ...]
├── verify.sh        # deterministic scorer
└── fixtures/        # optional test fixtures
```

**Target:** 10 tasks, distributed across pillars (2-3 per pillar). Each task must have `verify.sh` (deterministic, no judge variance for calibration).

### 2B — Task integration

**Modified files:**
- `scorers/task_budgets.py` — add reference_cost_usd for new tasks
- `bench_cli/run/core.py` — no change needed (task discovery is automatic from `tasks/` subdirs)

**Reference calibration:** Run each new task on minimax-m3 first to get `reference_cost_usd`. Add to `task_budgets.py`.

### 2C — Full-eval run

```bash
bench run --model openai/<alias> --no-resume   # for each of 16 models
```

`--no-resume` is mandatory — new tasks have no existing logs.

**Output:** 16 × 10 = 100 new .eval logs. Total suite grows from 34 to ~44 tasks.

---

## Phase 3 — IRT Engine

**Goal:** Bayesian hierarchical 2PL per pillar; item analysis; ability estimates.

**Delivers:** SC 4, 5; completes SC 10.

### 3A — Module structure

**New files:**

```
bench_cli/irt/
├── __init__.py      # lazy import guard
├── fit.py           # PyMC model spec + fitting
├── items.py         # item analysis (difficulty, discrimination)
├── types.py         # dataclasses for IRT results
├── cli.py           # click commands
└── utils.py         # outcome matrix construction
```

**Lazy import pattern:**

```python
# bench_cli/irt/__init__.py
def _check_pymc():
    try:
        import pymc
    except ImportError:
        raise ImportError(
            "PyMC is required for IRT analysis. Install with: pip install pymc"
        )
```

### 3B — Outcome matrix

**`bench_cli/irt/utils.py`:**

```python
def build_outcome_matrix(
    log_dir: str,
    *,
    filter_monikers: bool = True,
) -> OutcomeMatrix:
    """Build the binary outcome matrix for IRT fitting.

    Rows = models (respondents), columns = tasks (items).
    Values = 1 (pass) or 0 (fail) per sample, aggregated to
    per-(model, task) pass rate.

    Steps:
    1. Read all .eval logs
    2. Reconcile recorded identities (task 4940c0c8 matching)
    3. Filter moniker aliases if filter_monikers=True
    4. For each (model, task): compute pass@1 from samples
    5. Return dense matrix + model/task labels

    Recorded identity reconciliation: models with different recorded
    names that resolve to the same backing model (via MODEL_ALIAS_MAP
    or litellm config) are merged. The merge uses the most-common
    recorded name as canonical.
    """

@dataclass
class OutcomeMatrix:
    matrix: np.ndarray       # shape (n_models, n_tasks), float 0-1
    models: list[str]        # model names (row labels)
    tasks: list[str]         # task names (column labels)
    pillars: dict[str, str]  # task_name -> pillar (analysis/competence/execution/universal)
```

**Note:** Uses numpy for the outcome matrix only. **Verified**: at
the time of writing, `pip show numpy` in the .venv returns 2.4.4
(transitive via inspect-ai 0.3.245). The IRT module imports numpy lazily
alongside pymc so the import is gated by the same `pip install pymc`
install step, keeping it part of the optional `[irt]` extra regardless
of whether it is technically transitively pulled.

### 3C — 2PL model spec

**`bench_cli/irt/fit.py`:**

```python
def fit_2pl(
    outcome: OutcomeMatrix,
    *,
    pillar: str | None = None,
    n_samples: int = 2000,
    n_chains: int = 2,
    seed: int = 42,
) -> IRTFit:
    """Fit a Bayesian 2PL IRT model.

    If pillar is None, fit on all tasks (general θ).
    If pillar is specified, filter to tasks in that pillar and fit per-pillar.

    Model spec (PyMC):
        # Priors
        theta ~ Normal(0, 1)        # ability per model
        a ~ LogNormal(0, 0.5)       # discrimination per task
        b ~ Normal(0, 2)            # difficulty per task

        # Likelihood
        p_ij = sigmoid(a_j * (theta_i - b_j))
        y_ij ~ Bernoulli(p_ij)

    Returns:
        IRTFit with posterior samples + summary stats
    """

@dataclass
class IRTFit:
    theta: np.ndarray         # shape (n_models,) — posterior mean ability
    theta_ci: np.ndarray      # shape (n_models, 2) — 95% credible interval
    a: np.ndarray             # shape (n_tasks,) — discrimination
    b: np.ndarray             # shape (n_tasks,) — difficulty
    models: list[str]
    tasks: list[str]
    pillar: str | None
    converged: bool           # False if Rhat > 1.1 for any param
    n_divergences: int
```

**Per-pillar fitting:**

```python
def fit_all_pillars(
    outcome: OutcomeMatrix,
    **kwargs,
) -> dict[str, IRTFit]:
    """Fit 2PL per pillar. Falls back to general θ if any pillar has < 8 tasks."""
    fits = {}
    for pillar in ["analysis", "competence", "execution", "universal"]:
        pillar_tasks = [t for t in outcome.tasks if outcome.pillars.get(t) == pillar]
        if len(pillar_tasks) < 8:
            # Too few items for stable IRT — skip this pillar
            fits[pillar] = None
            continue
        fits[pillar] = fit_2pl(outcome, pillar=pillar, **kwargs)
    return fits
```

**Convergence fallback:** If any pillar fit has `converged=False`, fall back to fitting a single general θ on all tasks. Document this in the output.

### 3D — Item analysis

**`bench_cli/irt/items.py`:**

```python
@dataclass
class ItemAnalysis:
    task: str
    pillar: str
    a: float          # discrimination (posterior mean)
    a_ci: tuple[float, float]
    b: float          # difficulty (posterior mean)
    b_ci: tuple[float, float]
    band: str         # "high", "medium", "low", "cull"

def classify_discrimination(
    a: float,
    *,
    high_threshold: float = 1.0,
    medium_threshold: float = 0.5,
    low_threshold: float = 0.2,
) -> str:
    """Classify discrimination parameter.

    Initial thresholds (literature defaults, not PRD-anchored — validate
    against B2 calibration data in Phase 2/3 before locking):
    - a >= high_threshold:    high discrimination
    - med <= a < high:        medium
    - low <= a < med:         low
    - a < low_threshold:      cull (no signal)

    PRD open question: thresholds should be calibrated on the first batch
    of B2 IRT fits and may be tightened. Until then, defaults are
    literature-typical; Phase 3 implementation logs calibration data so a
    later minor revision can update defaults from the empirical
    distribution of a.
    """
    if a >= high_threshold:
        return "high"
    elif a >= medium_threshold:
        return "medium"
    elif a >= low_threshold:
        return "low"
    return "cull"

def item_analysis(fit: IRTFit) -> list[ItemAnalysis]:
    """Extract per-task item parameters from a fitted IRT model."""
```

**Target band for B2 tasks:**

```python
def in_discriminating_band(b: float, mean_theta: float, tolerance: float = 0.5) -> bool:
    """Check if task difficulty is in the discriminating band.

    The band is mean_theta ± tolerance (in SD units).
    Tasks in this band separate models that cluster near the mean.
    """
    return abs(b - mean_theta) <= tolerance
```

### 3E — CLI commands

**`bench_cli/irt/cli.py`:**

```python
@click.group("irt")
def irt_group():
    """IRT discrimination analysis (requires PyMC)."""
    pass

@irt_group.command("fit")
@click.option("--log-dir", default="logs")
@click.option("--pillar", default=None, help="Fit single pillar (default: all)")
@click.option("--n-samples", default=2000)
@click.option("--json", "as_json", is_flag=True)
def irt_fit(log_dir, pillar, n_samples, as_json):
    """Fit Bayesian 2PL IRT model on eval logs.

    Output: posterior ability estimates θ + 95% CI per model, per pillar.
    """
    # 1. build_outcome_matrix
    # 2. fit_2pl or fit_all_pillars
    # 3. render table or JSON

@irt_group.command("item-analysis")
@click.option("--log-dir", default="logs")
@click.option("--json", "as_json", is_flag=True)
def irt_item_analysis(log_dir, as_json):
    """Report per-task difficulty and discrimination parameters.

    Output: table with a, b params + discrimination band label.
    """
    # 1. build_outcome_matrix
    # 2. fit_2pl (general)
    # 3. item_analysis
    # 4. render table
```

**Register in `main.py`:**

```python
from bench_cli.irt.cli import irt_group
cli.add_command(irt_group)
```

### 3F — Tests

**New file:** `tests/test_irt.py`

- `test_2pl_recovers_synthetic_params` (SC4) — generate synthetic 2PL data with known a,b,θ; fit; assert recovery within tolerance
- `test_item_analysis_labels_cull` (SC5) — feed low-a items, assert "cull" label
- `test_outcome_matrix_filters_monikers` — moniker aliases excluded
- `test_outcome_matrix_reconciles_identities` — duplicate recorded names merged
- `test_convergence_fallback` — synthetic data that causes non-convergence triggers general-θ fallback
- `test_pymc_lazy_import` (SC13) — `pip uninstall pymc`, assert `bench irt fit` gives clear error, `bench compare` works fine

**New file:** `tests/test_irt_isolation.py`

- `test_core_without_pymc` (SC13) — run non-IRT test suite without PyMC installed

---

## Phase 4 — Preset Router

**Goal:** `bench recommend-preset --preset {best,cheap-fast,balanced}` (alias `bench rp`) with deterministic per-use-case rankings.

**Delivers:** SC 9.

### 4A — Preset definitions

**New files:**

```
bench_cli/recommend/
├── __init__.py
├── presets.py       # preset logic
└── pareto.py        # Pareto front computation (reuse from discriminative/)
```

**`bench_cli/recommend/presets.py`:**

```python
@dataclass
class RecommendResult:
    preset: str
    models: list[RankedModel]

@dataclass
class RankedModel:
    model: str
    rank: int
    capability: float        # θ or pass@1
    ci: tuple[float, float]
    cost_per_task: float
    time_per_task: float
    on_pareto: bool          # True if Pareto-optimal (balanced preset only)
    dominated_by: list[str]  # models dominating this one (balanced only)

def recommend_preset(
    data: CompareData,
    preset: str,
    *,
    use_irt: bool = True,  # use θ if IRT fit available, else pass@1
) -> RecommendResult:
    """Rank models by preset logic.

    Presets (locked in PRD):

    best:
      Rank by capability θ (highest first). Ignore efficiency.
      If IRT not available, rank by pass@1 mean.

    cheap-fast:
      1. Filter to models with cost/task < cohort median
      2. Among filtered: rank by time/task ascending
      3. Break ties by capability θ descending

    balanced:
      1. Compute Pareto front across (capability, -cost, -time)
         - A dominates B if A >= B on all axes and > on at least one
      2. Rank Pareto-optimal models by capability θ
      3. List dominated models below, ranked by capability θ
    """
```

### 4B — Pareto computation

**New file:** `bench_cli/recommend/pareto.py`

Adapt from existing `bench_cli/discriminative/pareto.py`:

```python
def compute_pareto_front(
    models: list[str],
    capability: list[float],
    cost: list[float],
    time: list[float],
) -> tuple[list[int], list[list[int]]]:
    """Compute Pareto front across (capability, -cost, -time).

    Returns:
        pareto_indices: indices of Pareto-optimal models
        dominated_by: for each model, list of indices that dominate it
    """
```

The existing `discriminative/pareto.py` operates on `SubjectProfile`
objects (richer shape: cluster_scores, free/paid carve-out, dominance
metadata). The new `recommend/pareto.py` operates on flat
arrays-of-scalars — simpler, no SubjectProfile coupling. **Not
duplication:** different input shape, different caller. If the
discriminative module ever needs flat-array pareto, lift it into a
shared `bench_cli/_pareto.py`; for now two implementations with
distinct shapes is YAGNI-cleaner than premature shared abstraction.

### 4C — CLI

**Decision (locked):** NEW top-level command `bench recommend-preset`
(or short alias `bench rp`). Rationale:

- Existing `bench recommend --model <alias>` in
  `bench_cli/discriminative/cli.py:17` is a **single-subject discriminative
  profile** operation (different beast — inspects one model's task-by-task
  behavior).
- New `bench recommend-preset --preset best` is a **model ranking**
  operation (operates over the whole cohort).
- Sharing the command name would force a flag-collision pattern
  (`--preset` vs `--model`) with mutual exclusion, which is brittle and
  hides the conceptual difference.
- Naming `recommend-preset` (or alias `rp`) signals the distinct
  operation without migrating the legacy `recommend` users.

**New file:** `bench_cli/recommend/cli.py` — the top-level command. The
existing `bench_cli/discriminative/cli.py::recommend` is untouched.

```python
@click.command("recommend-preset")
@click.option("--preset", type=click.Choice(["best", "cheap-fast", "balanced"]),
              required=True, help="Recommendation preset.")
@click.option("--log-dir", default="logs")
@click.option("--use-irt/--no-use-irt", default=True,
              help="Use θ from `bench irt fit` results if available; else pass@1.")
@click.option("--json", "as_json", is_flag=True)
def recommend_preset(preset, log_dir, use_irt, as_json):
    """Rank models by use-case preset.

    Presets:
      best:       highest capability (θ or pass@1)
      cheap-fast: below-median cost, fastest first
      balanced:   Pareto-optimal across capability/cost/time
    """
```

**Register in `bench_cli/main.py`:**

```python
from bench_cli.recommend.cli import recommend_preset
cli.add_command(recommend_preset)
```

The existing `recommend` (from `bench_cli/discriminative/cli.py`) stays
exactly as-is for backwards compatibility with users of single-subject
profiles. No migration.

### 4D — IRT integration

When IRT fits are available (Phase 3 shipped), the preset router uses `θ` as the capability measure. When IRT is not available, it falls back to `pass@1` mean.

```python
def _resolve_capability(data, model, irt_fits=None):
    """Return capability score for a model.

    Priority: IRT θ (if available) > pass@1 mean.
    """
    if irt_fits and model in irt_fits:
        return irt_fits[model].theta
    return data.matrix...correct_mean
```

### 4E — Tests

**New file:** `tests/test_recommend_preset.py` (matches the `bench recommend-preset` command name)

- `test_preset_rankings_deterministic` (SC9) — synthetic cohort, assert each preset's ranking is stable across runs
- `test_best_preset_ranks_by_capability` — highest θ first
- `test_cheap_fast_filters_below_median_cost` — verify cost filter
- `test_cheap_fast_ranks_by_time` — verify time sorting
- `test_balanced_pareto_front` — verify Pareto computation
- `test_balanced_dominated_below` — dominated models listed after Pareto-optimal
- `test_different_presets_different_top3` (H4) — verify preset divergence

---

## Cross-Cutting Concerns

### Dependency isolation

- PyMC is isolated in `bench_cli/irt/`. All lazy imports behind `_check_pymc()`.
- `pip uninstall pymc && .venv/bin/pytest -q` must pass the non-IRT suite.
- `requirements.txt` / `pyproject.toml`: add `pymc` as optional dependency (`[irt]` extra).

### Moniker filtering

Every new module that operates on model data must filter moniker aliases:

```python
from bench_cli.results.core import is_moniker_alias   # REAL location: bench_cli/results/core.py:49
models = [m for m in all_models if not is_moniker_alias(m)]
# filters: default/thinking/heavy/background/smart-router
```

**Definition of done:** filter at data acquisition (in
`build_outcome_matrix` Phase 3, and the analogous load path in Phase 4's
preset router), not at render time. Single filter point guarantees all
downstream consumers see only concrete models and the cohort is identical
across IRT, preset router, and rendering.

**Test:** unit test feeds a synthetic cohort containing `default` and
`thinking` monikers, asserts they are absent from the returned matrix /
ranking list.

### Recorded identity reconciliation

Phases 3–4 need consistent model identities. Reuse the discriminative module's matching (task 4940c0c8). Centralize into a shared utility:

```python
# bench_cli/identity.py (new)
def reconcile_identities(log_dir: str) -> dict[str, str]:
    """Map recorded model names to canonical identities.

    Returns dict of recorded_name -> canonical_name.
    """
```

### `nan` / `inf` handling

All rendering functions must handle:
- `nan` cost → render as `n/a (unpriced)`, never `nan` or `inf`
- `nan` CI → render as `[n/a, n/a]` for partial-eval models
- `inf` price_ratio → legacy only; new code never produces inf

### `--no-resume` for new tasks

Phase 2's new tasks require `bench run --no-resume` for all 16 models. Document in the Phase 2 implementation plan. The rescore (Phase 0) does NOT require `--no-resume` because it reads existing logs without re-running.

---

## File Inventory

### New files (all phases)

| File | Phase | Purpose |
|------|-------|---------|
| `bench_cli/rescore/__init__.py` | 0 | Package init |
| `bench_cli/rescore/core.py` | 0 | Rescore logic |
| `bench_cli/rescore/cli.py` | 0 | `bench rescore` command |
| `bench_cli/compare/bootstrap.py` | 1 | Bootstrap CI computation |
| `bench_cli/compare/ties.py` | 1 | Pairwise tie detection |
| `bench_cli/identity.py` | 3 | Recorded identity reconciliation |
| `bench_cli/irt/__init__.py` | 3 | Package init + PyMC guard |
| `bench_cli/irt/fit.py` | 3 | 2PL model spec + fitting |
| `bench_cli/irt/items.py` | 3 | Item analysis |
| `bench_cli/irt/types.py` | 3 | IRT dataclasses |
| `bench_cli/irt/utils.py` | 3 | Outcome matrix construction |
| `bench_cli/irt/cli.py` | 3 | `bench irt` commands |
| `bench_cli/recommend/__init__.py` | 4 | Package init |
| `bench_cli/recommend/presets.py` | 4 | Preset router logic |
| `bench_cli/recommend/pareto.py` | 4 | Pareto computation |
| `tests/test_rescore.py` | 0 | Rescore tests |
| `tests/test_compare.py` | 0, 1 | Bootstrap CI + tie + capability tests (PRD Test Plan locked location) |
| `tests/test_irt.py` | 3 | IRT tests |
| `tests/test_irt_isolation.py` | 3 | PyMC isolation tests |
| `tests/test_recommend_preset.py` | 4 | Preset router tests |

**Locked test locations:** Per the PRD's Test Plan section (source of
truth), tests for SC6 (`test_bootstrap_ci_reproducible`) and SC7
(`test_tie_badge_on_overlapping_ci`) MUST live in `tests/test_compare.py`,
NOT a separate `test_compare_bootstrap.py`. All compare-rendering tests
land in one file for reviewer navigation.
| `tasks/<pillar>/<new-task>/` | 2 | ~10 new tasks |

### Modified files (all phases)

| File | Phase | Changes |
|------|-------|---------|
| `bench_cli/compare/core.py` | 0, 1 | Remove weighted default; add efficiency columns, sub-measures, CI, tie badges |
| `bench_cli/compare/cli.py` | 0, 1 | Add `--legacy-weighted`, `--no-ci` flags |
| `bench_cli/main.py` | 0, 3, 4 | Remove `score_cmd`; add `irt_group`; add `recommend_preset` (existing `recommend` left untouched) |
| `bench_cli/score.py` | 0 | DELETE |
| `scorers/task_budgets.py` | 2 | Add reference_cost_usd for new tasks |
| `pyproject.toml` | 3 | Add `[irt]` optional dependency |

---

## Phase Dependencies

```
Phase 0 ─── Phase 1 ─── Phase 2 ─── Phase 3 ─── Phase 4
(rescore)    (CIs)       (tasks)     (IRT)        (router)
                                                 
Phase 0 is prerequisite for everything (rescore unblocks new columns).
Phase 1 depends on Phase 0 (CIs need the new column structure).
Phase 2 is independent of 1 (can run in parallel).
Phase 3 depends on Phase 2 (IRT needs enough tasks to discriminate).
Phase 4 depends on Phase 3 (router uses θ when available; works without it too).
```

**Critical path:** 0 → 1 (ship fast, days). 2 is the long pole (person-weeks). 3 → 4 are quick once 2 lands.

**Parallelism opportunity:** Phase 2 (task authoring) can start immediately after Phase 0 ships. Phase 1 and Phase 2 are independent.

---

## Verification Commands

```bash
# Phase 0
bench rescore --dry-run
bench compare --legacy-weighted   # backward compat
bench compare                      # new default (capability-only)
bench compare -v                   # with efficiency columns + sub-measures

# Phase 1
bench compare                      # CIs + tie badges in default output
bench compare --no-ci              # fast mode

# Phase 2
bench run --model openai/<alias> --no-resume   # new tasks
bench compare                      # now with ~44 tasks

# Phase 3
bench irt fit                      # per-pillar θ + CI
bench irt item-analysis            # task difficulty/discrimination
bench irt fit --pillar analysis    # single pillar

# Phase 4
bench recommend-preset --preset best
bench recommend-preset --preset cheap-fast
bench recommend-preset --preset balanced
# alias also available:
bench rp --preset balanced

# Regression
.venv/bin/pytest -q                # all tests green
pip uninstall pymc && .venv/bin/pytest -q  # IRT isolation
```

---

## Success Criteria Traceability

| SC | Phase | Verification |
|----|-------|-------------|
| 1 | 0+1 | `bench compare` shows capability column (Phase 0); CI-bearing rendering verified in Phase 1 tests `tests/test_compare.py::test_capability_with_ci_renders_correctly` |
| 2 | 0 | `bench compare` default has no weighted score; `--legacy-weighted` restores it |
| 3 | 0 | `bench compare` shows cost/task, tok/task, time/task as raw columns |
| 4 | 3 | `bench irt fit` produces θ + CI per model per pillar |
| 5 | 3 | `bench irt item-analysis` outputs a, b + discrimination band |
| 6 | 1 | `bench compare` shows capability [CI] column |
| 7 | 1 | Overlapping CIs → "≈" tie badge |
| 8 | 0 | 5 AA sub-measures appear as columns |
| 9 | 4 | `bench recommend-preset --preset <name>` (alias `bench rp`) produces deterministic ranking |
| 10 | 2+3 | ≥8 new tasks classified high-discrimination by IRT |
| 11 | 0 | `bench rescore` makes zero API calls |
| 12 | 0 | `bench rescore` reports skips for corrupt logs |
| 13 | 3 | Core works without PyMC installed |
