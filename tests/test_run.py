"""Tests for bench run resume + plain-progress (W1a/W1b)."""
from __future__ import annotations
import datetime
from pathlib import Path
from unittest.mock import patch


def _write_eval(path: Path, model: str, task_token: str, status: str) -> None:
    """Write a valid Inspect .eval log (header-only) for resume testing."""
    from inspect_ai.log import EvalLog, write_eval_log
    from inspect_ai.log._log import EvalConfig, EvalDataset, EvalSpec

    log = EvalLog(
        status=status,
        eval=EvalSpec(
            created=datetime.datetime.now().isoformat(),
            task=task_token.replace("-", "_"),
            task_id="ABC123",
            dataset=EvalDataset(samples=1),
            model=model,
            config=EvalConfig(),
        ),
    )
    fname = f"2026-06-16T10-00-00-00-00_{task_token}_ABC123.eval"
    write_eval_log(log, location=str(path / fname), format="eval")


def test_completed_tasks_skips_success_only(tmp_path):
    """W1a: only status='success' logs count as done; started/error do not."""
    from bench_cli.run.core import _completed_tasks

    _write_eval(tmp_path, "openai/glm-5.1", "f23-ghost-constraint", "success")
    _write_eval(tmp_path, "openai/glm-5.1", "f1-multi-file-verify", "error")  # not done
    done = _completed_tasks(
        str(tmp_path),
        "openai/glm-5.1",
        spec_dirs={"f23-ghost-constraint", "f1-multi-file-verify"},
    )
    assert done == {"f23-ghost-constraint"}


def test_run_resume_short_circuits_when_all_done(tmp_path, monkeypatch):
    """W1a: when every discovered task has a success log, eval is never called."""
    from click.testing import CliRunner
    from inspect_ai import Task
    import bench_cli.run.cli as cli_mod

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    fake_spec = "tasks/analysis/f23-ghost-constraint/task.py"

    monkeypatch.setattr(cli_mod, "_discover_tasks", lambda *a, **k: [fake_spec])
    monkeypatch.setattr(cli_mod, "_check_price_gate", lambda *_a, **_k: None)
    monkeypatch.setattr(cli_mod, "_resolve_task", lambda *a, **k: Task(dataset=None))
    monkeypatch.setattr(cli_mod, "_completed_tasks", lambda *a, **k: {"f23-ghost-constraint"})

    called = {"n": 0}
    def fake_eval(*a, **k):
        called["n"] += 1
        return []
    # inspect_eval is imported lazily inside run() as `from inspect_ai import eval`,
    # so patch the source rather than a non-existent module attribute.
    import inspect_ai
    monkeypatch.setattr(inspect_ai, "eval", fake_eval)

    runner = CliRunner()
    result = runner.invoke(
        cli_mod.run,
        ["--tier", "full", "--model", "openai/qwen-local", "--log-dir", str(log_dir), "--no-compare"],
    )
    assert result.exit_code == 0, result.output
    assert "nothing to do" in result.output.lower()
    assert called["n"] == 0


def test_run_no_resume_dispatches_despite_success_logs(tmp_path, monkeypatch):
    """W1a: --no-resume ignores existing success logs and dispatches eval."""
    from click.testing import CliRunner
    from inspect_ai import Task
    import bench_cli.run.cli as cli_mod

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    fake_spec = "tasks/analysis/f23-ghost-constraint/task.py"

    monkeypatch.setattr(cli_mod, "_discover_tasks", lambda *a, **k: [fake_spec])
    monkeypatch.setattr(cli_mod, "_check_price_gate", lambda *_a, **_k: None)
    monkeypatch.setattr(cli_mod, "_resolve_task", lambda *a, **k: Task(dataset=None))
    def boom(*a, **k):
        raise AssertionError("_completed_tasks must not be called under --no-resume")
    monkeypatch.setattr(cli_mod, "_completed_tasks", boom)

    called = {"n": 0}
    def fake_eval(*a, **k):
        called["n"] += 1
        return []
    import inspect_ai
    monkeypatch.setattr(inspect_ai, "eval", fake_eval)

    runner = CliRunner()
    result = runner.invoke(
        cli_mod.run,
        ["--tier", "full", "--no-resume", "--model", "openai/qwen-local",
         "--log-dir", str(log_dir), "--no-compare"],
    )
    assert result.exit_code == 0, result.output
    assert called["n"] == 1
