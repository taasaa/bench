"""Routing tests for `bench_cli.run.core.build_model_route()`.

These tests pin the routing contract:
  * Bare alias + no chatgpt prefix  -> Inspect's OpenAI provider
  * Prefixed alias                  -> preserved
  * chatgpt/gpt-5.5 (and friends)   -> openai-api streaming route
  * --as name                       -> wins for recorded identity

Each test patches only the parts of the pricing layer the routing logic
depends on (managed-model check + OR id resolver) so the test runs
without any LiteLLM proxy / pricing cache on disk.
"""

from __future__ import annotations


def test_normal_bare_alias_routes_through_openai_provider() -> None:
    from bench_cli.run.core import build_model_route

    route = build_model_route("go-kimi-k2.7-code", as_name=None)
    assert route.routed_name == "openai/go-kimi-k2.7-code"
    assert route.pricing_alias == "go-kimi-k2.7-code"
    assert route.provider_alias == "go-kimi-k2.7-code"
    # 0.3.245 upgrade: non-chatgpt routes pin responses_api=False so
    # OpenAIAPI doesn't auto-route to /v1/responses (which Chat-Completions-
    # only backends like opencode, kilocode, nvidia_nim 404 on).
    assert route.model_args == {"responses_api": False}
    assert route.config_overrides == {}


def test_normal_prefixed_alias_is_preserved() -> None:
    from bench_cli.run.core import build_model_route

    route = build_model_route("openai/go-kimi-k2.7-code", as_name=None)
    assert route.routed_name == "openai/go-kimi-k2.7-code"
    assert route.pricing_alias == "openai/go-kimi-k2.7-code"
    assert route.provider_alias == "openai/go-kimi-k2.7-code"
    # Same 0.3.245 responses_api=False pin as the bare alias case.
    assert route.model_args == {"responses_api": False}


def test_chatgpt_alias_uses_openai_api_provider_streaming_and_usage(monkeypatch) -> None:
    from bench_cli.run.core import build_model_route

    # Keep this unit test hermetic. Exact recorded identity normally comes
    # from live LiteLLM config + pricing cache; patch that resolver path here.
    monkeypatch.setattr(
        "bench_cli.pricing.litellm_config.is_managed_model",
        lambda _alias: False,
    )
    monkeypatch.setattr(
        "bench_cli.pricing.litellm_config.resolve_backing_model_id",
        lambda alias: "openai/gpt-5.5" if alias == "chatgpt/gpt-5.5" else None,
    )

    route = build_model_route("chatgpt/gpt-5.5", as_name=None)
    assert route.routed_name == "openai-api/openai/chatgpt/gpt-5.5"
    assert route.provider_alias == "chatgpt/gpt-5.5"
    assert route.pricing_alias == "chatgpt/gpt-5.5"
    assert route.recorded_name == "openai/gpt-5.5"
    assert route.model_args == {"stream": True}
    assert route.config_overrides == {
        "extra_body": {"stream_options": {"include_usage": True}}
    }


def test_openai_chatgpt_alias_normalizes_to_same_streaming_route() -> None:
    from bench_cli.run.core import build_model_route

    route = build_model_route("openai/chatgpt/gpt-5.5", as_name=None)
    assert route.routed_name == "openai-api/openai/chatgpt/gpt-5.5"
    assert route.provider_alias == "chatgpt/gpt-5.5"
    assert route.pricing_alias == "chatgpt/gpt-5.5"
    assert route.model_args == {"stream": True}


def test_as_name_still_wins_for_chatgpt_route() -> None:
    from bench_cli.run.core import build_model_route

    route = build_model_route("chatgpt/gpt-5.5", as_name="gpt-5.5-codex")
    assert route.recorded_name == "gpt-5.5-codex"
