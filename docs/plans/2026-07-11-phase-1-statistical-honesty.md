# Phase 1 — Statistical Honesty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Load subagent-driven-development/SKILL.md (recommended) or executing-plans/SKILL.md to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bootstrap 95% confidence intervals to the capability mean in `bench compare`, and render pairwise tie badges when CIs overlap. Give the user honest "I can't separate these models" signals instead of false-precision rank gaps.

**Architecture:** Pure additions to `bench_cli/compare/`. Two new modules — `compare/bootstrap.py` (pure-Python percentile bootstrap with seeded RNG) and `compare/ties.py` (pairwise CI overlap detection, NOT transitive). The aggregator grows two new fields (`ci_low`, `ci_high` per model) and three renderers (`format_summary`, `format_pillar_table`, `format_compact_table`) learn to embed `[CI_low, CI_high]` after the capability number plus a `≈` badge on consecutive overlapping ties. CLI gates via `--no-ci`.

**Tech Stack:** Python 3.14 stdlib (`random.Random` for bootstrap, no numpy), Click 8, pytest. No new dependencies.

## Global Constraints

- Use the project `.venv`: `.venv/bin/python` and `.venv/bin/pytest`. No system python. (`AGENTS.md`)
- Scorers live in `scorers/` at repo root, imported as `from scorers import ...`. `bench_cli/scorers/` does NOT exist. (`AGENTS.md`)
- Models route through a LiteLLM proxy as `openai/<alias>`; `.env` holds credentials. (SB Operating Rules)
- `bench_cli/compare/` is a package: `from bench_cli.compare.bootstrap import ...`, etc.
- Bootstrap CI is the **performance CI** (bootstrap on pass@1 means across tasks). IRT credible interval is the **ability CI** (θ posterior). The two have different concepts; F3 mitigation requires they are explicitly labeled to avoid confusion. Phase 1 ships performance CIs only; the IRT ability-CI lands in Phase 3.
- Bootstrap module is pure-Python (`random.Random(seed)`); do not pull numpy — keep the dependency surface flat.
- Partial-eval models (n < `MIN_FULL_EVAL_TASKS`, the existing constant = 34) suppress CI: render `[insufficient data]`, not `[n/a, n/a]`. They remain ranked but the tie badge is also suppressed (no pairwise comparison without CIs).
- Tie detection is **pairwise, non-transitive**. Two models tie if their CIs overlap on any point. `detect_ties()` returns a flat list of `{model_a, model_b}` groups — not connected components. A model can appear in multiple groups.
- Render gate: capability columns appear in default (capability-only) view; CI bracket appears AFTER the capability number so users see both. Tie badge annotates consecutive sorted models whose CIs overlap.
- Tests for SC6 (`test_bootstrap_ci_reproducible`) and SC7 (`test_tie_badge_on_overlapping_ci`) live in `tests/test_compare.py`, per PRD Test Plan lock. Do not split into separate files.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `bench_cli/compare/bootstrap.py` | `bootstrap_ci()` — seeded percentile bootstrap, returns `(ci_low, ci_high) | None` | Create |
| `bench_cli/compare/ties.py` | `detect_ties()` + `annotate_with_ties()` — pairwise overlap, non-transitive; annotator picks highest-ranked partner | Create |
| `bench_cli/compare/core.py` | Extend `_aggregate_model_pillars()` with CI; extend `format_summary`/`format_pillar_table`/`format_compact_table` to embed CIs and tie badges | Modify |
| `bench_cli/compare/cli.py` | `--no-ci` flag + plumb through to renderers | Modify |
| `tests/test_compare.py` | SC6 + SC7 + pairwise-not-transitive + CI rendering tests | Modify |

No new dependencies. No scorer changes. No `.eval` log format changes.

---

## Task 1: `bench_cli/compare/bootstrap.py` with `bootstrap_ci()`

**Files:**
- Create: `bench_cli/compare/bootstrap.py`
- Modify: `tests/test_compare.py` (append SC6 + 2 invariant tests)

**Interfaces:**
- Consumes: a flat list of per-task correctness values
- Produces: `bootstrap_ci(per_task_scores, *, n_resample=1000, confidence=0.95, seed=42, min_n=34) -> tuple[float, float] | None`
  - Returns `None` if `len(per_task_scores) < min_n` — caller renders "insufficient data".
  - Otherwise returns `(ci_low, ci_high)` from the percentile-of-resampled-means distribution.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_compare.py`:

```python
from bench_cli.compare.bootstrap import bootstrap_ci


def test_bootstrap_ci_reproducible_with_fixed_seed():
    """PRD-locked name: ``test_bootstrap_ci_reproducible``. SC6: bootstrap_ci
    returns the same bounds across runs when seed and inputs are identical.
    The PRD test plan locks this name as the canonical SC6 reviewer
    navigation point; the ``_with_fixed_seed`` suffix here is descriptive
    only — implementations are encouraged to alias this exact test name."""
    scores = [0.9, 0.85, 0.7, 0.6, 0.55, 0.95, 0.8, 0.75, 0.65, 0.5] * 4  # 40 values
    a = bootstrap_ci(scores, n_resample=500, seed=42)
    b = bootstrap_ci(scores, n_resample=500, seed=42)
    assert a == b, "identical seed + inputs must produce identical CIs"
    lo, hi = a
    assert 0 <= lo <= hi <= 1


def test_bootstrap_ci_returns_none_when_too_few_tasks():
    """Edge case (PRD edge cases): a model with < min_n tasks cannot get a
    trustworthy CI; return None and let the caller render 'insufficient data'.
    """
    # MIN_FULL_EVAL_TASKS = 34; fewer items -> None.
    scores = [0.9, 0.85, 0.7, 0.6, 0.55, 0.95, 0.8]  # 7 items
    assert bootstrap_ci(scores) is None


def test_bootstrap_ci_default_min_n_is_full_eval_threshold():
    """Invariant: default min_n matches ``MIN_FULL_EVAL_TASKS`` so a partial-
    eval model never gets a misleading CI."""
    from bench_cli.compare.bootstrap import bootstrap_ci as bc
    from bench_cli.compare.core import MIN_FULL_EVAL_TASKS

    # One item below the threshold — must return None.
    scores_below = [0.5 + (i % 5) * 0.1 for i in range(MIN_FULL_EVAL_TASKS - 1)]
    assert bc(scores_below) is None

    # Exactly at the threshold — bootstrap proceeds (returns bounds).
    scores_at = scores_below + [0.7]
    result = bc(scores_at)
    assert result is not None
    lo, hi = result
    assert 0 <= lo <= hi <= 1


def test_bootstrap_ci_narrow_for_tight_values():
    """Sanity: when values cluster tightly, CI is narrow."""
    scores = [0.5] * 50
    lo, hi = bootstrap_ci(scores, n_resample=500, seed=42)
    assert (hi - lo) < 0.1
```

- [ ] **Step 2: Run tests — confirm `ImportError`**

Run: `.venv/bin/pytest tests/test_compare.py -k "bootstrap_ci" -v`
Expected: 4 tests fail with `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Implement `bench_cli/compare/bootstrap.py`**

```python
"""Percentile bootstrap on per-task correctness values.

Used by ``bench compare`` to attach 95% CIs to a model's capability mean.
Pure Python — no numpy. Seeded for reproducibility.
"""

from __future__ import annotations

import random
from typing import Iterable


def bootstrap_ci(
    per_task_scores: Iterable[float],
    *,
    n_resample: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
    min_n: int = 34,
) -> tuple[float, float] | None:
    """Bootstrap 95% CI on the mean of per-task correctness scores.

    Args:
        per_task_scores: per-task correctness values (each in [0, 1]).
        n_resample: number of bootstrap iterations. Default 1000.
        confidence: CI level. Default 0.95.
        seed: random seed for reproducibility. Default 42.
        min_n: minimum task count to compute CI. Default ``34``
               (matches ``MIN_FULL_EVAL_TASKS``). Below this returns
               ``None``; callers render "insufficient data" rather than a
               misleading CI.

    Returns:
        ``(ci_low, ci_high)`` tuple, or ``None`` if
        ``len(per_task_scores) < min_n``.
    """
    scores = list(per_task_scores)
    if len(scores) < min_n:
        return None

    rng = random.Random(seed)
    means: list[float] = []
    n = len(scores)
    for _ in range(n_resample):
        # Sample with replacement.
        sample = [scores[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)

    means.sort()
    # Percentile bounds (e.g., 2.5 / 97.5 for 0.95 CI).
    alpha = (1.0 - confidence) / 2.0
    lo_idx = max(0, int(alpha * n_resample))
    hi_idx = min(n_resample - 1, int((1.0 - alpha) * n_resample))
    return (means[lo_idx], means[hi_idx])
```

- [ ] **Step 4: Run tests — confirm pass**

Run: `.venv/bin/pytest tests/test_compare.py -k "bootstrap_ci" -v`
Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add bench_cli/compare/bootstrap.py tests/test_compare.py
git commit -m "feat(compare): percentile bootstrap CI for capability mean"
```

---

## Task 2: `bench_cli/compare/ties.py` with pairwise tie detection

**Files:**
- Create: `bench_cli/compare/ties.py`
- Modify: `tests/test_compare.py` (append SC7 partial + pairwise-not-transitive test)

**Interfaces:**
- Consumes: dict of model → `(ci_low, ci_high)`
- Produces:
  - `detect_ties(model_cis: dict[str, tuple[float, float]]) -> list[set[str]]` — flat list of `{a, b}` for each pairwise overlap. Non-transitive.
  - `annotate_with_ties(sorted_models) -> list[tuple[str, int, str, str | None]]` — assigns rank + tie badge; annotation references the highest-ranked tie-partner (not the predecessor).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_compare.py`:

```python
from bench_cli.compare.ties import annotate_with_ties, detect_ties


def test_tie_badge_on_overlapping_ci():
    """SC7: synthetic overlapping CIs produce a '≈' badge on the lower-ranked
    model and an annotation pointing to the highest-ranked tie-partner."""
    sorted_models = [
        ("a", 0.90, (0.80, 0.99)),  # model a, cap 0.90, CI [0.80, 0.99]
        ("b", 0.85, (0.78, 0.92)),  # overlaps A: 0.78<=0.99 AND 0.80<=0.92
    ]
    out = annotate_with_ties(sorted_models)
    assert out[0] == ("a", 1, "", None)
    assert out[1] == ("b", 2, "≈", "#1"), (
        "B's CI overlaps A's; expect rank=2 (capability order), badge '≈', "
        "annotation '#1' (highest-ranked partner)"
    )


def test_tie_annotation_picks_highest_ranked_partner():
    """Spec example: M ties with both rank 1 and rank 3 (rank 3 ties with neither),
    annotation must point to rank 1, not the predecessor."""
    # Need: c overlaps a but NOT b. b must be disjoint from a (so b→a doesn't tie either),
    # so b's CI is below a's, and c's CI falls between b's range and a's range so it
    # overlaps a but not b.
    # a [0.50, 0.99], b [0.20, 0.45], c [0.55, 0.95].
    # a↔b: a_hi=0.99 < b_lo=0.20? No. b_hi=0.45 < a_lo=0.50? Yes → disjoint. ✓
    # a↔c: a_hi=0.99 < c_lo=0.55? No. c_hi=0.95 < a_lo=0.50? No → overlap. ✓
    # b↔c: b_hi=0.45 < a_lo=0.55? b_hi=0.45 < c_lo=0.55? Yes → disjoint. ✓
    sorted_models = [
        ("a", 0.95, (0.50, 0.99)),
        ("b", 0.40, (0.20, 0.45)),  # rank 2 by cap; CI disjoint from both a and c
        ("c", 0.39, (0.55, 0.95)),  # rank 3 by cap; CI overlaps a (rank 1), not b
    ]
    out = annotate_with_ties(sorted_models)
    # b: disjoint from a → rank 2, no badge.
    assert out[1] == ("b", 2, "", None)
    # c: overlaps a (rank 1) but not b (rank 2) → annotation = "#1".
    assert out[2] == ("c", 3, "≈", "#1"), (
        "c's CI overlaps a's (rank 1), so annotation should be '#1' "
        "(highest-ranked partner), not '#2'"
    )


def test_pairwise_not_transitive():
    """A ties B, B ties C, but A does NOT tie C — implementation respects
    pairwise semantics."""
    # A's CI: [80, 95], B's CI: [78, 97] (overlaps A), C's CI: [50, 70]
    # B-C: 78<=70 is False, but 50<=97 is True... wait, let me think.
    # Overlap = NOT(disjoint). Disjoint = a_hi < b_lo OR b_hi < a_lo.
    # A-B: A_hi=95, B_lo=78 → not disjoint (95 >= 78). Overlap.
    # B-C: B_hi=97, C_lo=50 → not disjoint (97 >= 50). Overlap.
    # A-C: A_hi=95, C_lo=50 → not disjoint (95 >= 50). Overlap.
    # Need stricter example: B's hi < A's lo AND B's hi >= C's hi.
    # A: [60, 80], B: [50, 65], C: [40, 55].
    # A-B: A_lo=60, B_hi=65 — 60<=65 AND 50<=80 → overlap.
    # B-C: B_lo=50, C_hi=55 — 50<=55 AND 40<=65 → overlap.
    # A-C: A_lo=60, C_hi=55 — 60<=55 is False — disjoint. NO tie.
    model_cis = {"a": (60, 80), "b": (50, 65), "c": (40, 55)}
    # Render each pair at 0-1 scale (multiply by 0.01).
    scaled = {k: (v[0] / 100, v[1] / 100) for k, v in model_cis.items()}
    ties = detect_ties(scaled)
    # Expect two ties: {a, b} and {b, c}. A and C should NOT appear together.
    pair_set = [tuple(sorted(g)) for g in ties]
    assert ("a", "b") in pair_set
    assert ("b", "c") in pair_set
    assert ("a", "c") not in pair_set


def test_detect_ties_empty_when_no_overlap():
    """Sanity: non-overlapping CIs produce an empty tie list."""
    model_cis = {"a": (0.50, 0.60), "b": (0.80, 0.90)}
    assert detect_ties(model_cis) == []


def test_detect_ties_skips_models_with_none_ci():
    """Models with CI=None (partial evals) are skipped, not force-tied with anyone."""
    model_cis = {"a": (0.50, 0.60), "b": None, "c": (0.55, 0.65)}
    ties = detect_ties(model_cis)
    # A overlaps C; B is skipped.
    pair_set = [tuple(sorted(g)) for g in ties]
    assert ("a", "c") in pair_set
    assert all("b" not in g for g in pair_set)
```

- [ ] **Step 2: Run tests — confirm `ImportError`**

Run: `.venv/bin/pytest tests/test_compare.py -k "tie or pairwise" -v`
Expected: 4 tests fail with `ImportError`.

- [ ] **Step 3: Implement `bench_cli/compare/ties.py`**

```python
"""Pairwise CI overlap tie detection for ``bench compare``.

Ties are determined per pair (NOT transitive). ``detect_ties`` returns a
flat list of ``{model_a, model_b}`` groups; a model can appear in multiple
groups. ``annotate_with_ties`` produces display rank + ``≈`` badge +
annotation pointing to the highest-ranked tie-partner for any model whose
CI overlaps with at least one higher-ranked model's CI.
"""

from __future__ import annotations

from typing import Iterable


def detect_ties(
    model_cis: dict[str, tuple[float, float] | None],
) -> list[set[str]]:
    """Detect pairwise overlapping CIs.

    Two models are tied if their CIs overlap on any point. Returns a flat
    list of 2-element groups (one per overlapping pair). Non-transitive —
    a model can appear in multiple groups.

    Models with CI=None (partial evals) are skipped.
    """
    groups: list[set[str]] = []
    valid = {k: v for k, v in model_cis.items() if v is not None}
    models = list(valid.keys())
    for i, a in enumerate(models):
        a_lo, a_hi = valid[a]
        for b in models[i + 1 :]:
            b_lo, b_hi = valid[b]
            # Overlap iff NOT (a_hi < b_lo OR b_hi < a_lo).
            if not (a_hi < b_lo or b_hi < a_lo):
                groups.append({a, b})
    return groups


def annotate_with_ties(
    sorted_models: list[tuple[str, float, tuple[float, float] | None]],
) -> list[tuple[str, int, str, str | None]]:
    """Assign (model, rank, badge, tied_with_rank_str) per spec.

    Rank is ordinal (1, 2, 3, ...) by capability descending — never
    non-advancing on tie. The badge is ``"≈"`` only when this model's CI
    overlaps with at least one higher-ranked model's CI; the annotation
    ``tied_with_rank_str`` is ``"#X"`` for the highest-ranked such
    partner, or ``None`` when no badge.

    Partial-eval models (CI=None) get ``(model, rank, "", None)`` — pairwise
    comparison is undefined.

    Implementation: walk the sorted list forward. For each model M, scan
    earlier sorted entries until the first overlap is found. The first
    earlier entry IS the highest-ranked partner because the list is sorted
    by capability descending.
    """
    out: list[tuple[str, int, str, str | None]] = []
    for i, (model, _cap, ci) in enumerate(sorted_models):
        rank = i + 1
        if ci is None:
            out.append((model, rank, "", None))
            continue
        tie_partner_rank: int | None = None
        for j in range(i):
            _other, _other_cap, other_ci = sorted_models[j]
            if other_ci is None:
                continue
            a_lo, a_hi = other_ci
            b_lo, b_hi = ci
            # Overlap iff NOT (a_hi < b_lo OR b_hi < a_lo).
            if not (a_hi < b_lo or b_hi < a_lo):
                tie_partner_rank = j + 1
                break
        if tie_partner_rank is None:
            out.append((model, rank, "", None))
        else:
            out.append((model, rank, "≈", f"#{tie_partner_rank}"))
    return out
```

- [ ] **Step 4: Run tests — confirm pass**

Run: `.venv/bin/pytest tests/test_compare.py -k "tie or pairwise or detect_ties_skips" -v`
Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add bench_cli/compare/ties.py tests/test_compare.py
git commit -m "feat(compare): pairwise CI overlap tie detection"
```

---

## Task 3: Wire CI + tie badge into `format_summary()` and friends

**Files:**
- Modify: `bench_cli/compare/core.py` (`_aggregate_model_pillars` gains `ci_low`, `ci_high`; `format_summary`, `format_pillar_table`, `format_compact_table` render CIs + badges)
- Modify: `tests/test_compare.py` (SC6 + SC7 fully-verified rendering tests)

**Interfaces:**
- Consumes: Task 1 `bootstrap_ci`, Task 2 ties; existing aggregator + renderers
- Produces:
  - `_aggregate_model_pillars()` returns a dict with two new keys: `ci_low: float | None`, `ci_high: float | None`
  - `format_summary()` rows render `capability [CI_low, CI_high]` or `capability [insufficient data]` for partial-eval models. Tie badge `≈` appears adjacent to tied models (rendered after rank).
  - `format_pillar_table()` and `format_compact_table()` render CIs where applicable.
  - All three renderers take a new parameter `include_ci: bool = True` (driven by `--no-ci`).

- [ ] **Step 1: Write the failing rendering tests**

Append to `tests/test_compare.py`:

```python
def test_capability_with_ci_renders_correctly():
    """SC6 (full): format_summary shows capability [CI_low, CI_high] when CI
    is available (>= 34 tasks)."""
    data = CompareData()
    data.tasks = [f"t{i}" for i in range(34)]
    data.models = ["m1"]
    # m1 correctness oscillates between 0.7 and 0.9 — bootstrap CI is well-defined.
    scores = [0.7 + (0.2 if i % 2 == 0 else 0.0) for i in range(34)]
    data.matrix = {
        f"t{i}": {
            "m1": PillarScores(
                correctness=scores[i],
                token_ratio=1.0,
                time_ratio=1.0,
                avg_tokens=100,
                avg_time=1.0,
                samples=1,
            )
        }
        for i in range(34)
    }
    out = format_summary(data, include_ci=True)
    # Bracket form '[lo, hi]' with one decimal place.
    import re
    assert re.search(r"\[\d+\.\d, \d+\.\d\]", out), f"expected CI bracket in:\n{out}"


def test_capability_insufficient_data_for_partial_eval():
    """Edge case: a model with < MIN_FULL_EVAL_TASKS scored tasks renders
    '[insufficient data]' instead of [CI_low, CI_high]."""
    data = CompareData()
    data.tasks = ["t1", "t2"]
    data.models = ["m1", "m2"]
    data.matrix = {
        "t1": {
            "m1": PillarScores(correctness=0.8, token_ratio=1.0, time_ratio=1.0,
                               avg_tokens=100, avg_time=1.0, samples=1),
        },
        "t2": {
            "m1": PillarScores(correctness=0.7, token_ratio=1.0, time_ratio=1.0,
                               avg_tokens=100, avg_time=1.0, samples=1),
        },
    }
    out = format_summary(data, show_partial=True)
    assert "insufficient data" in out
    # No raw CI bracket for partial-eval models.
    import re
    assert not re.search(r"\[0\.\d, 0\.\d\]", out), \
        "partial-eval models must not render numeric CI brackets"


def test_tie_badge_in_renderer():
    """SC7 (full): two models with identical CIs cause the renderer to emit
    the '≈' badge with an annotation pointing to the highest-ranked partner.
    Identical correctness → identical bootstrap CIs → overlap is guaranteed."""
    data = CompareData()
    data.tasks = [f"t{i}" for i in range(34)]
    data.models = ["a", "b"]
    data.matrix = {
        f"t{i}": {
            "a": PillarScores(
                correctness=0.80,
                token_ratio=1.0, time_ratio=1.0,
                avg_tokens=100, avg_time=1.0, samples=1,
            ),
            "b": PillarScores(
                correctness=0.80,
                token_ratio=1.0, time_ratio=1.0,
                avg_tokens=100, avg_time=1.0, samples=1,
            ),
        }
        for i in range(34)
    }
    out = format_summary(data, include_ci=True)
    assert "≈" in out
    # Annotation must reference #1 (highest-ranked partner, the only other
    # model in this fixture).
    assert "tied with #1" in out
```

- [ ] **Step 2: Extend `_aggregate_model_pillars()` with CI fields**

In `bench_cli/compare/core.py`, add an import at the top:

```python
from bench_cli.compare.bootstrap import bootstrap_ci
```

Then, inside `_aggregate_model_pillars()` (the body rewritten in Phase 0 Task 1, before the `return {...}`), insert after `correct_mean = sum(c_vals) / n` and before `_mean(per_task_costs)`:

```python
    # Bootstrap CI on capability mean. Suppressed for partial evals (< min_n).
    ci = bootstrap_ci(c_vals)
    ci_low, ci_high = (None, None) if ci is None else ci
```

Then add `ci_low, ci_high` to the returned dict before `intelligence_per_dollar`.

- [ ] **Step 3: Add `include_ci` parameter to `format_summary()` + render**

In `format_summary()` (Phase 0 Task 2), change the signature to:

```python
def format_summary(
    data: CompareData,
    min_tasks: int = MIN_FULL_EVAL_TASKS,
    show_partial: bool = False,
    legacy_weighted: bool = False,
    include_ci: bool = True,
) -> str:
```

Add the import at the top of the file (or inside the function):

```python
from bench_cli.compare.ties import annotate_with_ties
```

Replace the inner `for m in full_evals_sorted:` loop body with:

```python
    # Build the (sorted_index, model, cap, ci) list the tie ranker expects.
    ranked_inputs = [
        (m, _score(m), (aggs[m].get("ci_low"), aggs[m].get("ci_high")))
        for m in full_evals_sorted
    ]
    # annotate_with_ties expects sorted_inputs as List[(model, cap, ci)].
    sorted_for_ties = [(m, cap, ci) for m, cap, ci in ranked_inputs]
    # annotate_with_ties returns 4-tuples (model, rank, badge, annotation).
    # Annotation is the precomputed string returned by the annotator ("#X"
    # pointing to the highest-ranked tie-partner, or None).
    ranked = annotate_with_ties(sorted_for_ties)

    for m, rank, badge, annotation in ranked:
        agg = aggs[m]
        score = _score(m)
        cap_str = _fmt_score(score)
        ci_lo = agg.get("ci_low")
        ci_hi = agg.get("ci_high")
        if include_ci:
            if ci_lo is None or ci_hi is None:
                ci_str = " [insufficient data]"
            else:
                ci_str = f" [{ci_lo:.1f}, {ci_hi:.1f}]"
        else:
            ci_str = ""
        cols = [
            f"#{rank}{('  ' + badge) if badge else ''} {bare_name(m)}",
            cap_str + ci_str,
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
        # Annotation comes from the tie annotator — it points to the
        # highest-ranked tie-partner, NOT the immediate predecessor. Per
        # spec example, "tied with #1" can render for a rank-3 model whose
        # CI overlaps with rank 1 but NOT rank 2.
        suffix = f"  (tied with {annotation})" if annotation else ""
        lines.append(f"  {'  '.join(cols)}{suffix}")
```

- [ ] **Step 4: Extend `format_pillar_table()` and `format_compact_table()` with `include_ci`**

Same treatment as `format_summary`: add `include_ci: bool = True` parameter and conditionally render the CI bracket. For `format_pillar_table()`, the CI is shown as a header annotation beneath the model name (`m1  [74.2, 87.8]`). For `format_compact_table()`, the MEAN row already shows correctness per task; add an optional row between MEAN and TOTAL showing `mean [CI_low, CI_high]` per model. Skip if `include_ci=False`.

- [ ] **Step 5: Run new tests + full suite**

Run: `.venv/bin/pytest tests/test_compare.py -k "capability_with_ci_renders_correctly or capability_insufficient_data_for_partial_eval or tie_badge_in_renderer" -v`
Expected: 3 passing.

Run: `.venv/bin/pytest -q`
Expected: previously-green tests stay green; this adds 3 to the tally.

- [ ] **Step 6: Commit**

```bash
git add bench_cli/compare/core.py tests/test_compare.py
git commit -m "feat(compare): render bootstrap CI + tie badge in summary/table/compact"
```

---

## Task 4: Add `--no-ci` CLI flag

**Files:**
- Modify: `bench_cli/compare/cli.py`
- Modify: `tests/test_compare.py`

**Interfaces:**
- Consumes: Phase 1 Task 3's `include_ci` parameter
- Produces: `compare --no-ci` Click option, default OFF (CIs on). Plumb through to all 3 renderers.

- [ ] **Step 1: Write the failing CLI test**

Append to `tests/test_compare.py`:

```python
def test_format_summary_no_ci_omits_brackets():
    """--no-ci path: include_ci=False drops the numeric CI bracket entirely
    (insufficient-data fallback may stay, since it carries no numeric value)."""
    import re
    data = CompareData()
    data.tasks = [f"t{i}" for i in range(34)]
    data.models = ["m1"]
    data.matrix = {
        f"t{i}": {
            "m1": PillarScores(
                correctness=0.85,
                token_ratio=1.0, time_ratio=1.0,
                avg_tokens=100, avg_time=1.0, samples=1,
            )
        }
        for i in range(34)
    }
    out = format_summary(data, include_ci=False)
    # No numeric bracket pattern "[<digit>" should appear (catches CI and
    # any future numeric brackets).
    assert re.search(r"\[\d", out) is None, (
        f"numeric CI bracket leaked into no-CI output:\n{out}"
    )
    # Capability percentage still renders.
    assert "85" in out
```

- [ ] **Step 2: Run test — confirm it fails**

Run: `.venv/bin/pytest tests/test_compare.py -k "no_ci_omits_brackets" -v`
Expected: PASS already — this is a regression guard rather than a TDD failure driver. The previous Tasks 1–3 ship `include_ci=True` by default. Move on.

- [ ] **Step 3: Add `--no-ci` flag to `bench_cli/compare/cli.py` AND wire per-row CI emission in `format_json`**

**Two file edits happen in this step.**

(A) **Extend `format_json()` to emit per-row CIs.** Find the JSON loop body in `bench_cli/compare/core.py::format_json` (lines 888–920 region per Phase 0's rewrite). The existing loop calls `_aggregate_model_pillars(data, model)` per row and copies the aggregator's AA / efficiency keys into the row dict. **Add `ci_low` and `ci_high`** to that copy:

```python
            agg = _aggregate_model_pillars(data, model)
            if agg is not None:
                for k in (
                    "cost_per_task", "tokens_per_task", "time_per_task",
                    "cost_per_suite", "tokens_per_suite", "time_per_suite",
                    "intelligence_per_dollar",
                    "intelligence_per_token",
                    "intelligence_per_token_total",
                    # NEW — emitted per-row from the model-level aggregator:
                    "ci_low", "ci_high",
                ):
                    v = agg[k]
                    if isinstance(v, float) and math.isnan(v):
                        v = None
                    row[k] = round(v, 4) if isinstance(v, float) else v
                ans_t = agg.get("answer_tokens_per_task")
                row["answer_tokens_per_task"] = (
                    round(ans_t, 1) if ans_t is not None else None
                )
                ans_s = agg.get("answer_tokens_per_suite")
                row["answer_tokens_per_suite"] = (
                    round(ans_s, 1) if ans_s is not None else None
                )
```

**Important:** the aggregator signature change (Phase 1 Task 3 Step 2) added `ci_low` and `ci_high` to the returned dict. If this step ships BEFORE Task 3, the test for `ci_low in row` will fail; ship Task 3 first or both in the same commit. The `format_json` signature gains `include_ci: bool = True` and the per-row block above only adds the keys when `include_ci=True`:

```python
def format_json(data: CompareData, legacy_weighted: bool = False, include_ci: bool = True) -> str:
```

(B) **Add `--no-ci` flag to `bench_cli/compare/cli.py`.**

```python
@click.option(
    "--no-ci",
    is_flag=True,
    default=False,
    help="Suppress bootstrap CI computation and rendering (faster).",
)
```

Change the `compare(...)` signature to add `no_ci: bool` and compute `include_ci = not no_ci`. Plumb into all 4 formatter invocations (`format_summary`, `format_pillar_table`, `format_compact_table`, `format_json`). With the format_json change from (A) above, `--no-ci` correctly suppresses per-row CI emission in JSON too.

- [ ] **Step 4: Run the CLI smoke test**

Run: `.venv/bin/python -m bench_cli compare --help | grep -i "no-ci"`
Expected: flag line shows `  --no-ci    Suppress bootstrap CI...`.

Run: `.venv/bin/python -m bench_cli compare --no-ci | head -c 400`
Expected: no `[lo, hi]` brackets in the output.

- [ ] **Step 5: Run full suite — confirm no regressions**

Run: `.venv/bin/pytest -q`
Expected: full suite green; total grew by 1 (the no_ci regression guard test).

- [ ] **Step 6: Commit**

```bash
git add bench_cli/compare/cli.py bench_cli/compare/core.py tests/test_compare.py
git commit -m "feat(compare): --no-ci flag plumbed to all renderers"
```

---

## Done Criteria

- [ ] All 4 tasks shipped as separate commits on `bench/main`.
- [ ] `bench compare` (default) shows `capability [CI_low, CI_high]` and `≈` ties for overlapping CIs.
- [ ] `bench compare --no-ci` suppresses CIs in all 3 text renderers and JSON.
- [ ] Partial-eval models render `[insufficient data]`, never `[NaN, NaN]`.
- [ ] Tie detection is pairwise, non-transitive (covered by `test_pairwise_not_transitive`).
- [ ] `.venv/bin/pytest -q` → green; net new tests for Phase 1 = 12 (4 bootstrap + 4 ties + 3 capability-rendering + 1 no-ci).
- [ ] SC traceability: SC1 (full), SC6, SC7 all pass; SC9 (preset router) lands in Phase 4.

## Out of Scope

- IRT ability CI (Phase 3) — distinct concept from performance CI; F3 mitigation explicitly labels them separately.
- Preset router that uses confidence overlaps (Phase 4) — that reads from the same `detect_ties()` helper but the consumer lands in the Phase 4 plan.
- Recorded-identity reconciliation lifting the `4940c0c8` implementation — Phase 3 prep, not Phase 1.
