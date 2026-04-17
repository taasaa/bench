"""LiteLLM config parser for model alias → OpenRouter ID resolution.

Reads ~/dev/litellm/config.yaml and builds a dict of bench model aliases
(e.g. "openai/nvidia-mistral-small4") → real OpenRouter IDs
(e.g. "openai/mistralai/mistral-small-4-119b-2603").

The LiteLLM config is the source of truth for which model is actually
configured. MODEL_ALIAS_MAP is used as a fallback for models not in config.
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path

import yaml

from bench_cli.pricing.model_aliases import MODEL_ALIAS_MAP

_LITELLM_CONFIG_PATH = Path.home() / "dev" / "litellm" / "config.yaml"


@lru_cache(maxsize=1)
def _load_litellm_alias_map() -> dict[str, str]:
    """Load and parse the LiteLLM config, returning {bench_alias: litellm_model}.

    Returns empty dict if config file is missing or invalid.
    """
    config_path = _LITELLM_CONFIG_PATH

    if not config_path.is_file():
        warnings.warn(
            f"LiteLLM config not found at {config_path}. "
            "Model ID resolution will rely on MODEL_ALIAS_MAP only.",
            RuntimeWarning,
            stacklevel=2,
        )
        return {}

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as exc:
        warnings.warn(
            f"Failed to parse LiteLLM config at {config_path}: {exc}. "
            "Model ID resolution will rely on MODEL_ALIAS_MAP only.",
            RuntimeWarning,
            stacklevel=2,
        )
        return {}

    result: dict[str, str] = {}

    model_list = config.get("model_list", [])
    for entry in model_list:
        if not isinstance(entry, dict):
            continue
        model_name = entry.get("model_name", "")
        litellm_params = entry.get("litellm_params", {})
        if not model_name or not isinstance(litellm_params, dict):
            continue
        litellm_model = litellm_params.get("model", "")
        if litellm_model:
            # LiteLLM uses openai/<provider>/<model-id> format
            # OpenRouter API uses <provider>/<model-id> format (no openai/ prefix)
            result[model_name] = litellm_model

    return result


def resolve_openrouter_id(alias: str) -> str | None:
    """Resolve a bench model alias to the full OpenRouter model ID.

    Resolution order:
      1. LiteLLM config (source of truth for configured models)
      2. MODEL_ALIAS_MAP (fallback for managed/local models)

    Args:
        alias: Bench LiteLLM alias (e.g. "openai/nvidia-mistral-small4").

    Returns:
        OpenRouter model ID string, or None if alias is unknown.
    """
    # LiteLLM config takes priority
    litellm_map = _load_litellm_alias_map()
    litellm_id = litellm_map.get(alias)
    if litellm_id:
        return litellm_id

    # Fall back to MODEL_ALIAS_MAP
    return MODEL_ALIAS_MAP.get(alias)


def is_managed_model(alias: str) -> bool:
    """Return True if alias is a local/proxy model not in OpenRouter catalog.

    Local models (qwen-local, gemma-*-local, glm-local) are managed on-device
    or via custom proxy — they are never in OpenRouter's public catalog.
    They are exempt from the pre-flight price gate.
    """
    # Match bench's naming convention: anything with a -local suffix or
    # known local prefixes.
    if alias.endswith("-local"):
        return True
    # glm-local uses a dash but not -local suffix
    if alias in ("openai/glm-local", "openai/qwen3-coder-plus", "openai/qwen3-max"):
        return True
    return False
