"""Tests for model name resolver."""

import click
import pytest

from bench_cli.resolver import bare_name, resolve_model


class TestResolveModel:
    def test_passthrough_with_slash(self):
        assert resolve_model("openai/qwen-local") == "openai/qwen-local"

    def test_exact_suffix_match(self):
        assert resolve_model("qwen-local") == "openai/qwen-local"

    def test_exact_suffix_match_opus(self):
        assert resolve_model("opus") == "openai/opus"

    def test_unique_prefix_match(self):
        # "qwen-local" is exact, not prefix — use a real unique prefix
        result = resolve_model("minimax")
        assert result == "openai/minimax"

    def test_ambiguous_prefix_raises(self):
        with pytest.raises(click.BadParameter, match="Ambiguous"):
            resolve_model("gemini")

    def test_unknown_returns_openai_prefix(self):
        result = resolve_model("totally-unknown-model")
        assert result == "openai/totally-unknown-model"

    def test_close_match_suggests(self):
        with pytest.raises(click.BadParameter, match="Closest"):
            resolve_model("qusen-local")  # typo — not a prefix, but close

    def test_default_alias(self):
        assert resolve_model("default") == "openai/default"


class TestBareName:
    def test_strips_prefix(self):
        assert bare_name("openai/qwen-local") == "qwen-local"

    def test_no_prefix(self):
        assert bare_name("qwen-local") == "qwen-local"

    def test_roundtrip(self):
        canonical = resolve_model("qwen-local")
        assert bare_name(canonical) == "qwen-local"

    def test_non_openai_prefix(self):
        assert bare_name("anthropic/claude-3") == "anthropic/claude-3"
