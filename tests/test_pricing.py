"""Tests for bench_cli.pricing: model aliases, price cache, and PriceInfo."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench_cli.pricing.model_aliases import (
    MODEL_ALIAS_MAP,
    PriceInfo,
    is_free_model,
    resolve_alias,
)
from bench_cli.pricing.price_cache import CacheMiss, KiloCodeCache


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

class TestKiloCodeCache:
    def test_cache_path_default(self, tmp_path):
        cache = KiloCodeCache(cache_path=tmp_path / "prices.json")
        assert cache.cache_path == tmp_path / "prices.json"

    def test_get_price_no_cache(self, tmp_path):
        cache = KiloCodeCache(cache_path=tmp_path / "nonexistent.json")
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
        cache = KiloCodeCache(cache_path=cache_file)
        with pytest.raises(CacheMiss, match="stale"):
            cache.get_price("qwen/qwen-local")

    def test_get_price_model_not_found(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        cache_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "models": {"qwen/qwen-local": {"input": 0.5, "output": 1.0, "context": 4096}},
        }
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = KiloCodeCache(cache_path=cache_file)
        with pytest.raises(CacheMiss, match="not found"):
            cache.get_price("unknown/model")

    def test_get_price_success(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        cache_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "models": {"qwen/qwen-local": {"input": 0.5, "output": 1.0, "context": 8192}},
        }
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = KiloCodeCache(cache_path=cache_file)
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
        cache = KiloCodeCache(cache_path=cache_file)
        info = cache.get_price("test/model")
        assert info.is_free is False
        assert info.context_window is None

    def test_get_freshness_none_when_missing(self, tmp_path):
        cache = KiloCodeCache(cache_path=tmp_path / "nonexistent.json")
        assert cache.get_freshness() is None

    def test_get_freshness_returns_timestamp(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        now = datetime.now(timezone.utc)
        cache_data = {"fetched_at": now.isoformat(), "models": {}}
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = KiloCodeCache(cache_path=cache_file)
        assert cache.get_freshness() == now.isoformat()

    def test_get_all_prices_empty_when_missing(self, tmp_path):
        cache = KiloCodeCache(cache_path=tmp_path / "nonexistent.json")
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
        cache = KiloCodeCache(cache_path=cache_file)
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
        cache = KiloCodeCache(cache_path=cache_file)
        assert cache.get_all_prices() == {}

    def test_fetch_and_cache_prices_missing_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("KILOCODE_API_KEY", raising=False)
        cache = KiloCodeCache(cache_path=tmp_path / "prices.json")
        with pytest.raises(RuntimeError, match="KILOCODE_API_KEY not set"):
            cache.fetch_and_cache_prices()

    def test_is_stale_true_when_old(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        old_time = datetime.now(timezone.utc) - timedelta(days=5)
        cache_data = {"fetched_at": old_time.isoformat(), "models": {}}
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = KiloCodeCache(cache_path=cache_file)
        with pytest.raises(CacheMiss, match="stale"):
            cache.get_price("any/model")

    def test_is_stale_false_when_fresh(self, tmp_path):
        cache_file = tmp_path / "prices.json"
        now = datetime.now(timezone.utc)
        cache_data = {"fetched_at": now.isoformat(), "models": {}}
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")
        cache = KiloCodeCache(cache_path=cache_file)
        # Should not raise CacheMiss for staleness (raises for model not found instead)
        with pytest.raises(CacheMiss, match="not found"):
            cache.get_price("any/model")
