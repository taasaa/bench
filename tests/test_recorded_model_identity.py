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
