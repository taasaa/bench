"""Tests for bench_cli: task discovery, tier filtering, and CLI invocation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from bench_cli.main import cli
from bench_cli.run import _discover_tasks

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


class TestRunIntegration:
    """Integration tests that mock inspect_ai.eval to verify wiring."""

    def test_run_discovers_and_passes_specs(self, tasks_root, monkeypatch):
        """Verify bench run discovers tasks and calls eval() with them."""
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
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
            with patch("bench_cli.run.cli._resolve_task", return_value=fake_task):
                with patch("bench_cli.run.cli.resolve_provider", return_value="test-provider"):
                    result = runner.invoke(
                        cli, ["run", "--model", "openai/default", "--tier", "quick"]
                    )

        assert result.exit_code == 0, result.output
        mock_eval.assert_called_once()
        call_kwargs = mock_eval.call_args
        # Verify tasks were resolved and passed
        tasks_arg = (
            call_kwargs.kwargs.get("tasks") or call_kwargs[1].get("tasks") or call_kwargs[0][0]
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
            with patch("bench_cli.run.cli._resolve_task", return_value=fake_task):
                result = runner.invoke(cli, ["run", "--tier", "quick"])

        assert result.exit_code == 1

    def test_run_with_agent_flag(self, tasks_root, monkeypatch):
        """Verify --agent passes a solver to eval()."""
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            with patch("bench_cli.run.cli._resolve_agent_solver") as mock_solver:
                from types import SimpleNamespace

                mock_solver.return_value = "fake_solver"
                fake_log = SimpleNamespace(
                    status="success",
                    eval=SimpleNamespace(task="fixture_task"),
                    results=None,
                )
                mock_eval.return_value = [fake_log]
                with patch("bench_cli.run.cli._resolve_task", return_value=fake_task):
                    with patch("bench_cli.run.cli.resolve_provider", return_value="test-provider"):
                        result = runner.invoke(cli, ["run", "--agent", "claude", "--tier", "quick"])

        assert result.exit_code == 0, result.output
        mock_solver.assert_called_once_with("claude", "local", cc_model=None)
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


def _run_with_mocked_eval(tasks_root, monkeypatch, extra_args):
    """Invoke `bench run --tier quick` with inspect_ai.eval mocked.

    Returns (result, mock_eval) so callers can assert on call_args.
    Mirrors the wiring test pattern in TestRunIntegration.
    """
    from inspect_ai import Task
    from types import SimpleNamespace

    fake_task = Task(dataset=None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    runner = CliRunner()
    with patch("inspect_ai.eval") as mock_eval:
        fake_log = SimpleNamespace(
            status="success",
            eval=SimpleNamespace(task="fixture_task"),
            results=SimpleNamespace(
                scores=[SimpleNamespace(metrics={"mean": SimpleNamespace(value=1.0)})]
            ),
        )
        mock_eval.return_value = [fake_log]
        with patch("bench_cli.run.cli._resolve_task", return_value=fake_task):
            with patch("bench_cli.run.cli._check_price_gate"):
                with patch("bench_cli.run.cli.resolve_provider", return_value="test-provider"):
                    result = runner.invoke(
                        cli,
                        ["run", "--model", "openai/default", "--tier", "quick"] + list(extra_args),
                    )
    return result, mock_eval


class TestRunSampleConcurrency:
    """P0 fix (SB task a69a58d4): programmatic inspect_eval() must thread
    max_samples + bounded max_retries, which Inspect's env vars silently ignore
    on the programmatic path."""

    def test_default_max_samples_is_one(self, tasks_root, monkeypatch):
        """No flag -> max_samples=1 (safe default for rpm-capped providers)."""
        result, mock_eval = _run_with_mocked_eval(tasks_root, monkeypatch, [])
        assert result.exit_code == 0, result.output
        assert mock_eval.call_args.kwargs.get("max_samples") == 1

    def test_max_samples_flag_is_passed(self, tasks_root, monkeypatch):
        """--max-samples N threads through to inspect_eval()."""
        result, mock_eval = _run_with_mocked_eval(tasks_root, monkeypatch, ["--max-samples", "4"])
        assert result.exit_code == 0, result.output
        assert mock_eval.call_args.kwargs.get("max_samples") == 4

    def test_sequential_implies_max_samples_one(self, tasks_root, monkeypatch):
        """--sequential => fully serial: max_samples=1 AND max_tasks=1."""
        result, mock_eval = _run_with_mocked_eval(tasks_root, monkeypatch, ["--sequential"])
        assert result.exit_code == 0, result.output
        kwargs = mock_eval.call_args.kwargs
        assert kwargs.get("max_samples") == 1
        assert kwargs.get("max_tasks") == 1

    def test_sequential_overrides_explicit_max_samples(self, tasks_root, monkeypatch):
        """--sequential --max-samples 8 => max_samples=1 (sequential wins)."""
        result, mock_eval = _run_with_mocked_eval(
            tasks_root, monkeypatch, ["--sequential", "--max-samples", "8"]
        )
        assert result.exit_code == 0, result.output
        assert mock_eval.call_args.kwargs.get("max_samples") == 1

    def test_max_retries_flag_is_passed(self, tasks_root, monkeypatch):
        """--max-retries N threads through to inspect_eval() (GenerateConfig kwarg)."""
        result, mock_eval = _run_with_mocked_eval(tasks_root, monkeypatch, ["--max-retries", "6"])
        assert result.exit_code == 0, result.output
        assert mock_eval.call_args.kwargs.get("max_retries") == 6

    def test_default_max_retries_passthrough(self, tasks_root, monkeypatch):
        """No --max-retries => max_retries=None (passthrough to Inspect provider default)."""
        result, mock_eval = _run_with_mocked_eval(tasks_root, monkeypatch, [])
        assert result.exit_code == 0, result.output
        assert mock_eval.call_args.kwargs.get("max_retries") is None

    def test_one_by_one_threads_max_samples_to_each_call(self, tasks_root, monkeypatch):
        """--one-by-one must pass max_samples to every per-task inspect_eval call."""
        result, mock_eval = _run_with_mocked_eval(tasks_root, monkeypatch, ["--one-by-one"])
        assert result.exit_code == 0, result.output
        # --tier quick discovers 2 verification tasks -> 2 eval calls
        assert mock_eval.call_count == 2
        for call in mock_eval.call_args_list:
            assert call.kwargs.get("max_samples") == 1
            assert call.kwargs.get("max_retries") is None

    def test_run_help_shows_concurrency_flags(self):
        """--help advertises the new --max-samples / --max-retries flags."""
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--max-samples" in result.output
        assert "--max-retries" in result.output


class TestPricesCLI:
    """Tests for bench prices refresh and bench prices list commands."""

    def test_prices_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["prices", "--help"])
        assert result.exit_code == 0
        assert "refresh" in result.output
        assert "list" in result.output

    def test_prices_list_no_cache_shows_na(self, tmp_path, monkeypatch):
        """prices list shows empty message gracefully when cache has no models."""
        from bench_cli.pricing.price_cache import OpenRouterCache

        isolated_cache = OpenRouterCache(cache_path=tmp_path / "openrouter-models.json")
        runner = CliRunner()
        result = runner.invoke(cli, ["prices", "list"], obj={"cache": isolated_cache})
        assert result.exit_code == 0
        # Empty cache: should show "No models in cache"
        assert "No models in cache" in result.output

    def test_prices_list_shows_litellm_models(self, tmp_path, monkeypatch):
        """prices list shows models from LiteLLM config that have cached prices."""
        from bench_cli.pricing.price_cache import OpenRouterCache

        isolated_cache = OpenRouterCache(cache_path=tmp_path / "openrouter-models.json")
        isolated_cache.add_price("nvidia/nemotron-3-nano-30b-a3b", 0.00000005, 0.0000002)
        runner = CliRunner()
        result = runner.invoke(cli, ["prices", "list"], obj={"cache": isolated_cache})
        assert result.exit_code == 0
        # Should show nvidia-nemotron-30b with its price
        assert "nvidia/nemotron-3-nano-30b-a3b" in result.output

    def test_prices_refresh_missing_key_shows_soft_error(self, tmp_path, monkeypatch):
        """prices refresh with missing API key exits with error, not crash."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        runner = CliRunner()
        result = runner.invoke(cli, ["prices", "refresh"])
        assert result.exit_code == 1
        assert "OPENROUTER_API_KEY" in result.output
        assert "not set" in result.output


class TestPricesAdd:
    """Tests for bench prices add command."""

    def test_prices_add_unknown_alias(self, tmp_path):
        """Unknown alias exits with error."""
        from bench_cli.pricing.price_cache import OpenRouterCache

        isolated_cache = OpenRouterCache(cache_path=tmp_path / "openrouter-models.json")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["prices", "add", "rut-xyz-not-a-real-model", "0.15", "0.60"],
            obj={"cache": isolated_cache},
        )
        assert result.exit_code == 1
        assert "not in" in result.output.lower()

    def test_prices_add_managed_model_rejected(self, tmp_path):
        """Managed/local models have no OpenRouter ID — add should reject them."""
        from bench_cli.pricing.price_cache import OpenRouterCache

        isolated_cache = OpenRouterCache(cache_path=tmp_path / "openrouter-models.json")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["prices", "add", "openai/qwen-local", "0.0", "0.0"],
            obj={"cache": isolated_cache},
        )
        assert result.exit_code == 1
        assert "managed" in result.output.lower()

    def test_prices_add_success(self, tmp_path):
        """Adding a price succeeds and confirms the entry. Mocks the resolver
        so the test is independent of proxy state."""
        from unittest.mock import patch

        from bench_cli.pricing.price_cache import OpenRouterCache

        isolated_cache = OpenRouterCache(cache_path=tmp_path / "openrouter-models.json")
        runner = CliRunner()
        with patch(
            "bench_cli.prices.resolve_openrouter_id",
            return_value="vendor/test-or-id",
        ):
            result = runner.invoke(
                cli,
                ["prices", "add", "openai/test-priced-alias", "0.15", "0.60"],
                obj={"cache": isolated_cache},
            )
        assert result.exit_code == 0, result.output
        assert "Added:" in result.output
        assert "openai/test-priced-alias" in result.output
        # Verify the price was actually written to the isolated cache
        info = isolated_cache.get_price("vendor/test-or-id")
        assert info.input_price == 0.15
        assert info.output_price == 0.6


class TestPriceGate:
    """Tests for the pre-flight price gate in bench run."""

    def test_gate_blocks_without_api_key_when_price_missing(self, tasks_root, monkeypatch):
        """Gate fires when model resolves but price isn't in cache."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "")  # empty, no refresh possible
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            mock_eval.return_value = []
            # Use an empty isolated cache and empty overrides to guarantee price miss
            from bench_cli.pricing import litellm_config
            from bench_cli.pricing.price_cache import OpenRouterCache

            empty_cache_path = tasks_root / "empty-cache.json"
            empty_cache_path.write_text("{}")
            empty_overrides_path = tasks_root / "empty-overrides.json"
            empty_overrides_path.write_text("{}")

            monkeypatch.setattr(
                OpenRouterCache,
                "__init__",
                lambda self, **kw: self.__dict__.update(_cache_path=empty_cache_path, _data=None),
            )
            monkeypatch.setattr(litellm_config, "_OVERRIDES_PATH", empty_overrides_path)
            litellm_config._build_reverse_lookup.cache_clear()
            # Decouple from any specific proxy entry: pretend a priced model
            # exists AND the resolver returns its OR id, so the gate is the
            # only thing under test (provider + price-miss).
            monkeypatch.setattr(
                "bench_cli.run.cli.resolve_provider", lambda routed: "openai",
            )
            monkeypatch.setattr(
                litellm_config, "resolve_openrouter_id",
                lambda alias: "fake/gate-test-or-id",
            )

            result = runner.invoke(
                cli, ["run", "--tier", "quick", "--model", "openai/gate-test-model"]
            )
            assert "No price found" in result.output
            assert "ERROR" in result.output

    def test_gate_exempts_local_models(self, tasks_root, monkeypatch):
        """Local models should be exempt from the price gate."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        runner = CliRunner()
        with patch("inspect_ai.eval") as mock_eval:
            mock_eval.return_value = []
            result = runner.invoke(cli, ["run", "--tier", "quick", "--model", "openai/qwen-local"])
            assert "No price found" not in result.output


# ---------------------------------------------------------------------------
# Concurrency flags
# ---------------------------------------------------------------------------


class TestConcurrencyFlags:
    """Tests for --concurrency/-j and --sequential CLI flags."""

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

    def test_concurrency_passes_max_tasks_to_eval(self, tasks_root, monkeypatch):
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
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
            with patch("bench_cli.run.cli._resolve_task", return_value=fake_task):
                with patch("bench_cli.run.cli.resolve_provider", return_value="test-provider"):
                    result = runner.invoke(cli, ["run", "--tier", "quick", "--concurrency", "4"])
        assert result.exit_code == 0, result.output
        mock_eval.assert_called_once()
        call_kwargs = mock_eval.call_args[1]
        assert call_kwargs.get("max_tasks") == 4

    def test_sequential_passes_max_tasks_1_to_eval(self, tasks_root, monkeypatch):
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
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
            with patch("bench_cli.run.cli._resolve_task", return_value=fake_task):
                with patch("bench_cli.run.cli.resolve_provider", return_value="test-provider"):
                    result = runner.invoke(cli, ["run", "--tier", "quick", "--sequential"])
        assert result.exit_code == 0, result.output
        mock_eval.assert_called_once()
        call_kwargs = mock_eval.call_args[1]
        assert call_kwargs.get("max_tasks") == 1

    def test_sequential_wins_over_concurrency(self, tasks_root, monkeypatch):
        """--sequential should override --concurrency when both are passed."""
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
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
            with patch("bench_cli.run.cli._resolve_task", return_value=fake_task):
                with patch("bench_cli.run.cli.resolve_provider", return_value="test-provider"):
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

    def test_no_concurrency_passes_none_to_eval(self, tasks_root, monkeypatch):
        """When neither --concurrency nor --sequential is passed, max_tasks is None."""
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
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
            with patch("bench_cli.run.cli._resolve_task", return_value=fake_task):
                with patch("bench_cli.run.cli.resolve_provider", return_value="test-provider"):
                    result = runner.invoke(cli, ["run", "--tier", "quick"])
        assert result.exit_code == 0, result.output
        mock_eval.assert_called_once()
        call_kwargs = mock_eval.call_args[1]
        assert call_kwargs.get("max_tasks") is None

    def test_concurrency_1_sequential_one_by_one(self, tasks_root, monkeypatch):
        """--concurrency 1 should produce the same max_tasks=1 as --sequential."""
        from inspect_ai import Task

        fake_task = Task(dataset=None)
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
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
            with patch("bench_cli.run.cli._resolve_task", return_value=fake_task):
                with patch("bench_cli.run.cli.resolve_provider", return_value="test-provider"):
                    result = runner.invoke(cli, ["run", "--tier", "quick", "--concurrency", "1"])
        assert result.exit_code == 0, result.output
        call_kwargs = mock_eval.call_args[1]
        assert call_kwargs.get("max_tasks") == 1
