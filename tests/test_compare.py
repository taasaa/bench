"""Tests for bench_cli.compare — pillar-table comparison formatting."""

from __future__ import annotations

import math

import pytest

from bench_cli.compare import (
    CompareData,
    PillarScores,
    format_compact_table,
    format_json,
    format_pillar_table,
    format_summary,
    load_compare_data,
    MIN_FULL_EVAL_TASKS,
)
from bench_cli.compare.core import (
    WEIGHT_CORRECTNESS,
    WEIGHT_PRICE_RATIO,
    WEIGHT_TIME_RATIO,
    WEIGHT_TOKEN_RATIO,
    _aggregate_model_pillars,
    _weighted_total,
)

# ---------------------------------------------------------------------------
# Test data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_data():
    return CompareData()


@pytest.fixture
def two_model_data():
    """Two models, two tasks."""
    data = CompareData()
    data.tasks = ["task_a", "task_b"]
    data.models = ["model-x", "model-y"]
    data.matrix = {
        "task_a": {
            "model-x": PillarScores(
                correctness=0.9,
                token_ratio=1.5,
                time_ratio=1.2,
                avg_tokens=450.0,
                avg_time=3.5,
                samples=5,
            ),
            "model-y": PillarScores(
                correctness=0.7,
                token_ratio=0.8,
                time_ratio=0.9,
                avg_tokens=300.0,
                avg_time=2.1,
                samples=5,
            ),
        },
        "task_b": {
            "model-x": PillarScores(
                correctness=0.8,
                token_ratio=1.1,
                time_ratio=1.0,
                avg_tokens=500.0,
                avg_time=4.0,
                samples=5,
            ),
        },
    }
    return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompareData:
    def test_matrix_access(self, two_model_data):
        assert two_model_data.matrix["task_a"]["model-x"].correctness == 0.9
        assert two_model_data.matrix["task_b"].get("model-y") is None
        assert two_model_data.matrix["task_b"]["model-x"].correctness == 0.8


class TestFormatPillarTable:
    def test_empty_message(self, empty_data):
        result = format_pillar_table(empty_data)
        assert "No scored eval logs" in result

    def test_task_names_shown(self, two_model_data):
        result = format_pillar_table(two_model_data, "BENCHMARK RESULTS")
        assert "task_a" in result
        assert "task_b" in result

    def test_model_names_shown(self, two_model_data):
        result = format_pillar_table(two_model_data)
        assert "model-x" in result
        assert "model-y" in result

    def test_pillar_columns_present(self, two_model_data):
        result = format_pillar_table(two_model_data)
        assert "CORRECT" in result
        assert "TOK_RATIO" in result
        assert "TIME_RATIO" in result

    def test_mean_row(self, two_model_data):
        result = format_pillar_table(two_model_data)
        assert "MEAN" in result

    def test_missing_cell_dash(self, two_model_data):
        result = format_pillar_table(two_model_data)
        assert "—" in result  # missing cells for model-y/task_b


class TestFormatJson:
    def test_empty(self, empty_data):
        result = format_json(empty_data)
        assert result == "[]"

    def test_task_model_score(self, two_model_data):
        result = format_json(two_model_data)
        import json

        rows = json.loads(result)
        assert len(rows) == 3
        row = next(r for r in rows if r["task"] == "task_a" and r["model"] == "model-x")
        assert row["correctness"] == 0.9
        assert row["token_ratio"] == 1.5

    def test_all_fields_present(self, two_model_data):
        result = format_json(two_model_data)
        import json

        rows = json.loads(result)
        row = rows[0]
        for key in (
            "task",
            "model",
            "correctness",
            "token_ratio",
            "time_ratio",
            "avg_tokens",
            "avg_time",
            "samples",
        ):
            assert key in row, f"Missing field: {key}"


class TestLoadCompareData:
    def test_empty_dir_returns_empty(self, tmp_path):
        data = load_compare_data(str(tmp_path))
        assert data.tasks == []
        assert data.models == []

    def test_multiple_models_same_task(self):
        """Multiple models for same task — each shown in columns."""
        data = CompareData()
        data.tasks = ["task-x"]
        data.models = ["model-a", "model-b"]
        data.matrix = {
            "task-x": {
                "model-a": PillarScores(
                    correctness=0.6,
                    token_ratio=0.9,
                    time_ratio=1.0,
                    avg_tokens=150.0,
                    avg_time=2.0,
                    samples=1,
                ),
                "model-b": PillarScores(
                    correctness=0.8,
                    token_ratio=1.2,
                    time_ratio=1.1,
                    avg_tokens=100.0,
                    avg_time=1.5,
                    samples=1,
                ),
            },
        }
        assert set(data.models) == {"model-a", "model-b"}
        assert data.matrix["task-x"]["model-a"].correctness == 0.6
        assert data.matrix["task-x"]["model-b"].correctness == 0.8


# ---------------------------------------------------------------------------
# W3a/W3c: ratio recomputation + reference labels
# ---------------------------------------------------------------------------


def test_recompute_token_time_ratios_from_budget(tmp_path, monkeypatch):
    """W3a: token/time ratios recomputed at view time; no reference -> budget tier."""
    from scorers import reference_model as rm
    from scorers.task_budgets import get_task_budget
    from scorers.ratio_recompute import recompute_token_ratio, recompute_time_ratio

    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")  # no reference -> budget tier
    budget = get_task_budget("add_tests")  # output_tokens=508
    assert recompute_token_ratio(baseline_store=None, task="add_tests", avg_tokens=1016, budget=budget) == 0.5
    assert (
        recompute_time_ratio(baseline_store=None, task="add_tests", avg_time=34.0, budget=budget)
        != float("nan")
    )


def test_recompute_uses_reference_baseline_when_registered(tmp_path, monkeypatch):
    """W3a + Goal #5: a registered reference baseline wins over task_budget for ALL subjects."""
    from scorers import reference_model as rm
    from scorers.baseline_store import BaselineStore, Baseline
    from scorers.task_budgets import get_task_budget
    from scorers.ratio_recompute import recompute_token_ratio

    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")
    rm.set_reference_model_id("openai/minimax-m3")
    store = BaselineStore(str(tmp_path / "baselines"))
    store.save(
        Baseline(
            task_id="add_tests",
            model_id="openai/minimax-m3",
            run_at="x",
            correctness=0.9,
            valid_for_reference=True,
            total_tokens=10,
            output_tokens=200,
        ),
        "add_tests",
        "openai/minimax-m3",
    )
    budget = get_task_budget("add_tests")  # output_tokens=508, must NOT win
    # reference 200 / actual 1016 != budget 508 / 1016 — proves the reference (not budget) is used
    assert (
        recompute_token_ratio(baseline_store=store, task="add_tests", avg_tokens=1016, budget=budget)
        == 200 / 1016
    )


def test_ratio_reference_labels_default_and_registered(tmp_path, monkeypatch):
    """W3c: legend names the reference model; defaults when none registered.

    Asserts the SHAPE (keys present, defaults are non-empty strings, registered
    reference wins when set) — not the specific model names, so re-baselining
    the calibration source doesn't break this test.
    """
    from scorers import reference_model as rm
    from bench_cli.compare.core import _ratio_reference_labels

    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")  # none registered
    labels = _ratio_reference_labels()
    assert set(labels.keys()) == {"efficiency_latency", "cost"}
    assert all(labels.values()), f"default labels must be non-empty: {labels}"

    rm.set_reference_model_id("openai/test-reference-model")
    labels = _ratio_reference_labels()
    assert labels["efficiency_latency"] == "openai/test-reference-model"
    assert labels["cost"] == "openai/test-reference-model"


# ---------------------------------------------------------------------------
# Weighted leaderboard (2026-07-10)
# ---------------------------------------------------------------------------


def _make_full_eval_model(
    correctness=0.8, price=1.0, time=1.0, token=1.0, n=46, model_name="m_full"
):
    """Build a CompareData matrix holding one model with `n` identically-scored tasks."""
    data = CompareData()
    data.tasks = [f"task_{i:02d}" for i in range(n)]
    data.models = [model_name]
    data.matrix = {
        task: {
            model_name: PillarScores(
                correctness=correctness,
                token_ratio=token,
                time_ratio=time,
                avg_tokens=1000.0,
                avg_time=10.0,
                samples=1,
                price_ratio=price,
                avg_cost_usd=0.001,
            )
        }
        for task in data.tasks
    }
    return data


def _make_partial_model(n=4, model_name="m_partial"):
    """Build a CompareData matrix holding one model with `n` scored tasks."""
    return _make_full_eval_model(n=n, model_name=model_name)


def test_weights_sum_to_one():
    assert WEIGHT_CORRECTNESS + WEIGHT_PRICE_RATIO + WEIGHT_TIME_RATIO + WEIGHT_TOKEN_RATIO == 1.0


def test_min_full_eval_tasks_is_46():
    assert MIN_FULL_EVAL_TASKS == 46


def test_aggregate_model_pillars_returns_none_when_no_scored_tasks():
    data = CompareData()
    data.tasks = ["t1"]
    data.models = ["m"]
    data.matrix = {"t1": {}}  # no entry → no correctness
    assert _aggregate_model_pillars(data, "m") is None


def test_aggregate_model_pillars_handles_missing_ratios():
    """Ratios default to 1.0 (neutral) when no task has a valid value."""
    data = _make_full_eval_model(correctness=0.5, price=float("nan"), time=2.0, token=1.0)
    agg = _aggregate_model_pillars(data, "m_full")
    assert agg is not None
    assert agg["correct_mean"] == 0.5
    assert agg["price_ratio_gm"] == 1.0  # defaulted (no valid price)
    assert agg["time_ratio_gm"] == 2.0
    assert agg["token_ratio_gm"] == 1.0


def test_weighted_total_uses_blend():
    agg = {
        "correct_mean": 0.8,
        "price_ratio_gm": 1.0,
        "time_ratio_gm": 1.0,
        "token_ratio_gm": 1.0,
    }
    # total = 0.5*0.8 + 0.2*1 + 0.15*1 + 0.15*1 = 0.4 + 0.5 = 0.9
    assert abs(_weighted_total(agg) - 0.9) < 1e-9


def test_weighted_total_with_better_than_bench_ratios():
    agg = {
        "correct_mean": 0.6,
        "price_ratio_gm": 2.0,
        "time_ratio_gm": 2.0,
        "token_ratio_gm": 2.0,
    }
    # total = 0.5*0.6 + 0.2*2 + 0.15*2 + 0.15*2 = 0.3 + 1.0 = 1.3
    assert abs(_weighted_total(agg) - 1.3) < 1e-9


def test_weighted_total_handles_default_ratios():
    """Missing ratios default to 1.0, so they don't tank a 0-correct model."""
    agg = {
        "correct_mean": 0.0,
        "price_ratio_gm": 1.0,
        "time_ratio_gm": 1.0,
        "token_ratio_gm": 1.0,
    }
    # total = 0.0 + 0.5 = 0.5 (not lower than 0.5)
    assert abs(_weighted_total(agg) - 0.5) < 1e-9


# ---- format_summary ----------------------------------------------------


def test_format_summary_excludes_partial_by_default():
    """A model with only 4 tasks must NOT appear in the ranked summary by default."""
    full = _make_full_eval_model(correctness=0.7, model_name="m_full", n=46)
    partial = _make_partial_model(n=4, model_name="m_partial")

    data = CompareData()
    data.tasks = full.tasks + [t for t in partial.tasks if t not in full.tasks]
    data.models = ["m_full", "m_partial"]
    data.matrix = {t: dict(full.matrix.get(t, {})) for t in full.tasks}
    for t in partial.tasks:
        data.matrix.setdefault(t, {})["m_partial"] = partial.matrix[t]["m_partial"]

    out = format_summary(data)
    assert "m_full" in out
    assert "m_partial" not in out  # excluded by default
    assert "EXCLUDED" not in out  # no partial section when not requested


def test_format_summary_show_partial_renders_footer_block():
    full = _make_full_eval_model(correctness=0.7, model_name="m_full", n=46)
    partial_data = _make_full_eval_model(correctness=0.5, model_name="m_partial", n=4)

    data = CompareData()
    data.tasks = full.tasks + [t for t in partial_data.tasks if t not in full.tasks]
    data.models = ["m_full", "m_partial"]
    data.matrix = {t: dict(full.matrix.get(t, {})) for t in full.tasks}
    for t in partial_data.tasks:
        data.matrix.setdefault(t, {})["m_partial"] = partial_data.matrix[t]["m_partial"]

    out = format_summary(data, min_tasks=46, show_partial=True, legacy_weighted=True)
    assert "m_partial" in out
    assert "Not full eval" in out  # partial footer present (legacy view)


def test_format_summary_ranking_uses_weighted_score():
    """Two models with same correctness but different cost ratios should rank differently."""
    cheap = _make_full_eval_model(correctness=0.7, price=2.0, model_name="cheap", n=46)
    expensive = _make_full_eval_model(correctness=0.7, price=0.5, model_name="expensive", n=46)

    data = CompareData()
    data.tasks = cheap.tasks
    data.models = ["cheap", "expensive"]
    data.matrix = {}
    for t in cheap.tasks:
        data.matrix[t] = {
            "cheap": cheap.matrix[t]["cheap"],
            "expensive": expensive.matrix[t]["expensive"],
        }

    out = format_summary(data, legacy_weighted=True)
    lines = [l for l in out.split("\n") if l.strip().startswith("#")]
    assert "cheap" in lines[0], f"cheaper model should rank first, got: {lines}"
    assert "expensive" in lines[1]


def test_format_summary_uses_0_5_0_2_0_15_0_15_formula_in_header():
    """Legacy weighted view shows the historical 0.5/0.2/0.15/0.15 header formula."""
    data = _make_full_eval_model(correctness=0.8)
    out = format_summary(data, legacy_weighted=True)
    assert "0.50×correct" in out
    assert "0.20×price_ratio" in out
    assert "0.15×time_ratio" in out
    assert "0.15×token_ratio" in out


def test_format_summary_min_tasks_respected():
    """A 46-task model is excluded when min_tasks=48."""
    data = _make_full_eval_model(correctness=0.8)
    out = format_summary(data, min_tasks=48, legacy_weighted=True)
    assert "m_full" not in out
    # Header announces 0 full evals when the only model is below min_tasks.
    assert "0 full evals" in out


# ---- format_compact_table ---------------------------------------------


def test_format_compact_table_excludes_partial():
    """The -v grid must only show full-eval models."""
    full = _make_full_eval_model(correctness=0.7, model_name="m_full", n=46)
    partial_data = _make_full_eval_model(correctness=0.5, model_name="m_partial", n=4)

    data = CompareData()
    data.tasks = full.tasks + [t for t in partial_data.tasks if t not in full.tasks]
    data.models = ["m_full", "m_partial"]
    data.matrix = {t: dict(full.matrix.get(t, {})) for t in full.tasks}
    for t in partial_data.tasks:
        data.matrix.setdefault(t, {})["m_partial"] = partial_data.matrix[t]["m_partial"]

    out = format_compact_table(data, legacy_weighted=True)
    assert "m_full" in out
    assert "m_partial" not in out
    assert "TOTAL" in out  # weighted TOTAL row present
    assert "0.50×correct" in out  # formula footer present


# ---- format_pillar_table TOTAL row -----------------------------------


def test_format_pillar_table_total_row_present():
    """Legacy view: the full table renders a TOTAL row with the weighted blend."""
    data = _make_full_eval_model(correctness=0.8)
    out = format_pillar_table(data, "BENCHMARK RESULTS", legacy_weighted=True)
    assert "TOTAL" in out
    # TOTAL row should show one nonzero value (~0.9 for correct=0.8, ratios=1.0)
    total_idx = [i for i, l in enumerate(out.split("\n")) if l.startswith("TOTAL")][0]
    # The TOTAL row's first column after the label is the blended total
    # We expect 0.90 (since 0.5*0.8 + 0.5*1.0 = 0.9)
    assert "0.90" in out.split("\n")[total_idx] or "0.9" in out.split("\n")[total_idx]


def test_format_pillar_table_total_handles_missing_ratios():
    """Legacy view: total falls back to defaults (1.0) when ratios are absent."""
    data = _make_full_eval_model(correctness=0.5, price=float("nan"))
    out = format_pillar_table(data, "BENCHMARK RESULTS", legacy_weighted=True)
    # total = 0.5*0.5 + 0.5*1.0 (no valid ratios → default to 1.0) = 0.75
    assert "0.75" in out


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
    out = format_summary(data, min_tasks=1)
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
    out = format_summary(data, min_tasks=1)
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
    out = format_summary(data, min_tasks=1)
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
    out = format_summary(data, min_tasks=1)
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
    out = format_summary(data, min_tasks=1)
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
    out = format_summary(data, min_tasks=1)
    assert "int/tok" in out
    # 0.5 / 100 = 0.005 — the answer-only value must appear (the total-tokens
    # alternative would be 0.5 / 1000 = 0.0005, which the 2-decimal formatter
    # rounds to 0.00 and would be missing from the row). We assert the
    # answer-tokens value is rendered — `0.005` rounds to `0.01` at 2dp and
    # `0.0005` rounds to `0.00`, so the presence of `int/tok=0.01` confirms
    # answer tokens were used (the total-token path would have produced
    # `int/tok=0.00`).
    assert "int/tok=0.01" in out


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
    out = format_compact_table(data, min_tasks=1)
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
    out = format_compact_table(data, min_tasks=1, legacy_weighted=True)
    assert "TOTAL" in out
    assert "0.50×correct" in out or "0.5×correct" in out


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


# ---- bootstrap CI (Phase 1 Task 1) -----------------------------------------
from bench_cli.compare.bootstrap import bootstrap_ci


def test_bootstrap_ci_reproducible_with_fixed_seed():
    """SC6: bootstrap_ci returns the same bounds across runs when seed and inputs are identical."""
    scores = [0.9, 0.85, 0.7, 0.6, 0.55, 0.95, 0.8, 0.75, 0.65, 0.5] * 4  # 40 values
    a = bootstrap_ci(scores, n_resample=500, seed=42, min_n=30)
    b = bootstrap_ci(scores, n_resample=500, seed=42, min_n=30)
    assert a == b, "identical seed + inputs must produce identical CIs"
    lo, hi = a
    assert 0 <= lo <= hi <= 1


def test_bootstrap_ci_returns_none_when_too_few_tasks():
    """Edge case: a model with < min_n tasks cannot get a trustworthy CI; return None."""
    scores = [0.9, 0.85, 0.7, 0.6, 0.55, 0.95, 0.8]  # 7 items < 46
    assert bootstrap_ci(scores) is None


def test_bootstrap_ci_default_min_n_is_full_eval_threshold():
    """Invariant: default min_n matches MIN_FULL_EVAL_TASKS so a partial-eval model never gets a misleading CI."""
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


# ---- tie detection (Phase 1 Task 2) ---------------------------------------
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
    annotation must point to rank 1, not the predecessor.
    """
    # a [0.50, 0.99], b [0.20, 0.45], c [0.55, 0.95]
    # a↔b: a_hi=0.99 >= b_lo=0.20, b_hi=0.45 < a_lo=0.50 → disjoint. ✓
    # a↔c: a_hi=0.99 >= c_lo=0.55, c_hi=0.95 >= a_lo=0.50 → overlap. ✓
    # b↔c: b_hi=0.45 < c_lo=0.55 → disjoint. ✓
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
    # A: [60, 80], B: [50, 65], C: [40, 55]
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


# ---- capability rendering + tie badge (Phase 1 Task 3) --------------------
import re as _re


def test_capability_with_ci_renders_correctly():
    """SC6 (full): format_summary shows capability [CI_low, CI_high] when CI
    is available (>= 46 tasks)."""
    data = CompareData()
    data.tasks = [f"t{i}" for i in range(46)]
    data.models = ["m1"]
    # m1 correctness oscillates between 0.7 and 0.9 — bootstrap CI is well-defined.
    scores = [0.7 + (0.2 if i % 2 == 0 else 0.0) for i in range(46)]
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
        for i in range(46)
    }
    out = format_summary(data, include_ci=True)
    # Bracket form '[lo, hi]' with one decimal place.
    assert _re.search(r"\[\d+\.\d, \d+\.\d\]", out), f"expected CI bracket in:\n{out}"


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
    assert not _re.search(r"\[0\.\d, 0\.\d\]", out), \
        "partial-eval models must not render numeric CI brackets"


def test_tie_badge_in_renderer():
    """SC7 (full): two models with identical CIs cause the renderer to emit
    the '≈' badge with an annotation pointing to the highest-ranked partner.
    Identical correctness → identical bootstrap CIs → overlap is guaranteed."""
    data = CompareData()
    data.tasks = [f"t{i}" for i in range(46)]
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
        for i in range(46)
    }
    out = format_summary(data, include_ci=True)
    assert "≈" in out
    # Annotation must reference #1 (highest-ranked partner, the only other
    # model in this fixture).
    assert "tied with #1" in out


# ---- --no-ci regression guard (Phase 1 Task 4) --------------------------
def test_format_summary_no_ci_omits_brackets():
    """--no-ci path: include_ci=False drops the numeric CI bracket entirely
    (insufficient-data fallback may stay, since it carries no numeric value)."""
    import re as _re_no_ci
    data = CompareData()
    data.tasks = [f"t{i}" for i in range(46)]
    data.models = ["m1"]
    data.matrix = {
        f"t{i}": {
            "m1": PillarScores(
                correctness=0.85,
                token_ratio=1.0, time_ratio=1.0,
                avg_tokens=100, avg_time=1.0, samples=1,
            )
        }
        for i in range(46)
    }
    out = format_summary(data, include_ci=False)
    # No numeric bracket pattern "[<digit>" should appear (catches CI and
    # any future numeric brackets).
    assert _re_no_ci.search(r"\[\d", out) is None, (
        f"numeric CI bracket leaked into no-CI output:\n{out}"
    )
    # Capability percentage still renders.
    assert "85" in out

