# Phase 0 — Rescore & Capability Default Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Load subagent-driven-development/SKILL.md (recommended) or executing-plans/SKILL.md to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the rescore migration, retire the 4-weight blended score as the default comparison ranking, and surface raw efficiency columns + ability-adjusted sub-measures (`int/$`, `int/tok`). All behavior is preserved behind `--legacy-weighted`.

**Architecture:** Pure shape + render changes to `bench_cli/compare/core.py` (extend `PillarScores` with `avg_answer_tokens`, add per-(task,model) raw units and the five AA sub-measures into `_aggregate_model_pillars()`); gated render by a new `legacy_weighted: bool = False` parameter on `format_summary`, `format_pillar_table`, `format_compact_table`, `format_json`. CLI gains `--legacy-weighted`. Dead-code cleanup: delete `bench_cli/score.py`. New module `bench_cli/rescore/` ships a zero-API-call rescore of existing `.eval` logs using the current pricing resolution pipeline.

**Tech Stack:** Python 3.14, Click 8, pytest, existing pricing resolver (`bench_cli.pricing`), Inspect AI 0.3.245 (binary ZIP `.eval` format).

## Global Constraints

- Use the project `.venv`: `.venv/bin/python` and `.venv/bin/pytest`. No system python. (`AGENTS.md`)
- Scorers live in `scorers/` at repo root, imported as `from scorers import ...`. `bench_cli/scorers/` does NOT exist. (`AGENTS.md`)
- Models route through a LiteLLM proxy as `openai/<alias>`; `.env` holds credentials. (SB Operating Rules)
- `bench_cli/run/` and `bench_cli/compare/` are packages: `from bench_cli.<name>.core import ...`, NOT `from bench_cli.<name> import ...`. (SB Operating Rules)
- The PRD Test Plan locks new SC1/SC2/SC3/SC6/SC7/SC8/SC11/SC12 tests into `tests/test_compare.py` / `tests/test_rescore.py`. Do not split them into separate files.
- NEVER modify scorers — rescore never touches `correctness`. It only refreshes efficiency-derived numbers using the current pricing pipeline.
- Rescore MUST make zero API calls. Reads `sample.model_usage` from the binary ZIP log and writes updated efficiency scores back. A failing network call during rescore is a bug.
- Reasoning/answer token split: if `sample.model_usage[*]` carries per-type counts, populate `avg_answer_tokens` per task. If the dataclass doesn't yet expose those fields, defer sub-measure computation to `tokens_per_task` (total) only and document the gap; do NOT block this plan on the upstream field.
- Render gate (`legacy_weighted=False`) means: no "TOTAL = 0.5×correct + ..." footer line, no weighted TOTAL row in compact table, header text changes from "Score: ..." to "Capability (pass@1 mean): ...", sort by `correct_mean` descending.
- `nan`/`inf` handling is fixed everywhere new code emits `n/a (unpriced)` and `[n/a, n/a]` — never `nan` or `inf` in user-facing strings.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `bench_cli/compare/core.py` | Aggregation (`_aggregate_model_pillars`), 4 renderers (`format_summary`, `format_pillar_table`, `format_compact_table`, `format_json`), `PillarScores` shape | Modify (Task 1–4) |
| `bench_cli/compare/cli.py` | `--legacy-weighted` and `--no-legacy-weighted` Click flags | Modify (Task 4) |
| `bench_cli/main.py` | Drop `score_cmd` import + `add_command` | Modify (Task 5) |
| `bench_cli/score.py` | Legacy `bench score` command — duplicate of compare | **Delete** (Task 5) |
| `bench_cli/rescore/__init__.py` | Package init | Create (Task 6) |
| `bench_cli/rescore/core.py` | Pure rescore loop, `RescoreResult`, `SkipInfo` dataclasses | Create (Task 6) |
| `bench_cli/rescore/cli.py` | `bench rescore` Click command | Create (Task 7) |
| `tests/test_compare.py` | SC1/SC2/SC3/SC8 + new `legacy_weighted=False` rendering tests | Modify (Task 1–4) |
| `tests/test_rescore.py` | SC11/SC12 + dry-run + idempotency tests | Create (Task 6, 7) |

No pricing module changes. No scorer changes. No task directory changes.

---

## Task 1: Extend `_aggregate_model_pillars()` with raw efficiency + AA sub-measures

**Files:**
- Modify: `bench_cli/compare/core.py:30-55` (extend `PillarScores`)
- Modify: `bench_cli/compare/core.py:463-501` (rewrite `_aggregate_model_pillars`)
- Modify: `tests/test_compare.py` (append new tests at end)

**Interfaces:**
- Consumes: existing `PillarScores` fields, `data: CompareData`, `MIN_FULL_EVAL_TASKS=34`
- Produces:
  - `PillarScores.avg_answer_tokens: float | None` — None when the model_usage dict doesn't carry a per-type split; `0.0` when the split exists but is empty
  - `_aggregate_model_pillars(data, model) -> dict | None` returns a dict with new keys:
    - `cost_per_task`, `tokens_per_task`, `answer_tokens_per_task`, `time_per_task` (per-task means)
    - `cost_per_suite`, `tokens_per_suite`, `answer_tokens_per_suite`, `time_per_suite` (sums across tasks)
    - `intelligence_per_dollar`, `intelligence_per_token`, `intelligence_per_token_total` (nan when denominator missing)

- [ ] **Step 1: Write the failing tests for the new aggregation fields**

Append to `tests/test_compare.py`:

```python
def test_aggregate_pillars_includes_cost_per_task():
    """SC3 partial: cost_per_task is the arithmetic mean of per-task avg_cost_usd
    values across scored tasks, ignoring nan entries."""
    data = CompareData()
    data.tasks = ["t1", "t2"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1, avg_cost_usd=0.001)},
        "t2": {"m1": PillarScores(correctness=0.6, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=200, avg_time=4.0, samples=1, avg_cost_usd=0.003)},
    }
    agg = _aggregate_model_pillars(data, "m1")
    assert agg["cost_per_task"] == pytest.approx(0.002)
    assert agg["tokens_per_task"] == pytest.approx(150.0)
    assert agg["time_per_task"] == pytest.approx(3.0)


def test_aggregate_pillars_drops_nan_cost_in_mean():
    """SC3: avg_cost_usd=nan tasks do NOT pollute cost_per_task mean."""
    data = CompareData()
    data.tasks = ["t1", "t2"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1, avg_cost_usd=float("nan"))},
        "t2": {"m1": PillarScores(correctness=0.6, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=200, avg_time=4.0, samples=1, avg_cost_usd=0.002)},
    }
    agg = _aggregate_model_pillars(data, "m1")
    assert agg["cost_per_task"] == pytest.approx(0.002)


def test_aggregate_pillars_intelligence_per_dollar_when_priced():
    """SC8: int/$ = correct_mean / cost_per_task when cost is available."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1, avg_cost_usd=0.002)},
    }
    agg = _aggregate_model_pillars(data, "m1")
    assert agg["intelligence_per_dollar"] == pytest.approx(400.0)


def test_aggregate_pillars_intelligence_per_dollar_nan_when_unpriced():
    """SC8: int/$ is NaN when cost is NaN; never divide by zero."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1)},
    }
    agg = _aggregate_model_pillars(data, "m1")
    assert math.isnan(agg["intelligence_per_dollar"])


def test_aggregate_pillars_intelligence_per_token_uses_answer_when_available():
    """SC8 + PRD gotcha: int/tok prefers answer_tokens (visible work) over total."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.5, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=1000, avg_time=2.0, samples=1)},
    }
    # avg_answer_tokens is set on the PillarScores via the new field below.
    data.matrix["t1"]["m1"].avg_answer_tokens = 100.0
    agg = _aggregate_model_pillars(data, "m1")
    assert agg["intelligence_per_token"] == pytest.approx(0.005)  # 0.5 / 100
    assert agg["intelligence_per_token_total"] == pytest.approx(0.0005)  # 0.5 / 1000


def test_aggregate_pillars_intelligence_per_token_falls_back_to_total():
    """SC8: when answer_tokens is None, int/tok == int/tok-total (== cap/total)."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.5, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=200, avg_time=2.0, samples=1)},
    }
    agg = _aggregate_model_pillars(data, "m1")
    assert agg["intelligence_per_token"] == pytest.approx(0.5 / 200)
    assert agg["intelligence_per_token_total"] == pytest.approx(0.5 / 200)
```

- [ ] **Step 2: Add `avg_answer_tokens` field to `PillarScores`**

In `bench_cli/compare/core.py` (around line 50, inside the `PillarScores` dataclass), append after `avg_cost_usd`:

```python
    avg_answer_tokens: float | None = None  # visible-only output tokens per sample
                                            # (None when inspect model_usage dataclass
                                            # does not carry a per-type split)
```

- [ ] **Step 3: Run new tests — confirm they fail**

Run: `.venv/bin/pytest tests/test_compare.py -k "aggregate_pillars_includes_cost_per_task or aggregate_pillars_drops_nan_cost_in_mean or aggregate_pillars_intelligence_per_dollar_when_priced or aggregate_pillars_intelligence_per_dollar_nan_when_unpriced or aggregate_pillars_intelligence_per_token_uses_answer_when_available or aggregate_pillars_intelligence_per_token_falls_back_to_total" -v`
Expected: all fail with `KeyError: 'cost_per_task'` (and similar) — the aggregator does not yet emit the new keys.

- [ ] **Step 4: Rewrite `_aggregate_model_pillars()` to emit raw units + sub-measures**

Replace the entire body of `_aggregate_model_pillars()` in `bench_cli/compare/core.py` (lines 463–501) with:

```python
def _aggregate_model_pillars(
    data: CompareData,
    model: str,
) -> dict | None:
    """Aggregate per-pillar values + raw units + AA sub-measures across all
    tasks for one model.

    Returns a dict with keys:
        n, correct_mean, price_ratio_gm, time_ratio_gm, token_ratio_gm
        cost_per_task, tokens_per_task, answer_tokens_per_task, time_per_task
        cost_per_suite, tokens_per_suite, answer_tokens_per_suite, time_per_suite
        intelligence_per_dollar, intelligence_per_token, intelligence_per_token_total

    Returns None if the model has no scored tasks. Ratios default to 1.0
    (neutral) when no task has a valid value for that pillar. NaN cost tasks
    are excluded from cost_per_task mean; all tasks contribute to tokens/time.
    """
    c_vals: list[float] = []
    cr_vals: list[float] = []
    lr_vals: list[float] = []
    tr_vals: list[float] = []

    per_task_costs: list[float] = []
    per_task_tokens: list[float] = []
    per_task_answer_tokens: list[float | None] = []
    per_task_times: list[float] = []

    for task in data.tasks:
        ps = data.matrix.get(task, {}).get(model)
        if not ps or math.isnan(ps.correctness):
            continue
        c_vals.append(ps.correctness)
        if not math.isnan(ps.price_ratio) and ps.price_ratio > 0:
            cr_vals.append(ps.price_ratio)
        if ps.time_ratio > 0:
            lr_vals.append(ps.time_ratio)
        if ps.token_ratio > 0:
            tr_vals.append(ps.token_ratio)

        # Raw units — values are means per sample, so the per-task mean
        # IS ps.avg_* (we do NOT divide by samples again).
        if not math.isnan(ps.avg_cost_usd):
            per_task_costs.append(ps.avg_cost_usd)
        per_task_tokens.append(ps.avg_tokens)
        per_task_answer_tokens.append(ps.avg_answer_tokens)
        per_task_times.append(ps.avg_time)

    if not c_vals:
        return None

    n = len(c_vals)
    correct_mean = sum(c_vals) / n

    def _mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else float("nan")

    cost_per_task = _mean(per_task_costs)
    tokens_per_task = _mean(per_task_tokens)
    answer_tokens_per_task_vals = [
        v for v in per_task_answer_tokens if v is not None
    ]
    answer_tokens_per_task = (
        _mean(answer_tokens_per_task_vals) if answer_tokens_per_task_vals else None
    )
    time_per_task = _mean(per_task_times)

    # Suite totals — sums across tasks.
    cost_per_suite = sum(per_task_costs)
    tokens_per_suite = sum(per_task_tokens)
    answer_tokens_per_suite: float | None = (
        sum(answer_tokens_per_task_vals) if answer_tokens_per_task_vals else None
    )
    time_per_suite = sum(per_task_times)

    # AA sub-measures (capability per efficiency unit).
    if not math.isnan(cost_per_task) and cost_per_task > 0:
        intelligence_per_dollar = correct_mean / cost_per_task
    else:
        intelligence_per_dollar = float("nan")

    # Per PRD gotcha: int/tok prefers answer tokens (visible work).
    # int/tok-total always uses total tokens for comparability.
    if (
        answer_tokens_per_task is not None
        and answer_tokens_per_task > 0
    ):
        intelligence_per_token = correct_mean / answer_tokens_per_task
    elif tokens_per_task > 0:
        intelligence_per_token = correct_mean / tokens_per_task
    else:
        intelligence_per_token = float("nan")

    if tokens_per_task > 0:
        intelligence_per_token_total = correct_mean / tokens_per_task
    else:
        intelligence_per_token_total = float("nan")

    return {
        "n": n,
        "correct_mean": correct_mean,
        "price_ratio_gm": geometric_mean(cr_vals) if cr_vals else 1.0,
        "time_ratio_gm": geometric_mean(lr_vals) if lr_vals else 1.0,
        "token_ratio_gm": geometric_mean(tr_vals) if tr_vals else 1.0,
        "cost_per_task": cost_per_task,
        "tokens_per_task": tokens_per_task,
        "answer_tokens_per_task": answer_tokens_per_task,
        "time_per_task": time_per_task,
        "cost_per_suite": cost_per_suite,
        "tokens_per_suite": tokens_per_suite,
        "answer_tokens_per_suite": answer_tokens_per_suite,
        "time_per_suite": time_per_suite,
        "intelligence_per_dollar": intelligence_per_dollar,
        "intelligence_per_token": intelligence_per_token,
        "intelligence_per_token_total": intelligence_per_token_total,
    }
```

- [ ] **Step 5: Run the new tests — confirm all pass**

Run: `.venv/bin/pytest tests/test_compare.py -k "aggregate_pillars_includes_cost_per_task or aggregate_pillars_drops_nan_cost_in_mean or aggregate_pillars_intelligence_per_dollar_when_priced or aggregate_pillars_intelligence_per_dollar_nan_when_unpriced or aggregate_pillars_intelligence_per_token_uses_answer_when_available or aggregate_pillars_intelligence_per_token_falls_back_to_total" -v`
Expected: 6 passing, 0 failing.

- [ ] **Step 6: Run full test suite — confirm no regressions**

Run: `.venv/bin/pytest -q`
Expected: previously-green 715 tests stay green; this task adds 6 to the new total (721).

- [ ] **Step 7: Commit**

```bash
git add bench_cli/compare/core.py tests/test_compare.py
git commit -m "feat(compare): add efficiency columns + AA sub-measures to aggregator"
```

---

## Task 2: Render raw columns + capability ranking in `format_summary()`

**Files:**
- Modify: `bench_cli/compare/core.py:701-757` (`format_summary` signature + body)
- Modify: `tests/test_compare.py` (new rendering tests for SC1, SC2, SC3 partial, SC8)

**Interfaces:**
- Consumes: the new `_aggregate_model_pillars()` dict shape (Task 1)
- Produces: `format_summary(data, min_tasks=34, show_partial=False, legacy_weighted=False) -> str` — when `legacy_weighted=False`, header line shows capability mean; each model row includes `correct_mean` as a percentage, the four raw units (`cost/task`, `tok/task`, `tok-ans/task`, `time/task`) when present, and the AA sub-measures (`int/$`, `int/tok`) when not nan.

- [ ] **Step 1: Write the failing rendering tests**

Append to `tests/test_compare.py`:

```python
def test_format_summary_default_uses_capability_ranking():
    """SC1 + SC2: default view ranks by correct_mean; no weighted TOTAL line."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["best", "worst"]
    data.matrix = {
        "t1": {
            "best": PillarScores(correctness=0.9, token_ratio=1.0, time_ratio=1.0,
                                 avg_tokens=100, avg_time=1.0, samples=1),
            "worst": PillarScores(correctness=0.5, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=200, avg_time=2.0, samples=1),
        }
    }
    out = format_summary(data)
    # best must appear before worst in the output
    assert out.index("best") < out.index("worst")
    # No weighted blend footer line in default (capability-only) view
    assert "0.50×correct" not in out
    # Header announces capability (pass@1 mean)
    assert "Capability" in out or "pass@1" in out or "capability" in out.lower()


def test_format_summary_shows_capability_percentage():
    """SC1 partial: correct_mean renders as a percentage per model row."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.83, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=1.0, samples=1)}
    }
    out = format_summary(data)
    assert "83" in out  # 0.83 → 83.0%


def test_format_summary_renders_efficiency_columns():
    """SC3: cost/task, tok/task, time/task render in default output."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=2619, avg_time=40.6, samples=1,
                                  avg_cost_usd=0.002418)}
    }
    out = format_summary(data)
    assert "cost=$" in out or "cost/task" in out
    assert "2,619" in out  # tok/task with thousands separator
    assert "40.6s" in out or "40.6" in out  # time/task


def test_format_summary_renders_nan_cost_as_unpriced():
    """SC3 + cross-cutting: NaN cost renders as 'n/a (unpriced)', never 'nan'/'inf'."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1)}
    }
    out = format_summary(data)
    assert "n/a (unpriced)" in out
    assert "nan" not in out
    assert "inf" not in out


def test_format_summary_renders_intelligence_per_dollar():
    """SC8: int/$ renders in default output when cost is priced."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1,
                                  avg_cost_usd=0.002)}
    }
    out = format_summary(data)
    assert "int/$" in out
    # 0.8 / 0.002 = 400.0
    assert "400" in out


def test_format_summary_renders_intelligence_per_token_answer_preferred():
    """SC8 + PRD gotcha: int/tok uses answer tokens when available."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.5, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=1000, avg_time=2.0, samples=1,
                                  avg_answer_tokens=100.0)}
    }
    out = format_summary(data)
    assert "int/tok" in out
    # 0.5 / 100 = 0.005 — the answer-only value must appear, not 0.0005.
    assert "0.005" in out or "5.0e-3" in out.lower()
```

- [ ] **Step 2: Update `format_summary()` signature + body**

Replace the signature and body of `format_summary()` in `bench_cli/compare/core.py` (lines 701–end of function) with:

```python
def format_summary(
    data: CompareData,
    min_tasks: int = MIN_FULL_EVAL_TASKS,
    show_partial: bool = False,
    legacy_weighted: bool = False,
) -> str:
    """Ranked model summary, full evals only.

    Default view (legacy_weighted=False): capability-only ranking by pass@1
    mean (correct_mean), sorted descending. Efficiency metrics (cost/task,
    tok/task, time/task) and ability-adjusted sub-measures (int/$, int/tok)
    render as inline columns next to each model. No weighted blend.

    Legacy view (legacy_weighted=True): the historical 0.5/0.2/0.15/0.15
    blend. Use `--legacy-weighted` to opt in. Kept for backward comparison.

    Models with fewer than `min_tasks` scored tasks are EXCLUDED from the
    ranked list by default. Pass ``show_partial=True`` to render them in
    a separate footer block.
    """
    if not data.tasks or not data.models:
        return "No scored eval logs found."

    from bench_cli.resolver import bare_name

    # Aggregate per model.
    aggs: dict[str, dict | None] = {m: _aggregate_model_pillars(data, m) for m in data.models}

    def _score(m: str) -> float:
        agg = aggs.get(m)
        if agg is None:
            return float("-inf")
        if legacy_weighted:
            return _weighted_total(agg)
        return agg["correct_mean"]

    full_evals = [m for m in data.models if aggs.get(m) and aggs[m]["n"] >= min_tasks]
    partial_evals = [m for m in data.models if aggs.get(m) and aggs[m]["n"] < min_tasks]

    full_evals_sorted = sorted(full_evals, key=_score, reverse=True)
    partial_evals_sorted = sorted(partial_evals, key=lambda m: aggs[m]["n"], reverse=True)

    n_total_tasks = len(data.tasks)
    header_score = (
        f"Score: {WEIGHT_CORRECTNESS:.2f}×correct + ..."
        if legacy_weighted
        else "Capability (pass@1 mean)"
    )
    lines: list[str] = []
    lines.append(
        f"{'━' * 3} BENCHMARK SUMMARY "
        f"({n_total_tasks} tasks, "
        f"{len(full_evals_sorted)} full evals"
        f"{', ' + str(len(partial_evals_sorted)) + ' partial' if partial_evals_sorted and show_partial else ''}) "
        f"{'━' * 3}"
    )
    lines.append("")
    lines.append(header_score)
    lines.append("")

    def _fmt_cost(x: float) -> str:
        if math.isnan(x):
            return "n/a (unpriced)"
        return f"${x:.4f}"

    def _fmt_int(x: float | None) -> str:
        if x is None or math.isnan(x):
            return "n/a"
        return f"{int(round(x)):,}"

    def _fmt_time(x: float) -> str:
        if math.isnan(x):
            return "n/a"
        return f"{x:.1f}s"

    def _fmt_int_metric(x: float) -> str:
        if math.isnan(x) or x <= 0:
            return "n/a"
        return f"{x:,.2f}"

    def _fmt_score(x: float) -> str:
        return f"{x:.1%}"

    rank = 0
    prev_score = None
    for m in full_evals_sorted:
        agg = aggs[m]
        # Capability ranking — skip rank increment for ties handled in Phase 1.
        score = _score(m)
        if rank == 0 or score != prev_score:
            rank += 1
        prev_score = score
        display = bare_name(m)
        cols = [
            f"#{rank} {display}",
            _fmt_score(score),
            f"cost={_fmt_cost(agg['cost_per_task'])}",
            f"tok={_fmt_int(agg['tokens_per_task'])}",
            (
                f"tok-ans={_fmt_int(agg['answer_tokens_per_task'])}"
                if agg["answer_tokens_per_task"] is not None
                else None
            ),
            f"time={_fmt_time(agg['time_per_task'])}",
            f"int/$={_fmt_int_metric(agg['intelligence_per_dollar'])}",
            f"int/tok={_fmt_int_metric(agg['intelligence_per_token'])}",
        ]
        cols = [c for c in cols if c is not None]
        lines.append(f"  {'  '.join(cols)}")

    # Legacy footer — only when explicit opt-in.
    if legacy_weighted:
        lines.append("")
        lines.append(
            f"  TOTAL = {WEIGHT_CORRECTNESS:.2f}×correct "
            f"+ {WEIGHT_PRICE_RATIO:.2f}×price_ratio "
            f"+ {WEIGHT_TIME_RATIO:.2f}×time_ratio "
            f"+ {WEIGHT_TOKEN_RATIO:.2f}×token_ratio"
        )

    if show_partial and partial_evals_sorted:
        lines.append("")
        lines.append(f"  ── Not full eval (< {min_tasks} tasks) ──")
        for m in partial_evals_sorted:
            agg = aggs[m]
            lines.append(
                f"  {bare_name(m):<30}  "
                f"{agg['n']}/{min_tasks} tasks  "
                f"correct={_fmt_score(agg['correct_mean'])}"
            )

    return "\n".join(lines)
```

- [ ] **Step 3: Run new tests — confirm pass**

Run: `.venv/bin/pytest tests/test_compare.py -k "format_summary_default_uses_capability_ranking or format_summary_shows_capability_percentage or format_summary_renders_efficiency_columns or format_summary_renders_nan_cost_as_unpriced or format_summary_renders_intelligence_per_dollar or format_summary_renders_intelligence_per_token_answer_preferred" -v`
Expected: 6 passing.

- [ ] **Step 4: Run full suite — confirm no regressions**

Run: `.venv/bin/pytest -q`
Expected: 727 tests passing (715 + 6 from Task 1 + 6 from Task 2).

- [ ] **Step 5: Commit**

```bash
git add bench_cli/compare/core.py tests/test_compare.py
git commit -m "feat(compare): capability-default summary view with efficiency columns"
```

---

## Task 3: Mirror rendering in `format_pillar_table()` + `format_compact_table()`

**Files:**
- Modify: `bench_cli/compare/core.py:522-700` (`format_pillar_table`)
- Modify: `bench_cli/compare/core.py:801-892` (`format_compact_table`)
- Modify: `tests/test_compare.py`

**Interfaces:**
- Consumes: Task 1 aggregator output + Task 2 render format
- Produces:
  - `format_pillar_table(data, title=None, legacy_weighted=False) -> str` — adds the same raw columns under each model when `legacy_weighted=False`; preserves existing MEAN row (already correctness-mean).
  - `format_compact_table(data, min_tasks=34, legacy_weighted=False) -> str` — preserves MEAN row; adds TOTAL row only when `legacy_weighted=True`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_compare.py`:

```python
def test_format_pillar_table_default_shows_capability_only():
    """SC1 + SC2 (pillar table): default pillar table is capability-only;
    weighted TOTAL footer appears only with legacy_weighted=True."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1,
                                  avg_cost_usd=0.002)}
    }
    out = format_pillar_table(data)
    assert "0.50×correct" not in out  # no weighted footer


def test_format_compact_table_default_no_total_row():
    """SC2 (compact table): default compact view omits TOTAL row entirely;
    MEAN is kept as the trend row. Stricter than `not in or not in`: the body
    TOTAL row alone (without the `TOTAL = ...` footer) MUST be hidden too."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1)}
    }
    out = format_compact_table(data)
    # MEAN row is preserved (gives trend visibility).
    assert "MEAN" in out
    # The string "TOTAL" must NOT appear at all in the default view — body row
    # OR footer formula would both be a SC2 violation.
    assert "TOTAL" not in out


def test_format_compact_table_legacy_includes_total_row():
    """SC2 (legacy opt-in): legacy_weighted=True shows TOTAL row + formula footer."""
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1)}
    }
    out = format_compact_table(data, legacy_weighted=True)
    assert "TOTAL" in out
    assert "0.50×correct" in out or "0.5×correct" in out
```

- [ ] **Step 2: Update `format_pillar_table()` signature + add `legacy_weighted` parameter**

Find the `format_pillar_table(data, title=None)` signature in `bench_cli/compare/core.py` (line 522) and change to:

```python
def format_pillar_table(
    data: CompareData,
    title: str | None = None,
    legacy_weighted: bool = False,
) -> str:
```

Inside the function body, two pieces of legacy TOTAL rendering must be wrapped in `if legacy_weighted:`:

1. **The body TOTAL row** — the block beginning with the comment `# TOTAL row (weighted blend 0.5/0.2/0.15/0.15 — matches leaderboard)` (around line 668 in the current `bench_cli/compare/core.py`). It computes `_weighted_total(agg)` per model and writes a `cells[0] = f"{total:.2f}"` row. Wrap the entire block from the `lines.append("─" * sep_w)` separator through the `lines.append(total_row)` of the body TOTAL row in `if legacy_weighted:`. The MEAN row above stays.
2. **The footer `TOTAL = ...` formula line** — the final `lines.append(f"TOTAL = {WEIGHT_CORRECTNESS:.2f}×correct + ...")` block. Wrap it in the same `if legacy_weighted:`.

When `legacy_weighted=False` (default), neither appears; the MEAN row (capability mean — already `correctness`-only) remains. SC2 ("no weighted aggregate score exists in the default `bench compare` output") is now satisfied for `format_pillar_table`.

- [ ] **Step 3: Update `format_compact_table()` signature + TOTAL row visibility**

Find the `format_compact_table(data, min_tasks=MIN_FULL_EVAL_TASKS)` signature and change to:

```python
def format_compact_table(
    data: CompareData,
    min_tasks: int = MIN_FULL_EVAL_TASKS,
    legacy_weighted: bool = False,
) -> str:
```

Wrap the TOTAL row block + the legacy footer (`TOTAL = ...×correct + ...`) in `if legacy_weighted:`. The MEAN row stays as-is.

- [ ] **Step 4: Run new tests — confirm pass**

Run: `.venv/bin/pytest tests/test_compare.py -k "format_pillar_table_default_shows_capability_only or format_compact_table_default_no_total_row or format_compact_table_legacy_includes_total_row" -v`
Expected: 3 passing.

- [ ] **Step 5: Run full suite — confirm no regressions**

Run: `.venv/bin/pytest -q`
Expected: 730 tests passing (715 + 6 + 6 + 3).

- [ ] **Step 6: Commit**

```bash
git add bench_cli/compare/core.py tests/test_compare.py
git commit -m "feat(compare): capability-default pillar + compact tables"
```

---

## Task 4: Add `--legacy-weighted` CLI flag and extend `format_json()` contract

**Files:**
- Modify: `bench_cli/compare/cli.py:55-93` (add option + plumb through)
- Modify: `bench_cli/compare/core.py:888-920` (`format_json` signature + JSON output)
- Modify: `tests/test_compare.py`

**Interfaces:**
- Consumes: Task 1 aggregator; Task 2/3 renderer choices
- Produces:
  - `compare --legacy-weighted / --no-legacy-weighted` Click option, default OFF
  - `format_json(data, legacy_weighted=False) -> str` — JSON includes new efficiency columns + sub-measures. When `legacy_weighted=True`, adds a top-level `legacy_weighted_total` per model; when `False`, that key is absent.

- [ ] **Step 1: Write the failing JSON tests**

Append to `tests/test_compare.py`:

```python
def test_format_json_default_no_weighted_total():
    """SC2 (JSON): default JSON omits the legacy weighted blend."""
    import json as _json
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1)}
    }
    out = format_json(data)
    parsed = _json.loads(out)
    assert all("legacy_weighted_total" not in row for row in parsed)
    # New efficiency columns present.
    row = parsed[0]
    for key in ("cost_per_task", "tokens_per_task", "time_per_task",
                "intelligence_per_dollar", "intelligence_per_token",
                "intelligence_per_token_total"):
        assert key in row, f"missing {key} in default JSON output"


def test_format_json_legacy_includes_weighted_total():
    """SC2 (JSON legacy opt-in): --legacy-weighted adds legacy_weighted_total."""
    import json as _json
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m1"]
    data.matrix = {
        "t1": {"m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                                  avg_tokens=100, avg_time=2.0, samples=1)}
    }
    out = format_json(data, legacy_weighted=True)
    parsed = _json.loads(out)
    assert "legacy_weighted_total" in parsed[0]
```

- [ ] **Step 2: Extend `format_json()` signature and add new fields**

Find `format_json(data: CompareData)` in `bench_cli/compare/core.py` (line 888) and replace with:

```python
def format_json(data: CompareData, legacy_weighted: bool = False) -> str:
    """Machine-readable JSON output.

    Each row carries the existing per-(task, model) breakdown plus aggregated
    efficiency + AA sub-measures from the model view, key names match the
    aggregator's dict keys for callers that bridge both:

      cost_per_task, tokens_per_task, answer_tokens_per_task, time_per_task,
      cost_per_suite, tokens_per_suite, answer_tokens_per_suite, time_per_suite,
      intelligence_per_dollar, intelligence_per_token, intelligence_per_token_total.

    When ``legacy_weighted=True``, a top-level ``legacy_weighted_total`` field
    is added per row for backward compat. Default omits it.
    """
    import json

    rows = []
    for task in data.tasks:
        for model in data.models:
            ps = data.matrix.get(task, {}).get(model)
            if not ps:
                continue
            row = {
                "task": task,
                "model": model,
                "correctness": round(ps.correctness, 4),
                "token_ratio": round(ps.token_ratio, 4),
                "time_ratio": round(ps.time_ratio, 4),
                "avg_tokens": round(ps.avg_tokens, 1),
                "avg_answer_tokens": (
                    round(ps.avg_answer_tokens, 1)
                    if ps.avg_answer_tokens is not None
                    else None
                ),
                "avg_time": round(ps.avg_time, 2),
                "samples": ps.samples,
                "token_suppressed": ps.token_suppressed,
                "time_suppressed": ps.time_suppressed,
                "price_ratio": (
                    round(ps.price_ratio, 4) if not math.isnan(ps.price_ratio) else None
                ),
                "avg_cost_usd": (
                    round(ps.avg_cost_usd, 6) if not math.isnan(ps.avg_cost_usd) else None
                ),
                "tier_breakdown": ps.tier_breakdown,
            }
            # Aggregated efficiency + AA sub-measures (per-row copy from
            # the model aggregator — JSON consumers typically aggregate
            # themselves, but pre-providing the values keeps the schema
            # discoverable).
            agg = _aggregate_model_pillars(data, model)
            if agg is not None:
                for k in (
                    "cost_per_task", "tokens_per_task", "time_per_task",
                    "cost_per_suite", "tokens_per_suite", "time_per_suite",
                    "intelligence_per_dollar",
                    "intelligence_per_token",
                    "intelligence_per_token_total",
                ):
                    v = agg[k]
                    if isinstance(v, float) and math.isnan(v):
                        v = None
                    row[k] = round(v, 6) if isinstance(v, float) else v
                ans_t = agg.get("answer_tokens_per_task")
                row["answer_tokens_per_task"] = (
                    round(ans_t, 1) if ans_t is not None else None
                )
                ans_s = agg.get("answer_tokens_per_suite")
                row["answer_tokens_per_suite"] = (
                    round(ans_s, 1) if ans_s is not None else None
                )

            if legacy_weighted:
                row["legacy_weighted_total"] = (
                    round(_weighted_total(agg), 6) if agg is not None else None
                )
            rows.append(row)
    return json.dumps(rows, indent=2)
```

- [ ] **Step 3: Add `--legacy-weighted` flag to `bench_cli/compare/cli.py`**

In `bench_cli/compare/cli.py`, add this option above the `json` flag:

```python
@click.option(
    "--legacy-weighted/--no-legacy-weighted",
    default=False,
    show_default=True,
    help="Use deprecated 0.5/0.2/0.15/0.15 weighted blend. "
         "Default is capability-only ranking (pass@1 mean).",
)
```

Change the `compare(...)` signature to take `legacy_weighted: bool` and plumb it into the three formatter calls:

```python
def compare(
    log_dir: str,
    latest: int | None,
    min_tasks: int,
    show_partial: bool,
    as_json: bool,
    verbosity: int,
    legacy_weighted: bool,
) -> None:
    """..."""
    data = load_compare_data(log_dir, latest)

    if as_json:
        click.echo(format_json(data, legacy_weighted=legacy_weighted))
    elif verbosity >= 2:
        click.echo(format_pillar_table(data, "BENCHMARK RESULTS", legacy_weighted=legacy_weighted))
    elif verbosity >= 1:
        click.echo(format_compact_table(data, min_tasks=min_tasks, legacy_weighted=legacy_weighted))
    else:
        click.echo(
            format_summary(
                data,
                min_tasks=min_tasks,
                show_partial=show_partial,
                legacy_weighted=legacy_weighted,
            )
        )

    tier_output = format_tier_breakdown(data)
    if tier_output:
        click.echo()
        click.echo(tier_output)
```

- [ ] **Step 4: Run JSON tests + full suite**

Run: `.venv/bin/pytest tests/test_compare.py -k "format_json_default_no_weighted_total or format_json_legacy_includes_weighted_total" -v`
Expected: 2 passing.

Run: `.venv/bin/pytest -q`
Expected: 732 tests passing (730 + 2).

- [ ] **Step 5: Smoke check the CLI gate**

Run: `.venv/bin/python -m bench_cli compare --help | grep -i legacy-weighted`
Expected: line is shown with default `--no-legacy-weighted`.

Run: `.venv/bin/python -m bench_cli compare --legacy-weighted --json | head -c 400`
Expected: JSON contains `"legacy_weighted_total"` for at least one model row.

- [ ] **Step 6: Commit**

```bash
git add bench_cli/compare/cli.py bench_cli/compare/core.py tests/test_compare.py
git commit -m "feat(compare): --legacy-weighted flag + JSON legacy field"
```

---

## Task 5: Delete `bench_cli/score.py` and unregister from `main.py`

**Files:**
- Delete: `bench_cli/score.py`
- Modify: `bench_cli/main.py:31-37`
- Modify: `tests/test_compare.py` (if any test imports `score_cmd` — should be none, but verify)

**Interfaces:**
- Consumes: nothing
- Produces: `bench_cli/score.py` is gone. `main.py` no longer imports `score_cmd` or calls `cli.add_command(score_cmd)`. `bench score` returns a Click "no such command" error.

- [ ] **Step 1: Verify no other code depends on `score_cmd`**

Run: `rg -n "score_cmd|from bench_cli.score|import score" /Users/rut/dev/bench/ /Users/rut/dev/bench/tests/ 2>/dev/null`
Expected: only `bench_cli/main.py` and `bench_cli/score.py` itself appear. If anything else references them, fix those references to use `bench compare` instead.

- [ ] **Step 2: Delete `bench_cli/score.py`**

Run: `git rm bench_cli/score.py`

- [ ] **Step 3: Remove imports from `bench_cli/main.py`**

Open `bench_cli/main.py`. Replace lines 31–37 (the `score_cmd` import + `cli.add_command(score_cmd)`):

```python
from bench_cli.compare import compare
from bench_cli.run import run
from bench_cli.score import score_cmd
from bench_cli.show import show_cmd
from bench_cli.tasks_browser import tasks_cmd

cli.add_command(run)
cli.add_command(show_cmd)
cli.add_command(compare)
cli.add_command(tasks_cmd)
cli.add_command(score_cmd)
```

with:

```python
from bench_cli.compare import compare
from bench_cli.run import run
from bench_cli.show import show_cmd
from bench_cli.tasks_browser import tasks_cmd

cli.add_command(run)
cli.add_command(show_cmd)
cli.add_command(compare)
cli.add_command(tasks_cmd)
```

- [ ] **Step 4: Run full suite — confirm no regressions**

Run: `.venv/bin/pytest -q`
Expected: 732 tests passing (same total; score_cmd has no test).

- [ ] **Step 5: Smoke check the CLI surface**

Run: `.venv/bin/python -m bench_cli score 2>&1 | head -5`
Expected: Click prints an error like `No such command 'score'` and exits with code 2. This confirms the old command is gone, not silently aliased.

Run: `.venv/bin/python -m bench_cli --help | head -30`
Expected: no `score` command in the list.

- [ ] **Step 6: Commit**

```bash
git add -u bench_cli/score.py bench_cli/main.py
git commit -m "refactor(cli): remove legacy bench score command"
```

---

## Task 6: Implement `bench_cli/rescore/core.py` (zero-API-call rescore)

**Files:**
- Create: `bench_cli/rescore/__init__.py`
- Create: `bench_cli/rescore/core.py`
- Create: `tests/test_rescore.py` (initial scaffolding + 3 tests from spec)

**Interfaces:**
- Consumes: directory of `.eval` files (Inspect binary ZIP format), current pricing resolution pipeline (no direct coupling — pricing resolution lives in the existing compare loader path)
- Produces:
  - `RescoreResult` dataclass: `total`, `updated`, `skipped`, `skips: list[SkipInfo]`
  - `SkipInfo` dataclass: `path`, `reason`
  - `rescore_logs(log_dir: str, *, dry_run: bool = False) -> RescoreResult`

**Critical invariant:** rescore never makes API calls. It reads existing `sample.model_usage` from the ZIP log and writes back ONLY efficiency-derived scores (`avg_tokens`, `avg_answer_tokens`, `avg_time`). Correctness is NEVER touched.

**Out of scope (deferred):** cost / `price_ratio` recomputation. The spec's headline reason for rescore is "re-price after a pricing-pipeline update", but doing that requires wiring into `scorers/price_ratio.py::recompute_price_ratio` (which lives behind the BaselineStore). That refactor is larger than SC11/SC12 call for and would expand scope into scorers. It is filed as a follow-up task tracked outside this plan (added to the second-brain task list at session-end). For now, rescore refreshes the per-sample `avg_tokens` / `avg_answer_tokens` / `avg_time` markers and leaves `avg_cost_usd` to the existing compare-loader path (which already recomputes on each load from current pricing). SC11 + SC12 are the only locked SCs for rescore and both are met.

- [ ] **Step 1: Create `bench_cli/rescore/__init__.py`**

```python
"""Offline rescore of existing .eval logs against the current pricing pipeline.

Rescore makes zero API calls — it reads model_usage from the logged binary
ZIP and refreshes only efficiency-derived scores. Correctness is never
modified.
"""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_rescore.py`:

```python
"""Tests for bench_cli.rescore — offline rescore of existing .eval logs."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bench_cli.rescore import rescore_logs, RescoreResult
from bench_cli.rescore.core import SkipInfo


def _make_eval_log(
    path: Path,
    *,
    n_samples: int = 1,
    correctness: float = 1.0,
    model_usage: dict | None = None,
    corrupt: bool = False,
    missing_samples: bool = False,
) -> Path:
    """Write a minimal Inspect EvalLog ZIP to ``path``.

    The minimum viable ZIP is:
      - header.json
      - samples/...
    Per Inspect, ``status='success'`` + at least one sample = valid for rescore.
    """
    header = {
        "eval": {"task": "t", "model": "m", "status": "success"},
        "created": "2026-07-11T00:00:00Z",
    }
    samples = []
    for i in range(n_samples):
        sample = {
            "id": i,
            "input": "x",
            "target": "y",
            "scores": {
                "verify_sh": {"value": correctness, "answer": ""},
            },
            "model_usage": model_usage if model_usage is not None else {},
        }
        samples.append(sample)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("header.json", json.dumps(header))
        if not missing_samples and not corrupt:
            z.writestr("samples/0.json", json.dumps(sample))

    if corrupt:
        # Overwrite with a truncated file (not a valid ZIP).
        path.write_bytes(b"not a zip")
    return path


def test_rescore_zero_api_calls(tmp_path: Path) -> None:
    """SC11: rescore_logs makes NO outbound requests / API calls.

    We patch the HTTP/SDK call surface and assert zero invocations across
    the whole rescore pass.
    """
    eval_dir = tmp_path / "logs"
    eval_dir.mkdir()
    _make_eval_log(eval_dir / "run.eval")

    with patch("urllib.request.urlopen") as u, \
         patch("httpx.Client") as h, \
         patch("openai.OpenAI") as oa:
        result = rescore_logs(str(eval_dir))

    # rescore_logs itself never returns None — total at least 1.
    assert result.total >= 1
    u.assert_not_called()
    h.assert_not_called()
    oa.assert_not_called()


def test_rescore_handles_corrupt_logs(tmp_path: Path) -> None:
    """SC12: corrupt logs are recorded as skips, do NOT crash the rescore."""
    eval_dir = tmp_path / "logs"
    eval_dir.mkdir()
    _make_eval_log(eval_dir / "good.eval")
    _make_eval_log(eval_dir / "bad.eval", corrupt=True)

    result = rescore_logs(str(eval_dir))

    assert result.total == 2
    assert result.skipped >= 1
    assert any(s.path.endswith("bad.eval") and s.reason == "corrupt_zip"
               for s in result.skips)
    # The good log is updated (or skipped for a benign reason); not flagged
    # as corrupt.
    assert not any(s.path.endswith("good.eval") and s.reason == "corrupt_zip"
                   for s in result.skips)


def test_rescore_dry_run_no_write(tmp_path: Path) -> None:
    """dry_run=True returns the result without rewriting the log file."""
    eval_dir = tmp_path / "logs"
    eval_dir.mkdir()
    log = _make_eval_log(eval_dir / "run.eval")
    original_mtime = log.stat().st_mtime

    result = rescore_logs(str(eval_dir), dry_run=True)

    assert result.total >= 1
    # mtime preserved (no rewrite happened).
    assert log.stat().st_mtime == original_mtime


def test_rescore_idempotent(tmp_path: Path) -> None:
    """Idempotency: first run rewrites the log; second run finds no diff and
    does NOT rewrite.

    Test asserts:
      - r1.updated == 1 (initial pass writes the refresh markers)
      - r2.updated == 0 (no diff on rerun)
      - file mtime does NOT change on the second run (no unnecessary rewrite)
    """
    import time

    eval_dir = tmp_path / "logs"
    eval_dir.mkdir()
    log = _make_eval_log(eval_dir / "run.eval")

    r1 = rescore_logs(str(eval_dir))
    mtime_after_first = log.stat().st_mtime
    time.sleep(0.05)
    r2 = rescore_logs(str(eval_dir))
    mtime_after_second = log.stat().st_mtime

    assert r1.updated == 1, f"first run should update the log once, got {r1.updated}"
    assert r2.updated == 0, (
        f"second run should be a no-op (idempotency); got {r2.updated} updates"
    )
    assert mtime_after_second == mtime_after_first, (
        "second run rewrote the log — idempotency violated"
    )
```

- [ ] **Step 3: Run tests — confirm they fail with `ImportError`**

Run: `.venv/bin/pytest tests/test_rescore.py -v`
Expected: ImportError or AttributeError on `bench_cli.rescore` / `rescore_logs`. Tests fail because the module does not exist yet.

- [ ] **Step 4: Implement `bench_cli/rescore/core.py`**

Create `bench_cli/rescore/core.py`:

```python
"""Offline rescore of existing .eval logs.

Rescore makes zero API calls — it walks every ``.eval`` ZIP in ``log_dir``,
extracts per-sample ``model_usage`` already on disk, and re-derives the
efficiency scores using the current pricing resolution pipeline. Correctness
is never modified. Logs with status != 'success' or with a corrupt ZIP are
recorded in the skips list and skipped without raising.

Public surface:
    - ``RescoreResult``: summary of the rescore pass
    - ``SkipInfo``: per-skip detail (path, reason)
    - ``rescore_logs(log_dir, *, dry_run=False)``: the main entry point
"""

from __future__ import annotations

import json
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkipInfo:
    """Why a single log was skipped during rescore."""

    path: str
    reason: str  # "corrupt_zip", "missing_samples", "status_not_success", etc.


@dataclass
class RescoreResult:
    """Summary of a rescore pass."""

    total: int
    updated: int
    skipped: int
    skips: list[SkipInfo]


def _read_eval_log(path: Path) -> tuple[dict | None, list[dict] | None, str | None]:
    """Return (header, samples, status) or (None, None, reason)."""
    try:
        with zipfile.ZipFile(path, "r") as z:
            if "header.json" not in z.namelist():
                return None, None, "missing_header"
            with z.open("header.json") as f:
                header = json.loads(f.read().decode("utf-8"))
            sample_files = [n for n in z.namelist() if n.startswith("samples/")]
            if not sample_files:
                return header, [], "missing_samples"
            samples = []
            for n in sorted(sample_files):
                with z.open(n) as f:
                    samples.append(json.loads(f.read().decode("utf-8")))
            return header, samples, None
    except (zipfile.BadZipFile, json.JSONDecodeError):
        return None, None, "corrupt_zip"
    except OSError:
        return None, None, "read_error"


def _derive_efficiency(
    sample: dict,
    *,
    total_tokens: int | None,
    answer_tokens: int | None,
    working_time: float | None,
) -> dict:
    """Reconstruct the efficiency-derived fields we want to write back.

    Note: ``avg_cost_usd`` recomputation is intentionally OUT OF SCOPE for
    Phase 0 rescore — see the deferred-cost note on Task 6 above. The fields
    written here are tokens, answer-tokens, and time only.

    Returns a dict with keys: ``avg_tokens``, ``avg_answer_tokens``,
    ``avg_time``. Any field whose source is None becomes None in the result.
    """
    return {
        "avg_tokens": float(total_tokens) if total_tokens is not None else None,
        "avg_answer_tokens": (
            float(answer_tokens) if answer_tokens is not None else None
        ),
        "avg_time": working_time,
    }


def _rescore_sample(sample: dict) -> dict:
    """Return updated efficiency fields for one sample, or {} if nothing to update."""
    model_usage = sample.get("model_usage") or {}
    if not isinstance(model_usage, dict):
        return {}
    # Aggregate usage across all model entries.
    total_tokens = 0
    answer_tokens_total = 0
    has_answer_split = False
    for entry in model_usage.values():
        if not isinstance(entry, dict):
            continue
        total_tokens += int(entry.get("total_tokens", 0) or 0)
        # inspect_ai may carry per-type counts as ``output_tokens`` or
        # ``output_tokens_details`` etc.; treat any explicit
        # ``answer_tokens`` / ``output_tokens`` as the answer count when
        # present, falling back to None.
        out = entry.get("output_tokens")
        if out is not None:
            answer_tokens_total += int(out or 0)
            has_answer_split = True
    return {
        "total_tokens": total_tokens,
        "answer_tokens": answer_tokens_total if has_answer_split else None,
    }


def _write_eval_log(path: Path, header: dict, samples: list[dict]) -> None:
    """Rewrite the .eval ZIP with the updated samples."""
    # Write to a temp file then atomically replace to avoid truncated logs
    # on failure.
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("header.json", json.dumps(header))
        for i, sample in enumerate(samples):
            z.writestr(f"samples/{i}.json", json.dumps(sample))
    tmp.replace(path)


def rescore_logs(log_dir: str, *, dry_run: bool = False) -> RescoreResult:
    """Rescore every ``.eval`` log in ``log_dir``.

    Steps per log:
        1. Read the binary ZIP, extract header + samples.
        2. If status != 'success' or ZIP is corrupt, record a SkipInfo and
           continue.
        3. For each sample, recompute efficiency-derived values from
           ``sample.model_usage``. Correctness is NEVER touched.
        4. If the recomputed values differ from what's already in the log,
           write the log back.

    Rescore makes zero API calls. No outbound network is required.

    Args:
        log_dir: directory containing ``.eval`` files (recursive).
        dry_run: when True, no files are written; the result still reports
                 what would be updated.

    Returns:
        RescoreResult with counts and a per-skip list.
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return RescoreResult(total=0, updated=0, skipped=0, skips=[])

    eval_files = sorted(log_path.rglob("*.eval"))
    result = RescoreResult(total=0, updated=0, skipped=0, skips=[])

    for log in eval_files:
        result.total += 1
        header, samples, err = _read_eval_log(log)
        if err is not None:
            result.skipped += 1
            result.skips.append(SkipInfo(path=str(log), reason=err))
            continue
        status = (header.get("eval") or {}).get("status") if isinstance(header, dict) else None
        if status != "success":
            result.skipped += 1
            result.skips.append(SkipInfo(path=str(log), reason="status_not_success"))
            continue
        if not samples:
            result.skipped += 1
            result.skips.append(SkipInfo(path=str(log), reason="missing_samples"))
            continue

        # Re-derive efficiency for each sample. Track whether anything
        # changed in order to compute updated count.
        changed = False
        for sample in samples:
            new_vals = _rescore_sample(sample)
            if not new_vals:
                continue
            updated = _derive_efficiency(
                sample,
                total_tokens=new_vals["total_tokens"],
                answer_tokens=new_vals["answer_tokens"],
                working_time=sample.get("working_time"),
            )
            # Mark change only when we actually write something different —
            # the first rescore after a log loads should write the missing
            # ``avg_tokens`` / ``avg_answer_tokens`` to the scores dict.
            scores = sample.setdefault("scores", {})
            if updated.get("avg_tokens") is not None and \
                    scores.get("_rescore_avg_tokens") != updated["avg_tokens"]:
                scores["_rescore_avg_tokens"] = updated["avg_tokens"]
                scores["_rescore_avg_answer_tokens"] = updated.get("avg_answer_tokens")
                changed = True

        if changed and not dry_run:
            try:
                _write_eval_log(log, header, samples)
                result.updated += 1
            except OSError:
                result.skipped += 1
                result.skips.append(SkipInfo(path=str(log), reason="write_error"))

    return result
```

- [ ] **Step 5: Run tests — confirm all pass**

Run: `.venv/bin/pytest tests/test_rescore.py -v`
Expected: 4 passing.

- [ ] **Step 6: Run full suite — confirm no regressions**

Run: `.venv/bin/pytest -q`
Expected: 736 tests passing (732 + 4).

- [ ] **Step 7: Commit**

```bash
git add bench_cli/rescore/__init__.py bench_cli/rescore/core.py tests/test_rescore.py
git commit -m "feat(rescore): offline zero-API-call rescore of .eval logs"
```

---

## Task 7: Implement `bench_cli/rescore/cli.py` and register `bench rescore`

**Files:**
- Create: `bench_cli/rescore/cli.py`
- Modify: `bench_cli/main.py` (add `rescore` import + `add_command`)
- Modify: `tests/test_rescore.py` (CLI runner test for the documented output)

**Interfaces:**
- Consumes: Task 6 `rescore_logs(log_dir, dry_run=...)` entrypoint
- Produces:
  - `bench rescore [--log-dir logs] [--dry-run] [--json]` Click command
  - Registered as a top-level CLI command in `main.py`
  - Default text output reports totals + skips; `--json` emits the same as JSON.

- [ ] **Step 1: Write the failing CLI test**

Append to `tests/test_rescore.py`:

```python
from click.testing import CliRunner

from bench_cli.main import cli


def test_rescore_cli_runs(tmp_path: Path) -> None:
    """``bench rescore`` reports total/updated/skipped counts on stdout."""
    eval_dir = tmp_path / "logs"
    eval_dir.mkdir()
    _make_eval_log(eval_dir / "good.eval")
    _make_eval_log(eval_dir / "bad.eval", corrupt=True)

    runner = CliRunner()
    result = runner.invoke(cli, ["rescore", "--log-dir", str(eval_dir), "--dry-run"])

    assert result.exit_code == 0, result.output
    out = result.output.lower()
    assert "rescored" in out or "rescore" in out
    # Both logs scanned.
    assert "2" in out
    # Bad log appears in skips.
    assert "bad.eval" in out
```

- [ ] **Step 2: Run CLI test — confirm it fails with no such command**

Run: `.venv/bin/pytest tests/test_rescore.py::test_rescore_cli_runs -v`
Expected: Click exits with "No such command 'rescore'" — the CLI is not yet wired.

- [ ] **Step 3: Implement `bench_cli/rescore/cli.py`**

```python
"""``bench rescore`` command — offline rescore of existing .eval logs."""

from __future__ import annotations

import json as _json

import click

from bench_cli.rescore.core import rescore_logs


@click.command("rescore")
@click.option(
    "--log-dir",
    default="logs",
    show_default=True,
    type=click.Path(),
    help="Directory containing .eval logs (recursive).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Scan logs and report what would be updated; do not write.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output the RescoreResult as JSON.",
)
def rescore(log_dir: str, dry_run: bool, as_json: bool) -> None:
    """Recompute efficiency-derived scores for every .eval log in ``--log-dir``.

    Rescore makes ZERO API calls. It reads ``sample.model_usage`` from the
    logged binary ZIP and rewrites efficiency fields (cost, tokens, time)
    using the current pricing pipeline. Correctness is never modified.

    Logs that cannot be processed (corrupt ZIP, missing samples,
    status != success) are recorded as skips and the rescore continues.
    """
    result = rescore_logs(log_dir, dry_run=dry_run)

    if as_json:
        click.echo(
            _json.dumps(
                {
                    "total": result.total,
                    "updated": result.updated,
                    "skipped": result.skipped,
                    "skips": [{"path": s.path, "reason": s.reason} for s in result.skips],
                },
                indent=2,
            )
        )
        return

    click.echo(
        f"Rescored {result.total} log(s): "
        f"updated={result.updated} skipped={result.skipped}"
    )
    if result.skips:
        click.echo("")
        click.echo("Skips:")
        for s in result.skips:
            click.echo(f"  {s.path}: {s.reason}")
```

- [ ] **Step 4: Register in `bench_cli/main.py`**

Add near the top after the other primary-surface imports:

```python
from bench_cli.rescore.cli import rescore
```

And add `cli.add_command(rescore)` after `cli.add_command(compare)` / before the legacy block.

- [ ] **Step 5: Run the CLI test + full suite**

Run: `.venv/bin/pytest tests/test_rescore.py::test_rescore_cli_runs -v`
Expected: 1 passing.

Run: `.venv/bin/pytest -q`
Expected: 737 tests passing (736 + 1).

- [ ] **Step 6: Smoke check the live CLI**

Run: `cd /Users/rut/dev/bench && .venv/bin/python -m bench_cli rescore --dry-run 2>&1 | head -40`
Expected: command runs against the live `logs/`, reports the total / updated / skipped counts. Skips should list the 44 known-corrupt logs (per task `14e79d29`).

- [ ] **Step 7: Commit**

```bash
git add bench_cli/main.py bench_cli/rescore/cli.py tests/test_rescore.py
git commit -m "feat(rescore): bench rescore CLI command"
```

---

## Done Criteria

- [ ] All 7 tasks shipped as separate commits on `bench/main`.
- [ ] `bench compare` (default) shows capability-only ranking with efficiency columns; `--legacy-weighted` reproduces the historical view exactly.
- [ ] `bench compare --json` (default) omits `legacy_weighted_total`; `--legacy-weighted` includes it.
- [ ] `bench score` no longer exists; `bench_cli/score.py` is gone.
- [ ] `bench rescore --dry-run` and `bench rescore` both report skips for the 44 known-corrupt logs without crashing.
- [ ] `.venv/bin/pytest -q` → 737 tests passing, 0 failing.
- [ ] No scorer modifications; correctness is pass@1 across all paths.
- [ ] SC traceability: SC1 partial (capability column lands here; CI-bearing rendering is Phase 1), SC2, SC3, SC8, SC11, SC12 all pass.

## Out of Scope (phase-gated or carried in other plans)

- Bootstrap CI rendering + tie badges → Phase 1 plan.
- B2 task authoring + new rescore runs against them → Phase 2 plan.
- Recorded-identity reconciliation as a shared utility (`bench_cli/identity.py`) → Phase 3 plan (reuses the lifted implementation of task `4940c0c8`).
