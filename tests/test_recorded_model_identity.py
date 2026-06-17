"""Tests for resolve_recorded_name and rewrite_log_model_name."""
from bench_cli.run.core import resolve_recorded_name


def test_as_override_used_literal():
    assert resolve_recorded_name("openai/thinking", "nemotron-ultra-550b") == "nemotron-ultra-550b"


def test_as_override_literal_full_name():
    assert resolve_recorded_name("openai/thinking", "nvidia/nemotron-3-ultra-550b-a55b") == \
        "nvidia/nemotron-3-ultra-550b-a55b"


def test_moniker_resolves_to_openrouter_id():
    # thinking currently backs minimax-m3 on the NIM endpoint
    assert resolve_recorded_name("openai/thinking", None) == "minimaxai/minimax-m3"


def test_recognizable_alias_resolves_to_openrouter_id():
    assert resolve_recorded_name("openai/nemotron-ultra-550b", None) == \
        "nvidia/nemotron-3-ultra-550b-a55b"


def test_managed_model_short_circuits_not_resolved():
    # CRITICAL: resolve_openrouter_id returns a non-None LiteLLM id for qwen-local;
    # managed models must record their alias unchanged.
    assert resolve_recorded_name("openai/qwen-local", None) == "openai/qwen-local"
    assert resolve_recorded_name("openai/gemma-4-26-local", None) == "openai/gemma-4-26-local"


def test_unknown_alias_falls_back_to_model():
    # An alias not in LiteLLM config and not managed -> unchanged
    assert resolve_recorded_name("openai/totally-unknown-xyz", None) == "openai/totally-unknown-xyz"


def test_as_overrides_managed_short_circuit():
    # --as wins even for managed models (user's explicit choice)
    assert resolve_recorded_name("openai/qwen-local", "my-local") == "my-local"


def test_bracket_pricing_override_does_not_leak_into_recorded_name():
    # B4: logs/pricing/model_overrides.json has openai/minimax-m3 -> minimax/minimax-m3
    # (a pricing-only correction for the OpenRouter-API provider). The recorded
    # name must be the actual NIM backing model, NOT the override target.
    # resolve_recorded_name must bypass the override map.
    assert resolve_recorded_name("openai/minimax-m3", None) == "minimaxai/minimax-m3", (
        "bracket pricing override leaked into recorded name"
    )


import shutil
import tempfile
from pathlib import Path

from inspect_ai.log import read_eval_log

from bench_cli.run.core import rewrite_log_model_name


_FIXTURE = Path(__file__).parent / "fixtures" / "eval-logs" / "sample_success.eval"


def _copy_fixture(dest_dir: Path) -> Path:
    """Copy the committed fixture log into dest_dir; return its path."""
    assert _FIXTURE.is_file(), f"fixture missing: {_FIXTURE}"
    dest = dest_dir / _FIXTURE.name
    shutil.copy2(_FIXTURE, dest)
    return dest


def test_rewrite_changes_eval_model_and_preserves_samples():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        log_path = _copy_fixture(td)
        before = read_eval_log(str(log_path))
        before_samples = len(before.samples or [])
        before_scorers = [s.name for s in (before.results.scores if before.results and before.results.scores else [])]
        original_model = before.eval.model

        ok = rewrite_log_model_name(log_path, "minimaxai/minimax-m3")

        assert ok is True
        after = read_eval_log(str(log_path))
        assert after.eval.model == "minimaxai/minimax-m3"
        assert after.eval.model != original_model
        # samples preserved
        assert len(after.samples or []) == before_samples
        # all scorers preserved
        after_scorers = [s.name for s in (after.results.scores if after.results and after.results.scores else [])]
        assert after_scorers == before_scorers


def test_rewrite_idempotent_when_already_recorded():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        log_path = _copy_fixture(td)
        # First rewrite to a known value
        assert rewrite_log_model_name(log_path, "x/y-model") is True
        # Second rewrite to the same value is a no-op (still True)
        assert rewrite_log_model_name(log_path, "x/y-model") is True
        after = read_eval_log(str(log_path))
        assert after.eval.model == "x/y-model"


def test_rewrite_non_fatal_on_missing_file():
    ok = rewrite_log_model_name(Path("/nonexistent/path/foo.eval"), "whatever")
    assert ok is False  # does not raise


def test_rewrite_non_fatal_on_corrupt_zip():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        bad = td / "broken.eval"
        bad.write_text("not a zip file at all")  # corrupt
        ok = rewrite_log_model_name(bad, "whatever")
        assert ok is False  # does not raise
