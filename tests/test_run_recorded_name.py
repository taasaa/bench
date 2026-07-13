"""End-to-end test of --as / recorded-name threading in `bench run`.

Patches inspect_ai.eval (inspect_eval is imported lazily inside run(), so we
patch the source name, not bench_cli.run.cli.inspect_eval) and uses the
committed fixture log so no hand-built EvalLog is needed.
"""
import shutil
from pathlib import Path

from click.testing import CliRunner
from inspect_ai.log import read_eval_log

import bench_cli.run.cli as cli_mod
from bench_cli.run.cli import run as run_cmd
from bench_cli.run.core import resolve_recorded_name


_FIXTURE = Path(__file__).parent / "fixtures" / "eval-logs" / "sample_success.eval"


def fake_inspect_eval_factory(received: dict):
    """Return a fake inspect_eval that records routed_model and copies the fixture."""
    def _fake(tasks=None, model=None, **kwargs):
        received["model"] = model
        log_dir = kwargs.get("log_dir", "logs")
        dest = Path(log_dir) / _FIXTURE.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_FIXTURE, dest)
        # Return a list with one re-read EvalLog (so .location points at dest).
        return [read_eval_log(str(dest))]
    return _fake


def test_as_flag_records_custom_name_and_routes_through_model(monkeypatch, tmp_path):
    received = {}
    # B2: patch the source name (inspect_eval is imported lazily inside run()).
    import inspect_ai
    monkeypatch.setattr(inspect_ai, "eval", fake_inspect_eval_factory(received))
    monkeypatch.setattr(cli_mod, "_check_price_gate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "resolve_provider", lambda *_args, **_kwargs: "test-provider")

    runner = CliRunner()
    result = runner.invoke(
        run_cmd,
        [
            "--model", "openai/thinking",
            "--as", "nemotron-ultra-550b",
            "--tier", "quick",
            "--task", "smoke",
            "--log-dir", str(tmp_path),
            "--no-compare",
            "--no-tui",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    # Routed name hit the proxy
    assert received["model"] == "openai/thinking"
    # The written log records the --as name
    logs = list(Path(tmp_path).glob("*.eval"))
    assert logs, f"no log written in {tmp_path}"
    el = read_eval_log(str(logs[0]))
    assert el.eval.model == "nemotron-ultra-550b"


def test_no_as_flag_records_openrouter_id(monkeypatch, tmp_path):
    """Without --as, the recorded name equals the resolved backing model.

    Mocks resolve_backing_model_id so the test is independent of proxy state.
    """
    expected_recorded = "fake/test-recorded-or-id"
    monkeypatch.setattr(
        "bench_cli.pricing.litellm_config.resolve_backing_model_id",
        lambda alias: expected_recorded if alias == "openai/thinking" else None,
    )

    received = {}
    import inspect_ai
    monkeypatch.setattr(inspect_ai, "eval", fake_inspect_eval_factory(received))
    monkeypatch.setattr(cli_mod, "_check_price_gate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "resolve_provider", lambda *_args, **_kwargs: "test-provider")

    runner = CliRunner()
    result = runner.invoke(
        run_cmd,
        [
            "--model", "openai/thinking",
            "--tier", "quick",
            "--task", "smoke",
            "--log-dir", str(tmp_path),
            "--no-compare",
            "--no-tui",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert received["model"] == "openai/thinking"
    logs = list(Path(tmp_path).glob("*.eval"))
    el = read_eval_log(str(logs[0]))
    assert el.eval.model == expected_recorded
