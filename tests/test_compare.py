"""Tests for bench_cli.compare — pivot-table comparison formatting."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench_cli.compare import (
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
        assert two_model_data.matrix["task_b"].get("model-y") is None  # no data for model-y on task_b
        assert two_model_data.matrix["task_b"]["model-x"].composite == 0.7


class TestFormatPivotTable:
    def test_empty_message(self, empty_data):
        result = format_pivot_table(empty_data, "composite")
        assert "No scored eval logs" in result

    def test_task_names_shown(self, two_model_data):
        result = format_pivot_table(two_model_data, "composite")
        assert "task_a" in result
        assert "task_b" in result

    def test_model_names_shortened(self, two_model_data):
        result = format_pivot_table(two_model_data, "composite")
        # model names should be shortened (openai/ prefix stripped by _short_model)
        assert "model-x" in result
        assert "model-y" in result

    def test_composite_values(self, two_model_data):
        result = format_pivot_table(two_model_data, "composite")
        # task_a / model-x has composite 0.75
        assert "task_a" in result
        # NaN/missing cells should show as "—"
        assert "—" in result  # task_b / model-y has no data

    def test_correctness_pillar(self, two_model_data):
        result = format_pivot_table(two_model_data, "correctness")
        assert "task_a" in result
        # model-x task_a has correctness 0.9

    def test_time_pillar(self, two_model_data):
        result = format_pivot_table(two_model_data, "time")
        assert "task_a" in result
        # time should be formatted as seconds

    def test_tokens_pillar(self, two_model_data):
        result = format_pivot_table(two_model_data, "tokens")
        assert "task_a" in result

    def test_speed_pillar(self, two_model_data):
        result = format_pivot_table(two_model_data, "speed")
        assert "task_a" in result

    def test_mean_row(self, two_model_data):
        result = format_pivot_table(two_model_data, "composite")
        assert "MEAN" in result


class TestFormatAllTables:
    def test_composite_section(self, two_model_data):
        result = format_all_tables(two_model_data)
        assert "COMPOSITE" in result

    def test_correctness_section(self, two_model_data):
        result = format_all_tables(two_model_data)
        assert "CORRECTNESS" in result

    def test_tokens_section(self, two_model_data):
        result = format_all_tables(two_model_data)
        # Should have tokens section
        assert "TOKENS" in result

    def test_time_section(self, two_model_data):
        result = format_all_tables(two_model_data)
        assert "TIME" in result

    def test_speed_section(self, two_model_data):
        result = format_all_tables(two_model_data)
        assert "TOKENS/SEC" in result


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
        assert "avg_time" in row
        assert "tokens_per_sec" in row
        assert "samples" in row


class TestLoadCompareData:
    def test_empty_dir_returns_empty(self, tmp_path):
        """load_compare_data should return empty data for empty dir."""
        data = load_compare_data(str(tmp_path))
        assert data.tasks == []
        assert data.models == []
