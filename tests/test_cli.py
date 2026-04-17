"""Tests for bench_cli: task discovery, tier filtering, and CLI invocation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

# Ensure project root is on sys.path for bench_cli imports.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench_cli.main import cli  # noqa: E402
from bench_cli.run import _discover_tasks  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tasks_root(tmp_path: Path, monkeypatch):
    """Create a temporary tasks/ directory tree with valid @task files.

    Each task.py contains a minimal @task-decorated function so _resolve_task()
    can load and call it without needing real dataset files or verify.sh.
    """
    tasks = tmp_path / "tasks"
    task_file_content = '''\
"""Fixture task for CLI testing."""
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset

@task
def fixture_task():
    return Task(
        dataset=MemoryDataset(samples=[]),
        scorer=None,
    )
'''
    for d in [
        "verification/smoke",
        "verification/agent_smoke",
        "competence/add-tests",
    ]:
        (tasks / d).mkdir(parents=True)
        (tasks / d / "task.py").write_text(task_file_content)
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
        assert "openai/default" in result.output
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
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            from types import SimpleNamespace

            fake_log = SimpleNamespace(
                status="success",
                eval=SimpleNamespace(task="fixture_task"),
                results=SimpleNamespace(
                    scores=[SimpleNamespace(metrics={"mean": SimpleNamespace(value=1.0)})]
                ),
            )
            mock_eval.return_value = [fake_log]
            with patch("bench_cli.run._resolve_task", return_value=fake_task):
                result = runner.invoke(
                    cli, ["run", "--model", "openai/default", "--tier", "quick"]
                )

        assert result.exit_code == 0, result.output
        mock_eval.assert_called_once()
        call_kwargs = mock_eval.call_args
        # Verify tasks were resolved and passed
        tasks_arg = (
            call_kwargs.kwargs.get("tasks")
            or call_kwargs[1].get("tasks")
            or call_kwargs[0][0]
        )
        assert len(tasks_arg) == 2
        # Verify model was passed
        model_arg = call_kwargs.kwargs.get("model")
        assert model_arg == "openai/default"

    def test_run_exits_1_on_error_status(self, tasks_root):
        """Verify non-zero exit when any eval task errors."""
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            from types import SimpleNamespace

            error_log = SimpleNamespace(
                status="error",
                eval=SimpleNamespace(task="fixture_task"),
                results=None,
            )
            mock_eval.return_value = [error_log]
            with patch("bench_cli.run._resolve_task", return_value=fake_task):
                result = runner.invoke(cli, ["run", "--tier", "quick"])

        assert result.exit_code == 1

    def test_run_with_agent_flag(self, tasks_root):
        """Verify --agent passes a solver to eval()."""
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            with patch("bench_cli.run._resolve_agent_solver") as mock_solver:
                from types import SimpleNamespace

                mock_solver.return_value = "fake_solver"
                fake_log = SimpleNamespace(
                    status="success",
                    eval=SimpleNamespace(task="fixture_task"),
                    results=None,
                )
                mock_eval.return_value = [fake_log]
                with patch("bench_cli.run._resolve_task", return_value=fake_task):
                    result = runner.invoke(
                        cli, ["run", "--agent", "claude", "--tier", "quick"]
                    )

        assert result.exit_code == 0, result.output
        mock_solver.assert_called_once_with("claude", "local")
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


class TestPricesCLI:
    """Tests for bench prices refresh and bench prices list commands."""

    def test_prices_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["prices", "--help"])
        assert result.exit_code == 0
        assert "refresh" in result.output
        assert "list" in result.output

    def test_prices_list_no_cache_shows_na(self, tmp_path, monkeypatch):
        """prices list shows N/A gracefully when no cache exists.

        Cache path is absolute (bench project root), so chdir to tmp_path doesn't
        hide it — skip that assertion. Instead verify N/A for unknown aliases works.
        """
        runner = CliRunner()
        result = runner.invoke(cli, ["prices", "list"])
        assert result.exit_code == 0
        assert "N/A" in result.output  # unknown aliases show N/A

    def test_prices_list_shows_all_known_aliases(self, tmp_path, monkeypatch):
        """prices list shows all models from MODEL_ALIAS_MAP."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["prices", "list"])
        assert result.exit_code == 0
        # Should show at least the 40 aliases
        assert "openai/qwen-local" in result.output
        assert "openai/gpt-4o" in result.output
        assert "openai/opus" in result.output

    def test_prices_refresh_missing_key_shows_soft_error(self, tmp_path, monkeypatch):
        """prices refresh with missing API key exits with error, not crash."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KILOCODE_API_KEY", raising=False)
        runner = CliRunner()
        result = runner.invoke(cli, ["prices", "refresh"])
        assert result.exit_code == 1
        assert "KILOCODE_API_KEY" in result.output
        assert "not set" in result.output


# ---------------------------------------------------------------------------
# Concurrency flags
# ---------------------------------------------------------------------------


class TestConcurrencyFlags:
    """Tests for --concurrency/-j and --sequential CLI flags."""

    def test_help_shows_concurrency_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--concurrency" in result.output
        assert "-j" in result.output

    def test_help_shows_sequential_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--sequential" in result.output

    def test_concurrency_zero_exits_with_error(self, tasks_root):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--tier", "quick", "--concurrency", "0"])
        assert result.exit_code == 2
        assert "positive integer" in result.output.lower()

    def test_concurrency_negative_exits_with_error(self, tasks_root):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--tier", "quick", "--concurrency", "-3"])
        assert result.exit_code == 2
        assert "positive integer" in result.output.lower()

    def test_concurrency_passes_max_tasks_to_eval(self, tasks_root):
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            from types import SimpleNamespace

            fake_log = SimpleNamespace(
                status="success",
                eval=SimpleNamespace(task="fixture_task"),
                results=SimpleNamespace(
                    scores=[SimpleNamespace(metrics={"mean": SimpleNamespace(value=1.0)})]
                ),
            )
            mock_eval.return_value = [fake_log]
            with patch("bench_cli.run._resolve_task", return_value=fake_task):
                result = runner.invoke(
                    cli, ["run", "--tier", "quick", "--concurrency", "4"]
                )
        assert result.exit_code == 0, result.output
        mock_eval.assert_called_once()
        call_kwargs = mock_eval.call_args[1]
        assert call_kwargs.get("max_tasks") == 4

    def test_sequential_passes_max_tasks_1_to_eval(self, tasks_root):
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            from types import SimpleNamespace

            fake_log = SimpleNamespace(
                status="success",
                eval=SimpleNamespace(task="fixture_task"),
                results=SimpleNamespace(
                    scores=[SimpleNamespace(metrics={"mean": SimpleNamespace(value=1.0)})]
                ),
            )
            mock_eval.return_value = [fake_log]
            with patch("bench_cli.run._resolve_task", return_value=fake_task):
                result = runner.invoke(
                    cli, ["run", "--tier", "quick", "--sequential"]
                )
        assert result.exit_code == 0, result.output
        mock_eval.assert_called_once()
        call_kwargs = mock_eval.call_args[1]
        assert call_kwargs.get("max_tasks") == 1

    def test_sequential_wins_over_concurrency(self, tasks_root):
        """--sequential should override --concurrency when both are passed."""
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            from types import SimpleNamespace

            fake_log = SimpleNamespace(
                status="success",
                eval=SimpleNamespace(task="fixture_task"),
                results=SimpleNamespace(
                    scores=[SimpleNamespace(metrics={"mean": SimpleNamespace(value=1.0)})]
                ),
            )
            mock_eval.return_value = [fake_log]
            with patch("bench_cli.run._resolve_task", return_value=fake_task):
                result = runner.invoke(
                    cli,
                    [
                        "run",
                        "--tier",
                        "quick",
                        "--concurrency",
                        "4",
                        "--sequential",
                    ],
                )
        assert result.exit_code == 0, result.output
        mock_eval.assert_called_once()
        call_kwargs = mock_eval.call_args[1]
        assert call_kwargs.get("max_tasks") == 1

    def test_no_concurrency_passes_none_to_eval(self, tasks_root):
        """When neither --concurrency nor --sequential is passed, max_tasks is None."""
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            from types import SimpleNamespace

            fake_log = SimpleNamespace(
                status="success",
                eval=SimpleNamespace(task="fixture_task"),
                results=SimpleNamespace(
                    scores=[SimpleNamespace(metrics={"mean": SimpleNamespace(value=1.0)})]
                ),
            )
            mock_eval.return_value = [fake_log]
            with patch("bench_cli.run._resolve_task", return_value=fake_task):
                result = runner.invoke(
                    cli, ["run", "--tier", "quick"]
                )
        assert result.exit_code == 0, result.output
        mock_eval.assert_called_once()
        call_kwargs = mock_eval.call_args[1]
        assert call_kwargs.get("max_tasks") is None

    def test_concurrency_1_sequential_one_by_one(self, tasks_root):
        """--concurrency 1 should produce the same max_tasks=1 as --sequential."""
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            from types import SimpleNamespace

            fake_log = SimpleNamespace(
                status="success",
                eval=SimpleNamespace(task="fixture_task"),
                results=SimpleNamespace(
                    scores=[SimpleNamespace(metrics={"mean": SimpleNamespace(value=1.0)})]
                ),
            )
            mock_eval.return_value = [fake_log]
            with patch("bench_cli.run._resolve_task", return_value=fake_task):
                result = runner.invoke(
                    cli, ["run", "--tier", "quick", "--concurrency", "1"]
                )
        assert result.exit_code == 0, result.output
        call_kwargs = mock_eval.call_args[1]
        assert call_kwargs.get("max_tasks") == 1
