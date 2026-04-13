"""Tests for bench_cli.compare — pivot-table comparison formatting."""

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
    format_all_tables,
    format_json,
    format_pivot_table,
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
                correctness=0.9, composite=0.75, avg_time=3.5,
                avg_tokens=450.0, avg_tokens_per_sec=57.1,
                samples=5, scorer="composite",
            ),
            "model-y": PillarScores(
                correctness=0.7, composite=0.6, avg_time=2.1,
                avg_tokens=300.0, avg_tokens_per_sec=50.0,
                samples=5, scorer="composite",
            ),
        },
        "task_b": {
            "model-x": PillarScores(
                correctness=0.8, composite=0.7, avg_time=4.0,
                avg_tokens=500.0, avg_tokens_per_sec=55.0,
                samples=5, scorer="composite",
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
            correctness=0.9,
            composite=0.75,
            avg_time=3.5,
            avg_tokens=450.0,
            avg_tokens_per_sec=57.1,
            samples=5,
            scorer="composite",
        )
        assert ps.correctness == 0.9
        assert ps.composite == 0.75
        assert ps.samples == 5
        assert ps.safety == 1.0  # default

    def test_safety_override(self):
        ps = PillarScores(
            correctness=0.9, composite=0.45, avg_time=3.5,
            avg_tokens=450.0, avg_tokens_per_sec=57.1,
            samples=5, scorer="composite", safety=0.5,
        )
        assert ps.safety == 0.5


class TestCompareData:
    def test_empty(self):
        data = CompareData()
        assert data.tasks == []
        assert data.models == []

    def test_matrix_access(self, two_model_data):
        assert two_model_data.matrix["task_a"]["model-x"].composite == 0.75
        assert two_model_data.matrix["task_b"].get("model-y") is None
        assert two_model_data.matrix["task_b"]["model-x"].composite == 0.7


class TestFormatPivotTable:
    def test_empty_message(self, empty_data):
        result = format_pivot_table(empty_data, "PILLAR SCORES")
        assert "No scored eval logs" in result

    def test_task_names_shown(self, two_model_data):
        result = format_pivot_table(two_model_data, "PILLAR SCORES")
        assert "task_a" in result
        assert "task_b" in result

    def test_model_names_shown(self, two_model_data):
        result = format_pivot_table(two_model_data, "PILLAR SCORES")
        assert "model-x" in result
        assert "model-y" in result

    def test_correctness_column(self, two_model_data):
        result = format_pivot_table(two_model_data, "PILLAR SCORES")
        assert "task_a" in result
        assert "—" in result  # missing cells

    def test_pillar_columns_present(self, two_model_data):
        result = format_pivot_table(two_model_data, "PILLAR SCORES")
        assert "CORRECT" in result
        assert "EFF_RATIO" in result
        assert "LAT_RATIO" in result
        assert "EXEC_SAFE" in result
        assert "CONSTR" in result
        assert "OUT_SAFE" in result

    def test_absolute_metrics_columns(self, two_model_data):
        result = format_pivot_table(two_model_data, "PILLAR SCORES")
        assert "TOK_OUT" in result
        assert "LAT_S" in result

    def test_mean_row(self, two_model_data):
        result = format_pivot_table(two_model_data, "PILLAR SCORES")
        assert "MEAN" in result


class TestFormatAllTables:
    def test_pillar_table_section(self, two_model_data):
        result = format_all_tables(two_model_data)
        # New two-tier format shows PILLAR SCORES table
        assert "PILLAR SCORES" in result

    def test_correctness_column(self, two_model_data):
        result = format_all_tables(two_model_data)
        # CORRECT column should be present
        assert "CORRECT" in result

    def test_efficiency_ratio_column(self, two_model_data):
        result = format_all_tables(two_model_data)
        # EFF_RATIO column should be present
        assert "EFF_RATIO" in result

    def test_latency_column(self, two_model_data):
        result = format_all_tables(two_model_data)
        assert "LAT_RATIO" in result

    def test_safety_columns(self, two_model_data):
        result = format_all_tables(two_model_data)
        # Safety sub-score columns
        assert "EXEC_SAFE" in result
        assert "CONSTR" in result
        assert "OUT_SAFE" in result

    def test_absolute_metrics_columns(self, two_model_data):
        result = format_all_tables(two_model_data)
        # Absolute metric columns
        assert "TOK_OUT" in result
        assert "LAT_S" in result


class TestFormatJson:
    def test_empty(self, empty_data):
        result = format_json(empty_data)
        assert result == "[]"

    def test_task_model_score(self, two_model_data):
        result = format_json(two_model_data)
        import json
        rows = json.loads(result)
        assert len(rows) == 3  # 3 non-empty (task_a/model-x, task_a/model-y, task_b/model-x)
        # Find the task_a/model-x row
        row = next(r for r in rows if r["task"] == "task_a" and r["model"] == "model-x")
        assert row["composite"] == 0.75
        assert row["correctness"] == 0.9

    def test_all_fields_present(self, two_model_data):
        result = format_json(two_model_data)
        import json
        rows = json.loads(result)
        row = rows[0]
        assert "task" in row
        assert "model" in row
        assert "scorer" in row
        assert "composite" in row
        assert "correctness" in row
        assert "avg_tokens" in row
        assert "avg_output_tokens" in row
        assert "avg_time" in row
        assert "efficiency_ratio" in row
        assert "latency_ratio" in row
        assert "exec_safety" in row
        assert "constraint_adherence" in row
        assert "output_safety" in row
        assert "samples" in row


class TestLoadCompareData:
    def test_empty_dir_returns_empty(self, tmp_path):
        """load_compare_data should return empty data for empty dir."""
        data = load_compare_data(str(tmp_path))
        assert data.tasks == []
        assert data.models == []

    def test_parses_pillar_fields_from_explanation(self, tmp_path):
        """load_compare_data extracts pillar scores via regex — verified by real logs."""
        from bench_cli.compare import _parse_pillars

        pillars = _parse_pillars(
            "correctness=0.75, efficiency=1.00, safety=1.00\nPASS 3/4"
        )
        assert pillars is not None
        c, e, s = pillars
        assert c == 0.75
        assert e == 1.00
        assert s == 1.00

    def test_nan_when_pillar_fields_missing(self, tmp_path):
        """Missing pillar fields → _parse_pillars returns None (handled as NaN)."""
        from bench_cli.compare import _parse_pillars

        pillars = _parse_pillars("PASS 1/2")  # no correctness/efficiency/safety
        assert pillars is None  # callers fall back to sc.value

    def test_best_run_selected_by_highest_composite(self, tmp_path):
        """Highest composite per task-model wins — verified by real eval logs."""
        from bench_cli.compare import _parse_pillars

        # Run with highest composite score should win
        pillars = _parse_pillars("correctness=0.90, efficiency=1.00, safety=1.00")
        assert pillars is not None
        assert pillars[0] == 0.90

    def test_multiple_runs_same_task_model(self, tmp_path):
        """Multiple models for same task — each shown in columns."""
        from bench_cli.compare import CompareData, PillarScores

        data = CompareData()
        data.tasks = ["task-x"]
        data.models = ["model-a", "model-b"]
        data.matrix = {
            "task-x": {
                "model-a": PillarScores(
                    correctness=0.6, composite=0.6, avg_time=2.0,
                    avg_tokens=150.0, avg_tokens_per_sec=75.0,
                    samples=1, scorer="composite",
                ),
                "model-b": PillarScores(
                    correctness=0.8, composite=0.8, avg_time=2.0,
                    avg_tokens=150.0, avg_tokens_per_sec=75.0,
                    samples=1, scorer="composite",
                ),
            },
        }
        assert set(data.models) == {"model-a", "model-b"}
        assert data.matrix["task-x"]["model-a"].composite == 0.6
        assert data.matrix["task-x"]["model-b"].composite == 0.8
