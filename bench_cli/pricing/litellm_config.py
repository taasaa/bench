"""LiteLLM config parser for model alias → OpenRouter ID resolution.

Reads ~/dev/litellm/config.yaml and resolves bench model aliases
(e.g. "openai/nvidia-nemotron-30b") to real OpenRouter model IDs
(e.g. "nvidia/nemotron-3-nano-30b-a3b").

The LiteLLM config is the ONLY source of truth for model ID resolution.
The openai/ prefix is stripped from provider endpoints because OpenRouter
uses <provider>/<model-id> format, not the LiteLLM openai/<provider>/<model> convention.
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path

import yaml

_LITELLM_CONFIG_PATH = Path.home() / "dev" / "litellm" / "config.yaml"
_OPENAI_PREFIX = "openai/"
_THREE_PART_PREFIXES = frozenset({"openai/nvidia/", "openai/qwen/", "openai/mistralai/"})


@lru_cache(maxsize=1)
def _load_litellm_alias_map() -> dict[str, str]:
    """Load and parse the LiteLLM config, returning {bench_alias: openrouter_id}.

    Returns empty dict if config file is missing or invalid.
    """
    if not _LITELLM_CONFIG_PATH.is_file():
        warnings.warn(
            f"LiteLLM config not found at {_LITELLM_CONFIG_PATH}. "
            "resolve_openrouter_id() will return None for all models.",
            RuntimeWarning,
            stacklevel=2,
        )
        return {}

    try:
        with open(_LITELLM_CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as exc:
        warnings.warn(
            f"Failed to parse LiteLLM config at {_LITELLM_CONFIG_PATH}: {exc}. "
            "resolve_openrouter_id() will return None for all models.",
            RuntimeWarning,
            stacklevel=2,
        )
        return {}

    result: dict[str, str] = {}

    for entry in config.get("model_list", []):
        if not isinstance(entry, dict):
            continue
        model_name = entry.get("model_name", "")
        litellm_params = entry.get("litellm_params", {})
        if not model_name or not isinstance(litellm_params, dict):
            continue
        litellm_model = litellm_params.get("model", "")
        if not litellm_model:
            continue
        if any(litellm_model.startswith(p) for p in _THREE_PART_PREFIXES):
            openrouter_id = litellm_model[len(_OPENAI_PREFIX) :]
        else:
            openrouter_id = litellm_model
        result[model_name] = openrouter_id.lower()

    return result


@lru_cache(maxsize=1)
def _build_reverse_lookup() -> dict[str, str]:
    """Build a reverse map from model name → full OpenRouter ID.

    E.g. "minimax-m2.7" → "minimax/minimax-m2.7".
    Cached to avoid repeated disk reads.
    """
    from bench_cli.pricing.price_cache import OpenRouterCache

    cache = OpenRouterCache()
    result: dict[str, str] = {}
    for cached_id in cache.get_all_prices():
        _, _, model = cached_id.partition("/")
        if model:
            result[model.lower()] = cached_id
    return result


def resolve_openrouter_id(alias: str) -> str | None:
    """Resolve a bench model alias to the OpenRouter model ID.

    Source of truth: ~/dev/litellm/config.yaml only.

    Args:
        alias: Bench LiteLLM alias (e.g. "openai/nvidia-nemotron-30b").

    Returns:
        OpenRouter model ID (e.g. "nvidia/nemotron-3-nano-30b-a3b"),
        or None if alias is not in the LiteLLM config.
    """
    litellm_map = _load_litellm_alias_map()

    lookup_key = alias[len(_OPENAI_PREFIX) :] if alias.startswith(_OPENAI_PREFIX) else alias
    openrouter_id = litellm_map.get(lookup_key.lower())

    if openrouter_id is None:
        return None

    if openrouter_id.startswith(_OPENAI_PREFIX):
        openrouter_id = openrouter_id[len(_OPENAI_PREFIX) :]

    if "/" not in openrouter_id:
        return _build_reverse_lookup().get(openrouter_id, openrouter_id)

    return openrouter_id


def is_managed_model(alias: str) -> bool:
    """Return True if alias is a local/proxy model not in OpenRouter catalog."""
    if alias.endswith("-local"):
        return True
    if alias in ("openai/glm-local", "openai/qwen3-coder-plus", "openai/qwen3-max"):
        return True
    return False
