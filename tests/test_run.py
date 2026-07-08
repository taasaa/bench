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
    monkeypatch.setattr(cli_mod, "resolve_provider", lambda *_a, **_k: "test-provider")
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
    monkeypatch.setattr(cli_mod, "resolve_provider", lambda *_a, **_k: "test-provider")
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


def test_plain_display_when_not_tty(tmp_path, monkeypatch):
    """W1b: display='plain' is passed when stdout is not a TTY."""
    from bench_cli.run.cli import _choose_display
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert _choose_display(no_tui=False) == "plain"
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert _choose_display(no_tui=False) is None
    assert _choose_display(no_tui=True) == "plain"


def test_heartbeat_appends_jsonl(tmp_path):
    """W1b: one-by-one mode appends one JSON object per task to the status file."""
    from bench_cli.run.cli import _append_heartbeat
    hb = tmp_path / "hb.jsonl"
    _append_heartbeat(hb, task="f23-ghost-constraint", status="success", score=0.75, tokens=1234)
    _append_heartbeat(hb, task="f1-multi-file-verify", status="error", score=None, tokens=0)
    lines = hb.read_text().strip().splitlines()
    assert len(lines) == 2
    import json
    first = json.loads(lines[0])
    assert first["task"] == "f23-ghost-constraint" and first["status"] == "success" and first["score"] == 0.75


def test_write_run_summary_contains_all_tasks(tmp_path):
    """W1b (SC#2): batch mode writes one post-run JSON summary listing every task."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from bench_cli.run.cli import _write_run_summary
    out = tmp_path / "m.summary.json"
    metric = MagicMock(); metric.value = 0.75
    score = MagicMock(); score.metrics = {"mean": metric}
    results = [
        SimpleNamespace(eval=SimpleNamespace(task="f23_ghost_constraint"), status="success",
                        results=SimpleNamespace(scores=[score])),
        SimpleNamespace(eval=SimpleNamespace(task="f1_multi_file_verify"), status="error",
                        results=SimpleNamespace(scores=[])),
    ]
    _write_run_summary(out, bench_alias="openai/glm-5.1", results=results)
    import json
    data = json.loads(out.read_text())
    assert data["model"] == "openai/glm-5.1"
    assert len(data["tasks"]) == 2
    assert data["tasks"][0]["task"] == "f23_ghost_constraint" and data["tasks"][0]["score"] == 0.75
    assert data["tasks"][1]["status"] == "error"
