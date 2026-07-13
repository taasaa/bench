"""Tests for model name resolver."""

import click
import pytest

from bench_cli.resolver import bare_name, resolve_model


class TestResolveModel:
    def test_passthrough_with_slash(self):
        assert resolve_model("openai/qwen-local") == "openai/qwen-local"

    def test_exact_suffix_match(self, monkeypatch):
        """Exact bare-name lookup hits `_SUFFIX_MAP`. Patches the module-level
        map so the test exercises resolver logic, not live proxy state."""
        monkeypatch.setattr("bench_cli.resolver._SUFFIX_MAP", {
            "qwen-local": "openai/qwen-local",
            "minimax": "openai/minimax",
            "default": "openai/default",
        }, raising=False)
        assert resolve_model("qwen-local") == "openai/qwen-local"
        assert resolve_model("minimax") == "openai/minimax"

    def test_unique_prefix_match(self, monkeypatch):
        """Unique prefix resolves when exactly one suffix starts with the input."""
        monkeypatch.setattr("bench_cli.resolver._SUFFIX_MAP", {
            "minimax": "openai/minimax",
            "minimax-m2.7": "openai/minimax-m2.7",
            "qwen-local": "openai/qwen-local",
        }, raising=False)
        # "minimax-" is unique to minimax-m2.7 (qwen-local doesn't share the prefix).
        # But "minimax" is also in the map as exact match. Use a longer prefix.
        assert resolve_model("minimax-") == "openai/minimax-m2.7"

    def test_unknown_returns_openai_prefix(self):
        result = resolve_model("totally-unknown-model")
        assert result == "openai/totally-unknown-model"

    def test_close_match_suggests(self):
        with pytest.raises(click.BadParameter, match="Closest"):
            resolve_model("qusen-local")  # typo — not a prefix, but close


class TestBareName:
    def test_strips_prefix(self):
        assert bare_name("openai/qwen-local") == "qwen-local"

    def test_no_prefix(self):
        assert bare_name("qwen-local") == "qwen-local"

    def test_roundtrip(self):
        canonical = resolve_model("qwen-local")
        assert bare_name(canonical) == "qwen-local"

    def test_non_openai_prefix(self):
        # bare_name now strips the FIRST segment (not just openai/), so a
        # non-openai prefix is also reduced to its suffix.
        assert bare_name("anthropic/claude-3") == "claude-3"
