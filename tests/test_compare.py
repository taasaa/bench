"""Tests for bench_cli.compare — pillar-table comparison formatting."""

from __future__ import annotations

import pytest

from bench_cli.compare import (
    CompareData,
    PillarScores,
    format_json,
    format_pillar_table,
    load_compare_data,
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
    """W3c: legend names the reference model; defaults when none registered."""
    from scorers import reference_model as rm
    from bench_cli.compare.core import _ratio_reference_labels

    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")  # none registered
    labels = _ratio_reference_labels()
    assert "qwen-local" in labels["efficiency_latency"]  # SYSTEM_DEFAULT calibration source
    assert "minimax-m2.7" in labels["cost"]  # task_budgets reference source

    rm.set_reference_model_id("openai/minimax-m3")
    labels = _ratio_reference_labels()
    assert labels["efficiency_latency"] == "openai/minimax-m3"
    assert labels["cost"] == "openai/minimax-m3"
