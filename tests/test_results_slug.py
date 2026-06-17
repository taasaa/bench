from bench_cli.results.core import _slug_from_alias, _real_model_name, is_moniker_alias


def test_slug_from_or_id():
    assert _slug_from_alias("minimaxai/minimax-m3") == "minimaxai-minimax-m3"
    assert _slug_from_alias("nvidia/nemotron-3-ultra-550b-a55b") == "nvidia-nemotron-3-ultra-550b-a55b"


def test_real_model_name_from_or_id():
    assert _real_model_name("minimaxai/minimax-m3") == "minimaxai/minimax-m3"
    assert _real_model_name("nvidia/nemotron-3-ultra-550b-a55b") == "nvidia/nemotron-3-ultra-550b-a55b"


def test_is_moniker_alias_false_for_or_id():
    assert is_moniker_alias("minimaxai/minimax-m3") is False
    assert is_moniker_alias("nvidia/nemotron-3-ultra-550b-a55b") is False


def test_is_moniker_alias_true_for_moniker_bare():
    assert is_moniker_alias("openai/thinking") is True
    assert is_moniker_alias("openai/default") is True


def test_is_moniker_alias_false_for_custom_as():
    assert is_moniker_alias("nemotron-ultra-550b") is False


def test_get_model_metadata_provider_for_nvidia_or_id():
    # R1: spec Testing #5 — provider detection must work on recorded OR ids.
    from bench_cli.results.core import _get_model_metadata
    meta = _get_model_metadata("nvidia/nemotron-3-ultra-550b-a55b")
    assert meta["provider"] == "NVIDIA NIM", (
        f"expected NVIDIA NIM for OR id, got {meta['provider']!r}"
    )
    assert meta["free"] is False  # not a managed/local model


def test_get_model_metadata_pricing_for_direct_or_id():
    from bench_cli.results.core import _get_model_metadata

    meta = _get_model_metadata("nvidia/nemotron-3-ultra-550b-a55b")

    assert meta["has_price"] is True
    assert meta["input_price"] > 0
    assert meta["output_price"] > 0


def test_get_model_metadata_pricing_for_bench_alias_still_works():
    from bench_cli.results.core import _get_model_metadata

    meta = _get_model_metadata("openai/nemotron-ultra-550b")

    assert meta["has_price"] is True
