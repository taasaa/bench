"""Tests for bench_cli.compare — pillar-table comparison formatting."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench_cli.compare import (  # noqa: E402
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
                correctness=0.9, token_ratio=1.5, time_ratio=1.2,
                avg_tokens=450.0, avg_time=3.5, samples=5,
            ),
            "model-y": PillarScores(
                correctness=0.7, token_ratio=0.8, time_ratio=0.9,
                avg_tokens=300.0, avg_time=2.1, samples=5,
            ),
        },
        "task_b": {
            "model-x": PillarScores(
                correctness=0.8, token_ratio=1.1, time_ratio=1.0,
                avg_tokens=500.0, avg_time=4.0, samples=5,
            ),
        },
    }
    return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPillarScores:
    def test_creation_defaults(self):
        ps = PillarScores(
            correctness=0.9, token_ratio=1.5, time_ratio=1.2,
            avg_tokens=450.0, avg_time=3.5, samples=5,
        )
        assert ps.correctness == 0.9
        assert ps.token_ratio == 1.5
        assert ps.time_ratio == 1.2
        assert ps.token_suppressed == 0  # default
        assert ps.time_suppressed == 0   # default


class TestCompareData:
    def test_empty(self):
        data = CompareData()
        assert data.tasks == []
        assert data.models == []

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

    def test_absolute_metrics_columns(self, two_model_data):
        result = format_pillar_table(two_model_data)
        assert "TOKENS" in result
        assert "TIME" in result

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
        for key in ("task", "model", "correctness", "token_ratio", "time_ratio",
                     "avg_tokens", "avg_time", "samples"):
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
                    correctness=0.6, token_ratio=0.9, time_ratio=1.0,
                    avg_tokens=150.0, avg_time=2.0, samples=1,
                ),
                "model-b": PillarScores(
                    correctness=0.8, token_ratio=1.2, time_ratio=1.1,
                    avg_tokens=100.0, avg_time=1.5, samples=1,
                ),
            },
        }
        assert set(data.models) == {"model-a", "model-b"}
        assert data.matrix["task-x"]["model-a"].correctness == 0.6
        assert data.matrix["task-x"]["model-b"].correctness == 0.8
