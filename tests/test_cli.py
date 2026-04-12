"""Tests for bench_cli: task discovery, tier filtering, and CLI invocation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

# Ensure project root is on sys.path for bench_cli imports.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench_cli.main import cli
from bench_cli.run import _discover_tasks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tasks_root(tmp_path: Path, monkeypatch):
    """Create a temporary tasks/ directory tree with fake task.py files."""
    tasks = tmp_path / "tasks"
    for d in [
        "verification/smoke",
        "verification/agent_smoke",
        "competence/add-tests",
    ]:
        (tasks / d).mkdir(parents=True)
        (tasks / d / "task.py").write_text("# task")
    monkeypatch.chdir(tmp_path)
    return tasks


# ---------------------------------------------------------------------------
# Task discovery
# ---------------------------------------------------------------------------


class TestDiscoverTasks:
    """Tests for _discover_tasks()."""

    def test_quick_tier_finds_verification_tasks(self, tasks_root):
        specs = _discover_tasks("quick")
        # Should find exactly 2 verification tasks
        assert len(specs) == 2
        assert all("verification" in s for s in specs)

    def test_full_tier_finds_eval_tasks(self, tasks_root):
        specs = _discover_tasks("full")
        # Should find competence (1: add-tests) task
        assert len(specs) == 1
        assert any("competence" in s for s in specs)
        # Should NOT include verification tasks
        assert not any("verification" in s for s in specs)

    def test_max_tasks_caps_results(self, tasks_root):
        specs = _discover_tasks("full", max_tasks=2)
        # Only 1 task exists (add-tests), so cap of 2 still returns 1
        assert len(specs) == 1

    def test_max_tasks_none_returns_all(self, tasks_root):
        specs = _discover_tasks("full", max_tasks=None)
        assert len(specs) == 1

    def test_max_tasks_zero_returns_empty(self, tasks_root):
        specs = _discover_tasks("full", max_tasks=0)
        assert len(specs) == 0

    def test_unknown_tier_raises(self, tasks_root):
        with pytest.raises(Exception, match="Unknown tier"):
            _discover_tasks("bogus")

    def test_specs_are_relative_paths(self, tasks_root):
        specs = _discover_tasks("quick")
        for s in specs:
            assert s.startswith("tasks/")
            assert s.endswith("task.py")

    def test_quick_tier_sorted(self, tasks_root):
        specs = _discover_tasks("quick")
        assert specs == sorted(specs)

    def test_full_tier_sorted(self, tasks_root):
        specs = _discover_tasks("full")
        assert specs == sorted(specs)

    def test_empty_dir_returns_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No tasks/ directory at all
        assert _discover_tasks("quick") == []


# ---------------------------------------------------------------------------
# CLI invocation (bench run --help, bench --help)
# ---------------------------------------------------------------------------


class TestCLIInvocation:
    """Smoke tests for the Click CLI."""

    def test_bench_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output

    def test_run_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--model" in result.output
        assert "--tier" in result.output
        assert "--agent" in result.output
        assert "--max-tasks" in result.output
        assert "--log-dir" in result.output

    def test_run_help_shows_defaults(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert "openai/rut-small" in result.output
        assert "quick" in result.output
        assert "logs" in result.output

    def test_bench_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestRunIntegration:
    """Integration tests that mock inspect_ai.eval to verify wiring."""

    def test_run_discovers_and_passes_specs(self, tasks_root):
        """Verify bench run discovers tasks and calls eval() with them."""
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            # Return a fake EvalLog-like object
            from types import SimpleNamespace

            fake_log = SimpleNamespace(
                status="success",
                eval=SimpleNamespace(task="smoke"),
                results=SimpleNamespace(
                    scores=[SimpleNamespace(metrics={"mean": SimpleNamespace(value=1.0)})]
                ),
            )
            mock_eval.return_value = [fake_log]

            result = runner.invoke(cli, ["run", "--model", "openai/rut-small", "--tier", "quick"])

        assert result.exit_code == 0, result.output
        mock_eval.assert_called_once()
        call_kwargs = mock_eval.call_args
        # Verify task specs were passed
        tasks_arg = call_kwargs.kwargs.get("tasks") or call_kwargs[1].get("tasks") or call_kwargs[0][0]
        assert len(tasks_arg) == 2
        # Verify model was passed
        assert call_kwargs.kwargs.get("model") == "openai/rut-small" or "openai/rut-small" in str(call_kwargs)

    def test_run_exits_1_on_error_status(self, tasks_root):
        """Verify non-zero exit when any eval task errors."""
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            from types import SimpleNamespace

            error_log = SimpleNamespace(
                status="error",
                eval=SimpleNamespace(task="smoke"),
                results=None,
            )
            mock_eval.return_value = [error_log]

            result = runner.invoke(cli, ["run", "--tier", "quick"])

        assert result.exit_code == 1

    def test_run_with_agent_flag(self, tasks_root):
        """Verify --agent passes a solver to eval()."""
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            with patch("bench_cli.run._resolve_agent_solver") as mock_solver:
                from types import SimpleNamespace

                mock_solver.return_value = "fake_solver"
                fake_log = SimpleNamespace(
                    status="success",
                    eval=SimpleNamespace(task="agent_smoke"),
                    results=None,
                )
                mock_eval.return_value = [fake_log]

                result = runner.invoke(cli, ["run", "--agent", "claude", "--tier", "quick"])

        assert result.exit_code == 0, result.output
        mock_solver.assert_called_once_with("claude")
        # Verify solver was passed to eval
        call_kwargs = mock_eval.call_args
        solver_arg = call_kwargs.kwargs.get("solver")
        assert solver_arg == "fake_solver"

    def test_run_no_tasks_exits_1(self, tmp_path, monkeypatch):
        """Tier with no matching tasks should exit with error."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "tasks").mkdir()

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--tier", "quick"])
        assert result.exit_code == 1
        assert "No tasks found" in result.output
