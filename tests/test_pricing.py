"""Tests for bench_cli.pricing: model aliases, price cache, and PriceInfo."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from bench_cli.pricing.model_aliases import (
    MODEL_ALIAS_MAP,
    PriceInfo,
    is_free_model,
    resolve_alias,
)
from bench_cli.pricing.price_cache import CacheMiss, OpenRouterCache
from bench_cli.pricing.litellm_config import (
    _load_litellm_alias_map,
    is_managed_model,
    resolve_openrouter_id,
    save_override,
)


# ---------------------------------------------------------------------------
# model_aliases
# ---------------------------------------------------------------------------

class TestModelAliases:
    def test_resolve_alias_known(self):
        assert resolve_alias("openai/qwen-local") == "qwen/qwen3.5-35b-a3b"
        assert resolve_alias("openai/gpt-4o") == "openai/gpt-4o"
        assert resolve_alias("openai/opus") == "anthropic/claude-3-opus"
        assert resolve_alias("openai/sonnet") == "anthropic/claude-3-sonnet"
        assert resolve_alias("openai/gemini-2-5-pro") == "google/gemini-2.5-pro"

    def test_resolve_alias_unknown(self):
        assert resolve_alias("openai/nonexistent-model") is None
        assert resolve_alias("unknown/thing") is None

    def test_resolve_alias_exact_match_required(self):
        assert resolve_alias("qwen-local") is None
        assert resolve_alias("gpt-4o") is None

    def test_alias_map_covers_required_models(self):
        required = [
            "openai/qwen-local",
            "openai/gemma-4-e2-local",
            "openai/gemma-4-26-local",
            "openai/opus",
            "openai/sonnet",
            "openai/haiku",
            "openai/opus-4",
            "openai/sonnet-4",
            "openai/haiku-4",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
        ]
        for alias in required:
            assert alias in MODEL_ALIAS_MAP, f"Missing alias: {alias}"

    def test_is_free_model_false(self):
        info = PriceInfo("test/model", input_price=0.5, output_price=1.5, context_window=4096)
        assert is_free_model("openai/test", info) is False

    def test_is_free_model_true(self):
        info = PriceInfo("test/model", input_price=0.0, output_price=0.0, context_window=None)
        assert is_free_model("openai/test", info) is True

    def test_is_free_model_input_only_zero_is_not_free(self):
        info = PriceInfo("test/model", input_price=0.0, output_price=1.5, context_window=None)
        assert is_free_model("openai/test", info) is False


class TestPriceInfo:
    def test_cost_per_sample_zero_tokens(self):
        info = PriceInfo("test/model", input_price=1.0, output_price=2.0, context_window=4096)
        assert info.cost_per_sample(0, 0) == 0.0

    def test_cost_per_sample_input_only(self):
        info = PriceInfo("test/model", input_price=1.0, output_price=2.0, context_window=4096)
        # 500 input tokens at $1/M = $0.0005
        assert info.cost_per_sample(500, 0) == pytest.approx(0.0005)

    def test_cost_per_sample_output_only(self):
        info = PriceInfo("test/model", input_price=1.0, output_price=2.0, context_window=4096)
        # 100 output tokens at $2/M = $0.0002
        assert info.cost_per_sample(0, 100) == pytest.approx(0.0002)

    def test_cost_per_sample_both(self):
        info = PriceInfo("test/model", input_price=1.0, output_price=2.0, context_window=4096)
        # 500 input + 100 output = 500*$1/M + 100*$2/M = $0.0005 + $0.0002 = $0.0007
        assert info.cost_per_sample(500, 100) == pytest.approx(0.0007)

    def test_cost_per_sample_free_model(self):
        info = PriceInfo("test/model", input_price=0.0, output_price=0.0, context_window=None)
        assert info.cost_per_sample(1_000_000, 500_000) == 0.0

    def test_is_free_property(self):
        paid = PriceInfo("test/model", input_price=1.0, output_price=2.0, context_window=4096)
        free = PriceInfo("test/model", input_price=0.0, output_price=0.0, context_window=None)
        assert paid.is_free is False
        assert free.is_free is True

    def test_context_window_none(self):
        info = PriceInfo("test/model", input_price=1.0, output_price=2.0, context_window=None)
        assert info.context_window is None

    def test_context_window_set(self):
        info = PriceInfo("test/model", input_price=1.0, output_price=2.0, context_window=4096)
        assert info.context_window == 4096


# ---------------------------------------------------------------------------
# price_cache
# ---------------------------------------------------------------------------

class TestOpenRouterCache:
    def test_cache_path_default(self, tmp_path):
        cache = OpenRouterCache(cache_path=tmp_path / "prices.json")
        assert cache.cache_path == tmp_path / "prices.json"

    def test_get_price_no_cache(self, tmp_path):
        cache = OpenRouterCache(cache_path=tmp_path / "nonexistent.json")
        with pytest.raises(CacheMiss):
            cache.get_price("qwen/qwen-local")

    def test_get_price_stale_cache(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        stale_time = datetime.now(timezone.utc) - timedelta(days=4)
        cache_data = {
            "fetched_at": stale_time.isoformat(),
            "models": {"qwen/qwen-local": {"input": 0.5, "output": 1.0, "context": 4096}},
        }
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = OpenRouterCache(cache_path=cache_file)
        with pytest.raises(CacheMiss, match="stale"):
            cache.get_price("qwen/qwen-local")

    def test_get_price_model_not_found(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        cache_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "models": {"qwen/qwen-local": {"input": 0.5, "output": 1.0, "context": 4096}},
        }
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = OpenRouterCache(cache_path=cache_file)
        with pytest.raises(CacheMiss, match="not found"):
            cache.get_price("unknown/model")

    def test_get_price_success(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        cache_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "models": {"qwen/qwen-local": {"input": 0.5, "output": 1.0, "context": 8192}},
        }
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = OpenRouterCache(cache_path=cache_file)
        info = cache.get_price("qwen/qwen-local")
        assert info.kilo_model_id == "qwen/qwen-local"
        assert info.input_price == 0.5
        assert info.output_price == 1.0
        assert info.context_window == 8192

    def test_get_price_fresh_cache(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        cache_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "models": {"test/model": {"input": 0.1, "output": 0.2, "context": None}},
        }
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = OpenRouterCache(cache_path=cache_file)
        info = cache.get_price("test/model")
        assert info.is_free is False
        assert info.context_window is None

    def test_get_freshness_none_when_missing(self, tmp_path):
        cache = OpenRouterCache(cache_path=tmp_path / "nonexistent.json")
        assert cache.get_freshness() is None

    def test_get_freshness_returns_timestamp(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        now = datetime.now(timezone.utc)
        cache_data = {"fetched_at": now.isoformat(), "models": {}}
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = OpenRouterCache(cache_path=cache_file)
        assert cache.get_freshness() == now.isoformat()

    def test_get_all_prices_empty_when_missing(self, tmp_path):
        cache = OpenRouterCache(cache_path=tmp_path / "nonexistent.json")
        assert cache.get_all_prices() == {}

    def test_get_all_prices_returns_all_models(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        cache_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "models": {
                "model/a": {"input": 0.1, "output": 0.2, "context": 4096},
                "model/b": {"input": 0.3, "output": 0.4, "context": 8192},
            },
        }
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = OpenRouterCache(cache_path=cache_file)
        all_prices = cache.get_all_prices()
        assert len(all_prices) == 2
        assert "model/a" in all_prices
        assert "model/b" in all_prices
        assert all_prices["model/a"].input_price == 0.1

    def test_get_all_prices_empty_when_stale(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        stale_time = datetime.now(timezone.utc) - timedelta(days=10)
        cache_data = {
            "fetched_at": stale_time.isoformat(),
            "models": {"model/a": {"input": 0.1, "output": 0.2, "context": None}},
        }
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = OpenRouterCache(cache_path=cache_file)
        assert cache.get_all_prices() == {}

    def test_fetch_and_cache_prices_missing_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cache = OpenRouterCache(cache_path=tmp_path / "prices.json")
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY not set"):
            cache.fetch_and_cache_prices()

    def test_is_stale_true_when_old(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        old_time = datetime.now(timezone.utc) - timedelta(days=5)
        cache_data = {"fetched_at": old_time.isoformat(), "models": {}}
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = OpenRouterCache(cache_path=cache_file)
        with pytest.raises(CacheMiss, match="stale"):
            cache.get_price("any/model")

    def test_is_stale_false_when_fresh(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        now = datetime.now(timezone.utc)
        cache_data = {"fetched_at": now.isoformat(), "models": {}}
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = OpenRouterCache(cache_path=cache_file)
        # Should not raise CacheMiss for staleness (raises for model not found instead)
        with pytest.raises(CacheMiss, match="not found"):
            cache.get_price("any/model")

    def test_add_price_new_entry(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        cache_file.write_text(
            json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "models": {}}),
            encoding="utf-8",
        )
        cache = OpenRouterCache(cache_path=cache_file)
        cache.add_price("mistralai/mistral-small-4-119b-2603", 0.15, 0.60)

        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert "mistralai/mistral-small-4-119b-2603" in data["models"]
        assert data["models"]["mistralai/mistral-small-4-119b-2603"]["input"] == 0.15
        assert data["models"]["mistralai/mistral-small-4-119b-2603"]["output"] == 0.60

    def test_add_price_updates_existing(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        cache_file.write_text(
            json.dumps({
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "models": {"model/x": {"input": 0.1, "output": 0.2, "context": 4096}},
            }),
            encoding="utf-8",
        )
        cache = OpenRouterCache(cache_path=cache_file)
        cache.add_price("model/x", 0.99, 1.99)

        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert data["models"]["model/x"]["input"] == 0.99
        assert data["models"]["model/x"]["output"] == 1.99
        assert data["models"]["model/x"]["context"] is None  # not overwritten
        assert "model/x" in data["models"]  # original still present

    def test_add_price_creates_cache_if_missing(self, tmp_path):
        cache = OpenRouterCache(cache_path=tmp_path / "nonexistent.json")
        cache.add_price("some/model", 0.5, 1.0)
        data = json.loads((tmp_path / "nonexistent.json").read_text(encoding="utf-8"))
        assert "some/model" in data["models"]
        assert data["models"]["some/model"]["input"] == 0.5


# ---------------------------------------------------------------------------
# litellm_config
# ---------------------------------------------------------------------------

class TestLiteLLMConfig:
    """Tests for LiteLLM config parser and resolution."""

    def test_resolve_openrouter_id_from_litellm_config_only(self):
        """Alias not in LiteLLM config returns None — no MODEL_ALIAS_MAP fallback."""
        # "openai/does-not-exist-xyz789" is not in LiteLLM config → None
        result = resolve_openrouter_id("openai/does-not-exist-xyz789")
        assert result is None

    def test_resolve_openrouter_id_unknown_alias(self):
        result = resolve_openrouter_id("openai/this-does-not-exist-xyz789")
        assert result is None

    def test_resolve_openrouter_id_litellm_name_without_prefix(self):
        """Bench alias without openai/ prefix resolves via LiteLLM config + cache reverse-lookup."""
        # "rut" in LiteLLM config → "openai/MiniMax-M2.7" → lowercase "minimax-m2.7"
        # → reverse-lookup in OpenRouter cache → "minimax/minimax-m2.7"
        result = resolve_openrouter_id("rut")
        assert result == "minimax/minimax-m2.7"

    def test_load_litellm_alias_map_caches(self):
        """Calling twice returns same dict (lru_cache)."""
        first = _load_litellm_alias_map()
        second = _load_litellm_alias_map()
        assert first is second  # same object due to @lru_cache


class TestModelOverrides:
    """Tests for persistent model ID overrides."""

    def test_save_override_rejects_unknown_id(self, tmp_path, monkeypatch):
        """save_override rejects IDs not in the OpenRouter cache."""
        from bench_cli.pricing import litellm_config

        overrides_file = tmp_path / "model_overrides.json"
        monkeypatch.setattr(litellm_config, "_OVERRIDES_PATH", overrides_file)

        with pytest.raises(ValueError, match="not found in OpenRouter cache"):
            save_override("openai/test-model", "provider/does-not-exist")

    def test_save_and_load_override(self, tmp_path, monkeypatch):
        """save_override persists when ID is in cache, resolve picks it up."""
        from bench_cli.pricing import litellm_config
        from bench_cli.pricing.price_cache import OpenRouterCache

        overrides_file = tmp_path / "model_overrides.json"
        monkeypatch.setattr(litellm_config, "_OVERRIDES_PATH", overrides_file)

        # Use an ID that's actually in the real cache
        cache = OpenRouterCache()
        all_prices = cache.get_all_prices()
        real_id = next(iter(all_prices))

        save_override("openai/test-model", real_id)
        assert overrides_file.is_file()

        result = resolve_openrouter_id("openai/test-model")
        assert result == real_id

    def test_override_used_when_litellm_slug_not_in_cache(self, tmp_path, monkeypatch):
        """Override kicks in when LiteLLM config slug isn't in the cache."""
        from bench_cli.pricing import litellm_config
        from bench_cli.pricing.price_cache import OpenRouterCache

        overrides_file = tmp_path / "model_overrides.json"
        monkeypatch.setattr(litellm_config, "_OVERRIDES_PATH", overrides_file)

        # Use a real cached ID as the override target
        cache = OpenRouterCache()
        all_prices = cache.get_all_prices()
        real_id = next(iter(all_prices))

        # Use a model name that doesn't resolve from LiteLLM at all,
        # so the override is the only way to find it
        save_override("openai/fake-test-model", real_id)
        result = resolve_openrouter_id("openai/fake-test-model")
        assert result == real_id

    def test_stale_override_raises_error(self, tmp_path, monkeypatch):
        """Override that points to a model no longer in cache raises RuntimeError."""
        from bench_cli.pricing import litellm_config

        overrides_file = tmp_path / "model_overrides.json"
        monkeypatch.setattr(litellm_config, "_OVERRIDES_PATH", overrides_file)

        # Write an override pointing to a non-existent cache entry
        overrides_file.write_text(json.dumps({"openai/gone-model": "provider/deleted-model"}))

        with pytest.raises(RuntimeError, match="Stale override"):
            resolve_openrouter_id("openai/gone-model")


class TestIsManagedModel:
    """Tests for managed/local model exemption logic."""

    @pytest.mark.parametrize("alias", [
        "openai/qwen-local",
        "openai/gemma-4-e2-local",
        "openai/gemma-4-26-local",
        "openai/glm-local",
    ])
    def test_local_suffix_is_managed(self, alias):
        assert is_managed_model(alias) is True

    @pytest.mark.parametrize("alias", [
        "openai/qwen3-coder-plus",
        "openai/qwen3-max",
    ])
    def test_named_local_models_managed(self, alias):
        assert is_managed_model(alias) is True

    @pytest.mark.parametrize("alias", [
        "openai/opus",
        "openai/sonnet",
        "openai/gpt-4o",
        "openai/nvidia-mistral-small4",
        "openai/default",
    ])
    def test_regular_aliases_not_managed(self, alias):
        assert is_managed_model(alias) is False

    def test_partial_match_not_managed(self):
        # "local" appears in the alias but not as -local suffix
        assert is_managed_model("openai/local-model-test") is False
