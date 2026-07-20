"""Bench model aliases → KiloCode model IDs, with free-model detection.

The primary source of truth for bench-alias → OpenRouter-id resolution is the
**live LiteLLM proxy config** at `~/dev/litellm/config.yaml`. Both the pricing
resolver (`resolve_openrouter_id`) and the recorded-identity resolver
(`resolve_backing_model_id`) consult it first via `_resolve_from_litellm()`,
which parses `model_name: <alias>` → `model: <provider>/<slug>` entries.

MODEL_ALIAS_MAP exists only as a **catch-all** for aliases the live proxy
config can't auto-resolve to an OpenRouter moniker. If the proxy has no
`model_name:` entry for your alias, AND you need a specific OR id for pricing
or recorded identity, add it here. Update the proxy config first; only fall
back to this map when you can't.

Resolution order (in resolve_openrouter_id / resolve_backing_model_id):
  1. Managed-model short-circuit (is_managed_model) — returns alias unchanged
  2. Persistent overrides (logs/pricing/model_overrides.json) — pricing-only
  3. Live LiteLLM proxy config — primary source of truth
  4. MODEL_ALIAS_MAP — catch-all (this dict)

Free model detection: any model with input_price == 0 AND output_price == 0
is flagged as FREE. These show `$0.00 (FREE)` in bench compare output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Catch-all alias map
# ---------------------------------------------------------------------------
# Key: bench model alias (openai/<alias>) NOT auto-resolvable by the live
#      LiteLLM proxy config (~/dev/litellm/config.yaml).
# Value: OpenRouter id (provider/model-slug) for pricing/recorded identity.
#
# Empty by design. Add an entry only if (a) the alias is not in the proxy
# config's model_list, AND (b) you want a specific OR id for it. Otherwise
# the resolver falls through to "alias unchanged" (recognizable form).

MODEL_ALIAS_MAP: dict[str, str] = {
    # Historical aliases removed from the live proxy config but still present
    # in the eval-log corpus. Their OpenRouter ids are recoverable only here
    # (the proxy no longer routes them), so this map preserves recorded
    # identity + pricing for legacy cards. All ids verified in the OpenRouter
    # price cache (logs/pricing/openrouter-models.json) at backfill time
    # (2026-06-18). See SB task for recorded-model-identity backfill.
    "openai/glm-plan-5-turbo": "z-ai/glm-5-turbo",
    "openai/glm-plan-5.2": "z-ai/glm-5.2",
    "openai/nvidia-devstral": "mistralai/devstral-2512",
    "openai/nvidia-mistral-small4": "mistralai/mistral-small-2603",
    "openai/nvidia-nemotron-30b": "nvidia/nemotron-3-nano-30b-a3b",
    "openai/nvidia-qwen-next": "qwen/qwen3-next-80b-a3b-instruct",
    "openai/fabric": "nvidia/nemotron-3-super-120b-a12b",
}



def is_free_model(bench_alias: str, price_info: PriceInfo) -> bool:
    """Detect whether a model is free based on its price.

    A model is free if both input and output prices are $0.
    """
    return price_info.input_price == 0.0 and price_info.output_price == 0.0


# ---------------------------------------------------------------------------
# Price data structure
# ---------------------------------------------------------------------------


@dataclass
class PriceInfo:
    """Price data for a single model, fetched from KiloCode API."""

    kilo_model_id: str
    input_price: float  # USD per million input tokens
    output_price: float  # USD per million output tokens
    context_window: int | None  # max context in tokens; None if not available
    is_free: bool = field(init=False)  # True if input_price == 0 AND output_price == 0

    def __post_init__(self) -> None:
        self.is_free = self.input_price == 0.0 and self.output_price == 0.0

    def cost_per_sample(self, input_tokens: int, output_tokens: int) -> float:
        """Compute cost in USD for a single sample.

        Args:
            input_tokens: Number of input tokens consumed.
            output_tokens: Number of output tokens generated.

        Returns:
            Cost in USD (as a float).
        """
        if self.is_free:
            return 0.0
        return (input_tokens * self.input_price / 1_000_000) + (
            output_tokens * self.output_price / 1_000_000
        )
