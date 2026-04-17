"""Bench model aliases → KiloCode model IDs, with free-model detection.

Maps bench's LiteLLM proxy alias format (openai/<alias>) to KiloCode API model
IDs (provider/model-slug). KiloCode uses OpenRouter format: provider/model.

Free model detection: any model with input_price == 0 AND output_price == 0
is flagged as FREE. These show `$0.00 (FREE)` in bench compare output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Alias map
# ---------------------------------------------------------------------------
# Key: bench model alias (openai/<alias> from LiteLLM proxy)
# Value: KiloCode model ID (provider/model-slug for KiloCode API)

MODEL_ALIAS_MAP: dict[str, str] = {
    # Known local models
    "openai/qwen-local": "qwen/qwen3.5-35b-a3b",
    "openai/gemma-4-e2-local": "google/gemma-4-26b-a4b-it",
    "openai/gemma-4-26-local": "google/gemma-4-26b-a4b-it",
    "openai/glm-local": "THUDM/glm-4-9b-chat",
    "openai/qwen3-coder-plus": "qwen/qwen3-coder-plus",
    "openai/qwen3-max": "qwen/qwen3-max",
    # OpenAI models
    "openai/gpt-4o": "openai/gpt-4o",
    "openai/gpt-4o-mini": "openai/gpt-4o-mini",
    "openai/o1": "openai/o1",
    "openai/o1-mini": "openai/o1-mini",
    "openai/o3": "openai/o3",
    "openai/o3-mini": "openai/o3-mini",
    # Anthropic models
    "openai/opus": "anthropic/claude-3-opus",
    "openai/sonnet": "anthropic/claude-3-sonnet",
    "openai/haiku": "anthropic/claude-3-haiku",
    "openai/opus-4": "anthropic/claude-3-opus",
    "openai/sonnet-4": "anthropic/claude-3-sonnet",
    "openai/haiku-4": "anthropic/claude-3-haiku",
    "openai/opus-3-5": "anthropic/claude-3.5-opus",
    "openai/sonnet-3-5": "anthropic/claude-3.5-sonnet",
    # Google models
    "openai/gemini-2-5-pro": "google/gemini-2.5-pro",
    "openai/gemini-2-5-flash": "google/gemini-2.5-flash",
    "openai/gemini-2-5-flash-lite": "google/gemini-2.5-flash-lite",
    "openai/gemini-pro": "google/gemini-pro",
    "openai/gemini-flash": "google/gemini-flash",
    # Meta models
    "openai/llama-3-1-8b": "meta-llama/llama-3.1-8b-instruct",
    "openai/llama-3-1-70b": "meta-llama/llama-3.1-70b-instruct",
    "openai/llama-3-2-11b": "meta-llama/llama-3.2-11b-instruct",
    "openai/llama-3-2-90b": "meta-llama/llama-3.2-90b-instruct",
    # Mistral models
    "openai/mistral-nemo": "mistralai/mistral-nemo",
    "openai/mistral-large": "mistralai/mistral-large",
    "openai/mixtral-8x7b": "mistralai/mixtral-8x7b-instruct",
    # DeepSeek models
    "openai/deepseek-chat": "deepseek/deepseek-chat",
    "openai/deepseek-coder": "deepseek/deepseek-coder",
    # xAI models
    "openai/grok-2": "xai/xgrok-2",
    "openai/grok-2-mini": "xai/xgrok-2-mini",
    # Perplexity models
    "openai/sonar": "perplexity/sonar",
    "openai/sonar-pro": "perplexity/sonar-pro",
    "openai/sonar-reasoning": "perplexity/sonar-reasoning",
    "openai/sonar-reasoning-pro": "perplexity/sonar-reasoning-pro",
    # Minimax models
    "openai/minimax": "minimax/minimax-m2.7",
    "openai/minimax-m2.7": "minimax/minimax-m2.7",
    "openai/nvidia-mistral-small4": "mistralai/mistral-small-4-119b-2603",
    # LiteLLM proxy default (minimax m2.7)
    "openai/default": "minimax/minimax-m2.7",
}


def resolve_alias(bench_alias: str) -> str | None:
    """Resolve a bench model alias to a KiloCode model ID.

    Args:
        bench_alias: Bench LiteLLM model name, e.g. "openai/qwen-local"

    Returns:
        KiloCode model ID string, or None if alias is unknown.
    """
    return MODEL_ALIAS_MAP.get(bench_alias)


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
