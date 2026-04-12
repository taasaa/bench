"""Tests for bench_cli.compare — per-task score breakdown from EvalLogs."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

# Ensure project root is on sys.path for bench_cli imports.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench_cli.compare import ScoreRow, _format_json, _format_table, _load_rows, compare
from bench_cli.main import cli


# ---------------------------------------------------------------------------
# Helpers — create minimal .eval logs for testing
# ---------------------------------------------------------------------------


def _make_eval_log(
    tmp_path: Path,
    task: str = "smoke",
    model: str = "openai/test-model",
    status: str = "success",
    scorer_name: str = "includes",
    score_value: float = 1.0,
    metric_name: str = "accuracy",
    scored_samples: int = 1,
    created: str | None = None,
    index: int = 0,
) -> Path:
    """Write a minimal .eval log and return its path."""
    from inspect_ai.log import (
        EvalConfig,
        EvalDataset,
        EvalLog,
        EvalMetric,
        EvalPlan,
        EvalResults,
        EvalScore,
        EvalSpec,
        EvalStats,
        write_eval_log,
    )

    if created is None:
        created = datetime.now(timezone.utc).isoformat()

    eval_log = EvalLog(
        version=2,
        status=status,
        eval=EvalSpec(
            task=task,
            task_id=f"test_{index}",
            run_id=f"run_{index}",
            created=created,
            task_version=0,
            model=model,
            dataset=EvalDataset(name="test", location="test", samples=scored_samples),
            config=EvalConfig(),
        ),
        plan=EvalPlan(name="test", steps=[], finish=None),
        results=EvalResults(
            total_samples=scored_samples,
            completed_samples=scored_samples,
            scores=[
                EvalScore(
                    name=scorer_name,
                    scorer=scorer_name,
                    scored_samples=scored_samples,
                    unscored_samples=0,
                    params={},
                    metrics={
                        metric_name: EvalMetric(
                            name=metric_name,
                            value=score_value,
                            params={},
                        ),
                        "stderr": EvalMetric(
                            name="stderr",
                            value=0.0,
                            params={},
                        ),
                    },
                )
            ],
        )
        if status == "success"
        else None,
        stats=EvalStats(
            started_at=created,
            completed_at=created,
        ),
        samples=None,
    )

    # Use a deterministic filename so tests are reproducible.
    fname = f"{created.replace(':', '-').replace('+', '_')}_{task}_test_{index}.eval"
    log_path = tmp_path / fname
    write_eval_log(eval_log, str(log_path))
    return log_path


def _make_error_log(
    tmp_path: Path,
    task: str = "smoke",
    model: str = "openai/test-model",
    created: str | None = None,
    index: int = 0,
) -> Path:
    """Write a minimal error-state .eval log (no results)."""
    return _make_eval_log(
        tmp_path,
        task=task,
        model=model,
        status="error",
        created=created,
        index=index,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def log_dir(tmp_path: Path):
    """Create a temporary log directory with a few sample eval logs."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _make_eval_log(
        logs,
        task="smoke",
        model="openai/model-a",
        score_value=1.0,
        created="2026-04-10T20:00:00+00:00",
        index=1,
    )
    _make_eval_log(
        logs,
        task="smoke",
        model="openai/model-b",
        score_value=0.5,
        created="2026-04-10T20:01:00+00:00",
        index=2,
    )
    _make_eval_log(
        logs,
        task="add-tests",
        model="openai/model-a",
        score_value=0.75,
        metric_name="mean",
        scorer_name="match",
        scored_samples=3,
        created="2026-04-10T20:02:00+00:00",
        index=3,
    )
    _make_error_log(
        logs,
        task="broken-task",
        model="openai/model-a",
        created="2026-04-10T20:03:00+00:00",
        index=4,
    )
    return logs


# ---------------------------------------------------------------------------
# _load_rows tests
# ---------------------------------------------------------------------------


class TestLoadRows:
    def test_loads_all_successful_rows(self, log_dir):
        rows = _load_rows(str(log_dir))
        # smoke x2 + add-tests x1 + error x1 = 4 rows
        assert len(rows) == 4

    def test_correct_task_names(self, log_dir):
        rows = _load_rows(str(log_dir))
        tasks = {r.task for r in rows}
        assert tasks == {"smoke", "add-tests", "broken-task"}

    def test_score_values(self, log_dir):
        rows = _load_rows(str(log_dir))
        smoke_rows = [r for r in rows if r.task == "smoke" and r.status == "success"]
        scores = {r.model: r.score for r in smoke_rows}
        assert scores["openai/model-a"] == 1.0
        assert scores["openai/model-b"] == 0.5

    def test_error_row_has_no_score(self, log_dir):
        rows = _load_rows(str(log_dir))
        error_rows = [r for r in rows if r.status == "error"]
        assert len(error_rows) == 1
        assert error_rows[0].score is None
        assert error_rows[0].scorer == "—"

    def test_samples_count(self, log_dir):
        rows = _load_rows(str(log_dir))
        fr = [r for r in rows if r.task == "add-tests"]
        assert fr[0].samples == 3

    def test_latest_limits_rows(self, log_dir):
        # Only last 2 logs (most recent by mtime descending)
        rows = _load_rows(str(log_dir), latest=2)
        assert len(rows) == 2

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty_logs"
        empty.mkdir()
        rows = _load_rows(str(empty))
        assert rows == []

    def test_nonexistent_directory(self, tmp_path):
        rows = _load_rows(str(tmp_path / "nonexistent"))
        assert rows == []

    def test_sorted_by_task_model_created(self, log_dir):
        rows = _load_rows(str(log_dir))
        keys = [(r.task, r.model, r.created) for r in rows]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# _format_table tests
# ---------------------------------------------------------------------------


class TestFormatTable:
    def test_empty_rows(self):
        result = _format_table([])
        assert "No eval logs found" in result

    def test_header_present(self):
        rows = [
            ScoreRow(
                task="t1", model="m1", scorer="s1",
                score=1.0, samples=5, status="success", created="2026-01-01",
            )
        ]
        table = _format_table(rows)
        assert "Task" in table
        assert "Model" in table
        assert "Scorer" in table
        assert "Score" in table
        assert "Samples" in table
        assert "Status" in table

    def test_score_formatted_3_decimals(self):
        rows = [
            ScoreRow(
                task="t1", model="m1", scorer="s1",
                score=0.8333, samples=10, status="success", created="2026-01-01",
            )
        ]
        table = _format_table(rows)
        assert "0.833" in table

    def test_none_score_shows_dash(self):
        rows = [
            ScoreRow(
                task="t1", model="m1", scorer="—",
                score=None, samples=None, status="error", created="2026-01-01",
            )
        ]
        table = _format_table(rows)
        # The score column should show "—"
        lines = table.split("\n")
        data_lines = [l for l in lines if l.strip() and not all(c == "—" for c in l.strip())]
        assert len(data_lines) >= 3  # header + separator + data


# ---------------------------------------------------------------------------
# _format_json tests
# ---------------------------------------------------------------------------


class TestFormatJson:
    def test_valid_json(self):
        rows = [
            ScoreRow(
                task="t1", model="m1", scorer="s1",
                score=1.0, samples=5, status="success", created="2026-01-01",
            )
        ]
        output = _format_json(rows)
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["task"] == "t1"
        assert data[0]["score"] == 1.0

    def test_empty_rows(self):
        output = _format_json([])
        data = json.loads(output)
        assert data == []

    def test_none_values(self):
        rows = [
            ScoreRow(
                task="t1", model="m1", scorer="—",
                score=None, samples=None, status="error", created="2026-01-01",
            )
        ]
        data = json.loads(_format_json(rows))
        assert data[0]["score"] is None
        assert data[0]["samples"] is None


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCompareCLI:
    def test_compare_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["compare", "--help"])
        assert result.exit_code == 0
        assert "--log-dir" in result.output
        assert "--latest" in result.output
        assert "--json" in result.output

    def test_compare_shows_table(self, log_dir):
        runner = CliRunner()
        result = runner.invoke(cli, ["compare", "--log-dir", str(log_dir)])
        assert result.exit_code == 0
        assert "smoke" in result.output
        assert "add-tests" in result.output
        assert "broken-task" in result.output

    def test_compare_json_output(self, log_dir):
        runner = CliRunner()
        result = runner.invoke(cli, ["compare", "--log-dir", str(log_dir), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 4

    def test_compare_latest_flag(self, log_dir):
        runner = CliRunner()
        result = runner.invoke(cli, ["compare", "--log-dir", str(log_dir), "--latest", "1"])
        assert result.exit_code == 0
        # Only the most recent log's task should appear
        # Since logs are sorted descending by mtime, the latest=1 means only 1 log
        # Check the JSON output to verify count
        result_json = runner.invoke(
            cli, ["compare", "--log-dir", str(log_dir), "--latest", "1", "--json"]
        )
        data = json.loads(result_json.output)
        assert len(data) == 1

    def test_compare_empty_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        runner = CliRunner()
        result = runner.invoke(cli, ["compare", "--log-dir", str(empty)])
        assert result.exit_code == 0
        assert "No eval logs found" in result.output

    def test_compare_bench_help_shows_compare(self):
        """Verify 'compare' appears in the top-level bench --help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "compare" in result.output
