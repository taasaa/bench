"""Tests for resolve_recorded_name and rewrite_log_model_name."""
from unittest.mock import patch

from bench_cli.run.core import resolve_recorded_name


def test_as_override_used_literal():
    assert resolve_recorded_name("openai/thinking", "nemotron-ultra-550b") == "nemotron-ultra-550b"


def test_as_override_literal_full_name():
    assert resolve_recorded_name("openai/thinking", "nvidia/nemotron-3-ultra-550b-a55b") == \
        "nvidia/nemotron-3-ultra-550b-a55b"


def test_recognizable_alias_resolves_to_openrouter_id():
    """A recognizable alias resolves to the OR id reported by the proxy.

    Mocks the resolution layer so the test is independent of which specific
    models happen to be in the proxy today — the assertion is on
    resolve_recorded_name's passthrough behavior, not on the proxy.
    """
    with patch(
        "bench_cli.pricing.litellm_config.resolve_backing_model_id",
        return_value="fake/test-or-id",
    ):
        assert resolve_recorded_name("openai/test-alias", None) == "fake/test-or-id"


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


def test_bracket_pricing_override_does_not_leak_into_recorded_name(tmp_path, monkeypatch):
    """B4 invariant: resolve_recorded_name bypasses the pricing-override map.

    The override (logs/pricing/model_overrides.json) is pricing-only and must
    not leak into the recorded model identity. For every alias where the
    override actually changes resolution (backing_id != pricing_id), the
    recorded name must follow backing_id (the override-blind resolution),
    NEVER pricing_id (the override-applied result).

    Synthesizes a divergent override fixture in tmp_path (the live override
    file is often a no-op when no override actually changes resolution, so
    we cannot depend on it for the test premise).
    """
    import json

    from bench_cli.pricing import litellm_config
    from bench_cli.pricing.price_cache import OpenRouterCache

    # Synthesize a divergent override + matching cache state. Backing model
    # is the "real" backing (override-blind resolution); pricing target is
    # the override-applied resolution — they must differ for B4 to apply.
    alias = "openai/test-b4-alias"
    backing_id = "vendor/test-backing-model"
    pricing_target = "vendor/test-pricing-target"

    overrides_path = tmp_path / "model_overrides.json"
    overrides_path.write_text(json.dumps({alias: pricing_target}))
    monkeypatch.setattr(litellm_config, "_OVERRIDES_PATH", overrides_path)

    # Mock both resolvers: backing returns the override-blind id; the
    # override-applied resolver returns the pricing target. Access via the
    # module attribute so monkeypatch is honored (imported bindings at the
    # test's top would have captured the original function).
    monkeypatch.setattr(
        litellm_config, "resolve_backing_model_id",
        lambda a: backing_id if a == alias else None,
    )
    monkeypatch.setattr(
        litellm_config, "resolve_openrouter_id",
        lambda a: pricing_target if a == alias else None,
    )
    # Cache must contain the pricing target so resolve_openrouter_id doesn't
    # raise the "stale override" RuntimeError.
    cache_path = tmp_path / "price-cache.json"
    cache_path.write_text(json.dumps({pricing_target: {"input": 1.0, "output": 2.0, "context": 4096}}))
    monkeypatch.setattr(
        OpenRouterCache, "__init__",
        lambda self, **kw: self.__dict__.update(_cache_path=cache_path, _data=None),
    )

    # Sanity: with the fixture in place, backing != pricing — the B4 case.
    assert litellm_config.resolve_backing_model_id(alias) == backing_id
    assert litellm_config.resolve_openrouter_id(alias) == pricing_target
    assert backing_id != pricing_target

    # The invariant: resolve_recorded_name returns backing_id, NOT pricing_id.
    recorded = resolve_recorded_name(alias, None)
    assert recorded == backing_id, (
        f"B4 broken: recorded={recorded!r} should equal backing={backing_id!r} "
        f"(pricing={pricing_target!r} would have leaked the override)"
    )
    assert recorded != pricing_target, (
        f"pricing override leaked into recorded name: {recorded!r} == {pricing_target!r}"
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
