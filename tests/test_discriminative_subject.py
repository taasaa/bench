"""Subject identity comes from el.eval.model (recorded), not model_usage keys."""
from pathlib import Path

from bench_cli.discriminative.subject import resolve_subject_from_log


def test_subject_uses_eval_model_not_model_usage_key(monkeypatch, tmp_path):
    # Simulate a rewritten log: eval.model is the recorded OR id, but
    # model_usage keys are the routed moniker (as real logs have).
    class FakeSample:
        model_usage = {"openai/thinking": object(), "openai/judge": object()}

    class FakeEval:
        model = "minimaxai/minimax-m3"
        task = "smoke"
        sandbox = None
        solver_args = None

    class FakeLog:
        samples = [FakeSample()]
        eval = FakeEval()

    # B2: read_eval_log is imported lazily inside resolve_subject_from_log,
    # so patch the SOURCE name, not the consumer module attribute.
    import inspect_ai.log
    monkeypatch.setattr(inspect_ai.log, "read_eval_log", lambda *a, **k: FakeLog())

    sid = resolve_subject_from_log(Path("/fake/x.eval"))
    assert sid.model == "minimaxai/minimax-m3", (
        f"expected recorded OR id, got {sid.model!r} (model_usage key leak)"
    )
