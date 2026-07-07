"""LiteLLM config parser for model alias → OpenRouter ID resolution.

Reads ~/dev/litellm/config.yaml and resolves bench model aliases
(e.g. "openai/nvidia-nemotron-30b") to real OpenRouter model IDs
(e.g. "nvidia/nemotron-3-nano-30b-a3b").

Resolution order:
  1. Persistent overrides (human-validated slug corrections)
  2. MODEL_ALIAS_MAP — deterministic static bench_alias → OpenRouter id
     (fires only when the mapped id is present in the cache; skipped for
     managed/local models, which are pricing-exempt by design)
  3. LiteLLM config → OpenRouter cache lookup (happy path for most models)
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

    # Single pass: collect tier->orid and alias->orid in one loop
    tier_to_orid: dict[str, str] = {}
    alias_to_orid: dict[str, str] = {}

    def _extract_orid(litellm_model: str) -> str:
        _, _, openrouter_id = litellm_model.partition("/")
        return openrouter_id.lower() if openrouter_id else litellm_model.lower()

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

        orid = _extract_orid(litellm_model)
        alias_to_orid[model_name] = orid
        tier_to_orid[model_name] = orid

    # Resolve routing layers to their default tier
    for entry in config.get("model_list", []):
        if not isinstance(entry, dict):
            continue
        model_name = entry.get("model_name", "")
        litellm_params = entry.get("litellm_params", {})
        if not model_name or not isinstance(litellm_params, dict):
            continue
        litellm_model = litellm_params.get("model", "")
        if not litellm_model.startswith("auto_router/"):
            continue

        default_tier = litellm_params.get("complexity_router_default_model", "")
        if default_tier and (orid := tier_to_orid.get(default_tier)):
            alias_to_orid[model_name] = orid

    return alias_to_orid


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

    The live LiteLLM proxy config (`~/dev/litellm/config.yaml`) is the primary
    source of truth for routing. This resolver consults it first via
    `_resolve_from_litellm()` so that recorded identity and pricing track the
    model actually being called today, not a stale static alias.

    Resolution order:
      0. Managed/local models (is_managed_model) — pricing-exempt, return None.
      1. Persistent overrides (logs/pricing/model_overrides.json) — human-
         validated slug corrections (e.g. :free → paid variant). Pricing only.
      2. Live LiteLLM config — primary source of truth (parsed each call).
      3. MODEL_ALIAS_MAP — catch-all for aliases the proxy can't auto-resolve.
         Empty by design; update the proxy config first.
      4. If an override exists but the model was dropped from cache → error.

    Returns:
        OpenRouter model ID that IS in the cache, or None if alias is unknown.

    Raises:
        RuntimeError: if an override exists but the model is no longer in cache.
    """
    from bench_cli.pricing.price_cache import OpenRouterCache
    from bench_cli.pricing.model_aliases import MODEL_ALIAS_MAP

    cache = OpenRouterCache()
    all_prices = cache.get_all_prices()

    # 0. Managed/local models — pricing-exempt; resolve_recorded_name
    #    short-circuits these in the caller, and pricing is skipped here.
    if is_managed_model(alias):
        return None

    # 1. Try persistent overrides first (e.g. :free → paid variant).
    #    Pricing-only; resolved ids here are intentional corrections, not
    #    bindings to live routing. See logs/pricing/model_overrides.json.
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

    # 2. Live LiteLLM config — the proxy is the source of truth for routing.
    litellm_id = _resolve_from_litellm(alias)
    if litellm_id is not None and litellm_id in all_prices:
        return litellm_id

    # 3. MODEL_ALIAS_MAP catch-all (empty by design). Only fires when the proxy
    #    has no model_name entry for the alias AND a human has explicitly added
    #    an OR-id mapping here.
    mapped_id = MODEL_ALIAS_MAP.get(alias)
    if mapped_id is not None and mapped_id in all_prices:
        return mapped_id

    # LiteLLM resolved but slug not in cache, and no override or map entry —
    # return the slug anyway so callers can decide (price gate will block,
    # scorer will NaN). This preserves behavior for OR-ids that resolve live
    # but aren't priced yet.
    if litellm_id is not None:
        return litellm_id

    return None


def resolve_backing_model_id(alias: str) -> str | None:
    """Resolve a bench alias to its actual backing OpenRouter id, IGNORING the
    pricing override map.

    Use this (not resolve_openrouter_id) when you need the *real* backing model
    for identity/recording, not the pricing correction. The bracket pricing
    override (logs/pricing/model_overrides.json) is pricing-only and must not
    leak into the recorded model identity (spec Non-Goal).

    Resolution order (no override lookup; managed short-circuit lives in the
    caller `resolve_recorded_name` so this function returns None for them):
      1. Live LiteLLM config — primary source of truth.
      2. MODEL_ALIAS_MAP catch-all (empty by design).
    """
    from bench_cli.pricing.model_aliases import MODEL_ALIAS_MAP

    # 1. Live LiteLLM config — the proxy is the source of truth for routing.
    litellm_id = _resolve_from_litellm(alias)

    # 2. MODEL_ALIAS_MAP catch-all (empty by design).
    mapped_id = MODEL_ALIAS_MAP.get(alias)
    if mapped_id is not None and litellm_id is None:
        return mapped_id

    # May be None; caller (resolve_recorded_name) decides the fallback.
    return litellm_id


def is_managed_model(alias: str) -> bool:
    """Return True if alias is a local/proxy model not in OpenRouter catalog."""
    if alias.endswith("-local"):
        return True
    if alias in ("openai/glm-local", "openai/qwen3-coder-plus", "openai/qwen3-max"):
        return True
    return False


# ---------------------------------------------------------------------------
# Market price resolution — single source of truth for cost-pillar pricing.
#
# Contract: every cost calculation in bench MUST use the model's DEFAULT
# (paid-tier) market price, regardless of how the user currently accesses it.
# A model that's free today via NIM/OpenRouter :free quota might cost money
# tomorrow; the cost pillar must compare on price-as-it-would-be, not price-as-
# the-user-pays-right-now.
#
# Resolution order:
#   1. LiteLLM config (~/dev/litellm/config.yaml) — authoritative. The
#      `model_info.input_cost_per_token` / `output_cost_per_token` fields
#      must hold the DEFAULT paid-tier price; bench does this for :free
#      aliases too, so no special-casing is needed here.
#   2. OpenRouter cache — for models NOT in the local LiteLLM proxy (e.g.
#      benchmark-only entries). :free variants are auto-resolved to the
#      paid variant (strip ":free" suffix).
#   3. None — caller treats as anomaly (NaN), never as "FREE".
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_litellm_pricing_map() -> dict[str, tuple[float, float]]:
    """Load LiteLLM pricing into {model_name: (input_per_M, output_per_M)}.

    Keyed by BOTH the bench alias (model_name) AND the OpenRouter id (the
    stripped `litellm_params.model` value) so callers that only have the OR
    id (e.g. card regen from recorded-identity logs) can still resolve
    pricing without a reverse-lookup dance.

    Returns empty dict if config is missing or invalid.
    """
    if not _LITELLM_CONFIG_PATH.is_file():
        return {}
    try:
        with open(_LITELLM_CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return {}

    result: dict[str, tuple[float, float]] = {}
    for entry in config.get("model_list", []):
        if not isinstance(entry, dict):
            continue
        model_name = entry.get("model_name", "")
        model_info = entry.get("model_info", {})
        litellm_params = entry.get("litellm_params", {})
        if not model_name or not isinstance(model_info, dict):
            continue
        inp = model_info.get("input_cost_per_token")
        out = model_info.get("output_cost_per_token")
        if inp is None or out is None:
            continue
        # LiteLLM stores per-token; convert to per-million (bench convention).
        price = (float(inp) * 1_000_000, float(out) * 1_000_000)
        result[model_name.lower()] = price
        # Also key by the OpenRouter id (stripped provider prefix from the
        # litellm_model path) so log-driven lookups work directly.
        litellm_model = litellm_params.get("model", "") if isinstance(litellm_params, dict) else ""
        _, _, openrouter_id = litellm_model.partition("/")
        if openrouter_id:
            result[openrouter_id.lower()] = price
    return result


def get_litellm_market_price(alias: str) -> tuple[float, float] | None:
    """Return (input_price_per_M, output_price_per_M) from the LiteLLM config.

    Strips the "openai/" prefix and matches case-insensitively against
    `model_name` entries in ~/dev/litellm/config.yaml. Returns None if the
    alias isn't configured or has no pricing fields set.
    """
    if not alias:
        return None
    lookup_key = alias[len(_OPENAI_PREFIX):] if alias.startswith(_OPENAI_PREFIX) else alias
    return _load_litellm_pricing_map().get(lookup_key.lower())


def resolve_market_price(
    alias: str | None = None,
    or_id: str | None = None,
) -> tuple[float, float] | None:
    """Resolve the model's DEFAULT market price (per-M USD) for cost calculations.

    Always returns the paid-tier price, regardless of whether the user is
    currently accessing the model free (e.g. NIM quota, OpenRouter :free).
    Never returns "0.0 / 0.0" for a known model — if both sources miss,
    returns None so the caller can flag an anomaly instead of rendering
    "FREE" (which is reserved for managed/local models with genuinely no
    market price).

    Resolution order:
      1. LiteLLM config pricing for `alias` (authoritative for proxied models).
      2. OpenRouter cache for `or_id` (or alias-resolved or_id), with :free
         auto-resolved to the paid variant.
      3. None — caller records anomaly (NaN), does not show "FREE".
    """
    # 1. LiteLLM config — covers proxied models (NIM, direct, :free variants
    #    we explicitly priced at the paid-tier rate).
    if alias:
        litellm_price = get_litellm_market_price(alias)
        if litellm_price is not None:
            return litellm_price

    # 2. OpenRouter cache — covers unproxied benchmark-only entries. Strip
    #    ":free" suffix so we get the paid variant's real price, not $0/$0.
    target_or_id = or_id
    if target_or_id is None and alias is not None:
        target_or_id = resolve_openrouter_id(alias)
    if target_or_id is None:
        return None
    try:
        from bench_cli.pricing.price_cache import OpenRouterCache

        cache = OpenRouterCache()
        paid_id = target_or_id.replace(":free", "") if ":free" in target_or_id else target_or_id
        price_info = cache.get_price(paid_id)
    except Exception:
        return None

    if price_info.input_price == 0.0 and price_info.output_price == 0.0:
        # Both zero — only acceptable for genuinely-free models (rare).
        # Treat as no price so the caller doesn't accidentally claim "FREE"
        # for a model that should have a paid-tier price.
        return None
    return (price_info.input_price, price_info.output_price)


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
