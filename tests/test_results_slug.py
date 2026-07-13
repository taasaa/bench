from bench_cli.results.core import _slug_from_alias, _real_model_name, is_moniker_alias


def test_slug_from_or_id():
    assert _slug_from_alias("minimaxai/minimax-m3") == "minimaxai-minimax-m3"
    assert _slug_from_alias("nvidia/nemotron-3-ultra-550b-a55b") == "nvidia-nemotron-3-ultra-550b-a55b"


def test_real_model_name_from_or_id():
    assert _real_model_name("minimaxai/minimax-m3") == "minimaxai/minimax-m3"
    assert _real_model_name("nvidia/nemotron-3-ultra-550b-a55b") == "nvidia/nemotron-3-ultra-550b-a55b"


def test_is_moniker_alias_predicate():
    # Pure predicate tests: constants are stable, no proxy state needed.
    assert is_moniker_alias("openai/thinking") is True
    assert is_moniker_alias("openai/default") is True
    assert is_moniker_alias("minimaxai/minimax-m3") is False
    assert is_moniker_alias("nvidia/nemotron-3-ultra-550b-a55b") is False
    assert is_moniker_alias("nemotron-ultra-550b") is False


def test_get_model_metadata_returns_pricing(monkeypatch):
    """A priced alias returns has_price=True with the resolved price values.

    Mocks the resolution + cache-lookup layers so the test is independent of
    any specific proxy entry or live cache state.
    """
    from unittest.mock import patch

    from bench_cli.pricing.model_aliases import PriceInfo
    from bench_cli.results.core import _get_model_metadata

    fake_price = PriceInfo("fake/test-or-id", 1.0, 2.0, 4096)
    with patch(
        "bench_cli.results.core.resolve_openrouter_id",
        return_value="fake/test-or-id",
    ), patch(
        "bench_cli.pricing.price_cache.OpenRouterCache.get_price",
        return_value=fake_price,
    ):
        meta = _get_model_metadata("openai/test-priced-alias")

    assert meta["has_price"] is True
    assert meta["input_price"] == 1.0
    assert meta["output_price"] == 2.0
