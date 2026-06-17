"""bench inspect must find rewritten logs by routing alias OR recorded name."""
from bench_cli.inspect.core import _resolve_query_name


def test_resolve_query_name_passes_recorded_through():
    # If user queries with the routing alias, resolve to recorded OR id
    assert _resolve_query_name("openai/thinking") == "minimaxai/minimax-m3"


def test_resolve_query_name_passes_or_id_through():
    # If user queries with an OR id, it's already recorded form -> unchanged
    assert _resolve_query_name("minimaxai/minimax-m3") == "minimaxai/minimax-m3"


def test_resolve_query_name_managed_passthrough():
    assert _resolve_query_name("openai/qwen-local") == "openai/qwen-local"


def test_resolve_query_name_custom_as_is_opaque():
    # R5: a custom --as value with no LiteLLM backing resolves to itself.
    # Users query such logs by the literal --as value (matched via raw input).
    # NOTE: use a genuinely opaque name — 'nemotron-ultra-550b' is NOT opaque
    # (it resolves via LiteLLM to nvidia/nemotron-3-ultra-550b-a55b).
    assert _resolve_query_name("my-custom-label") == "my-custom-label"
