"""LiteLLM config parser for model alias → OpenRouter ID resolution.

Reads ~/dev/litellm/config.yaml and resolves bench model aliases
(e.g. "openai/nvidia-nemotron-30b") to real OpenRouter model IDs
(e.g. "nvidia/nemotron-3-nano-30b-a3b").

Resolution order:
  1. LiteLLM config → OpenRouter cache lookup (happy path for most models)
  2. Persistent overrides (human-validated slug corrections)
If an override is stale (model dropped from cache), raises RuntimeError.
"""

from __future__ import annotations

import json
import warnings
from functools import lru_cache
from pathlib import Path

import yaml

_LITELLM_CONFIG_PATH = Path.home() / "dev" / "litellm" / "config.yaml"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OVERRIDES_PATH = _PROJECT_ROOT / "logs" / "pricing" / "model_overrides.json"
_OPENAI_PREFIX = "openai/"


# ---------------------------------------------------------------------------
# Persistent overrides
# ---------------------------------------------------------------------------


def _load_overrides() -> dict[str, str]:
    """Load persistent model ID overrides from logs/pricing/model_overrides.json."""
    if not _OVERRIDES_PATH.is_file():
        return {}
    try:
        return json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_override(bench_alias: str, openrouter_id: str) -> None:
    """Persist a model ID override, but only if it exists in the OpenRouter cache."""
    from bench_cli.pricing.price_cache import OpenRouterCache

    cache = OpenRouterCache()
    all_prices = cache.get_all_prices()
    if openrouter_id not in all_prices:
        raise ValueError(
            f"Cannot save override: '{openrouter_id}' not found in OpenRouter cache. "
            "Refresh the cache first with: bench prices refresh"
        )

    overrides = _load_overrides()
    overrides[bench_alias] = openrouter_id
    _OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OVERRIDES_PATH.write_text(
        json.dumps(overrides, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# LiteLLM config
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_litellm_alias_map() -> dict[str, str]:
    """Load and parse the LiteLLM config, returning {bench_alias: openrouter_id}.

    Returns empty dict if config file is missing or invalid.

    For routing layers (auto_router/complexity_router), resolves to the default
    tier's OpenRouter ID by reading complexity_router_default_model and looking
    up that tier name in the same config.
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

    # Build tier name → openrouter_id map from the same config.
    # Used to resolve routing-layer default tiers.
    tier_to_orid: dict[str, str] = {}
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
        _, _, openrouter_id = litellm_model.partition("/")
        if not openrouter_id:
            openrouter_id = litellm_model
        tier_to_orid[model_name] = openrouter_id.lower()

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

        # For routing layers (auto_router/...), resolve to default tier's ID
        if litellm_model.startswith("auto_router/"):
            default_tier = litellm_params.get("complexity_router_default_model", "")
            default_orid = tier_to_orid.get(default_tier, "")
            if default_orid:
                result[model_name] = default_orid
                continue
            # No default tier found, fall through to stripped model

        # Standard: strip provider prefix → OpenRouter ID
        _, _, openrouter_id = litellm_model.partition("/")
        if not openrouter_id:
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


def _resolve_from_litellm(alias: str) -> str | None:
    """Resolve alias from LiteLLM config, return OpenRouter slug or None."""
    litellm_map = _load_litellm_alias_map()

    lookup_key = alias[len(_OPENAI_PREFIX) :] if alias.startswith(_OPENAI_PREFIX) else alias
    openrouter_id = litellm_map.get(lookup_key.lower())

    if openrouter_id is None:
        return None

    if "/" not in openrouter_id:
        return _build_reverse_lookup().get(openrouter_id, openrouter_id)

    return openrouter_id


def resolve_openrouter_id(alias: str) -> str | None:
    """Resolve a bench model alias to an OpenRouter ID present in the price cache.

    Resolution order:
      1. Persistent overrides (human-validated slug corrections)
      2. LiteLLM config → verify slug is in OpenRouter cache (happy path)
      3. If an override exists but the model was dropped from cache → error

    Returns:
        OpenRouter model ID that IS in the cache, or None if alias is unknown.

    Raises:
        RuntimeError: if an override exists but the model is no longer in cache.
    """
    from bench_cli.pricing.price_cache import OpenRouterCache

    cache = OpenRouterCache()
    all_prices = cache.get_all_prices()

    # 1. Try persistent overrides first (e.g. :free → paid variant)
    overrides = _load_overrides()
    override_id = overrides.get(alias)
    if override_id is not None:
        if override_id in all_prices:
            return override_id
        raise RuntimeError(
            f"Stale override for {alias}: '{override_id}' is no longer in the "
            "OpenRouter price cache. The model may have been delisted. "
            "Update the override or refresh the cache."
        )

    # 2. Try LiteLLM config resolution — verify against cache
    litellm_id = _resolve_from_litellm(alias)
    if litellm_id is not None and litellm_id in all_prices:
        return litellm_id

    # LiteLLM resolved but slug not in cache, and no override — return the slug
    # anyway so callers can decide (price gate will block, scorer will NaN)
    if litellm_id is not None:
        return litellm_id

    return None


def is_managed_model(alias: str) -> bool:
    """Return True if alias is a local/proxy model not in OpenRouter catalog."""
    if alias.endswith("-local"):
        return True
    if alias in ("openai/glm-local", "openai/qwen3-coder-plus", "openai/qwen3-max"):
        return True
    return False


def get_router_tiers(alias: str) -> list[str] | None:
    """Return ordered list of tier names for a router model, or None if not a router.

    Reads the full LiteLLM config entry for the given alias and extracts
    complexity_router_config.tiers values. Returns the tier names in tier order
    (SIMPLE, MEDIUM, COMPLEX, REASONING) without duplicates.
    """
    lookup_key = alias[len(_OPENAI_PREFIX) :] if alias.startswith(_OPENAI_PREFIX) else alias
    litellm_map = _load_litellm_alias_map()

    # Re-parse config to access full entry (litellm_map only has stripped IDs)
    if not _LITELLM_CONFIG_PATH.is_file():
        return None
    try:
        with open(_LITELLM_CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None

    tiers_seen: list[str] = []
    for entry in config.get("model_list", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("model_name", "").lower() != lookup_key.lower():
            continue
        model_info = entry.get("model_info", {})
        if not model_info.get("router"):
            return None  # exists but not a router
        router_config = entry.get("litellm_params", {}).get("complexity_router_config", {})
        tier_map = router_config.get("tiers", {})
        for key in ("SIMPLE", "MEDIUM", "COMPLEX", "REASONING"):
            tier_name = tier_map.get(key)
            if tier_name and tier_name not in tiers_seen:
                tiers_seen.append(tier_name)
        return tiers_seen

    return None  # not in config at all
