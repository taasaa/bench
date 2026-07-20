"""Resolve user-supplied model names to canonical openai/<alias> form.

Enables bare names like 'qwen-local' instead of requiring 'openai/qwen-local'.

Bare-name candidates come from two sources, merged at import time:
  1. The live LiteLLM proxy config (~/dev/litellm/config.yaml) — primary.
     Every `model_name:` entry contributes its bare suffix (e.g. `qwen-local`,
     `default`, `opus`). Stays in sync with routing automatically.
  2. LOCAL_ONLY_ALIASES — a small hand-maintained constant for managed/local
     aliases that don't have a `model_name:` entry in the proxy config (they
     are short-circuited by `is_managed_model` and never routed, so they don't
     need a proxy binding).

Previously this module built the suffix map from MODEL_ALIAS_MAP. After the
Y-inversion cleanup (2026-06-17), MODEL_ALIAS_MAP is a catch-all for OR-moniker
resolution and is empty by design — using it for bare-name resolution would
silently drop all live aliases. The proxy config is the right source for bare
names (it's already a single source of truth for routing).
"""

from __future__ import annotations

import difflib

import click

from bench_cli.pricing.litellm_config import _load_litellm_alias_map


# Managed/local aliases without a `model_name:` entry in the proxy config.
# Listed explicitly here because the proxy parser can't see them. Keep minimal.
LOCAL_ONLY_ALIASES = (
    "openai/glm-local",
    "openai/qwen3-coder-plus",
    "openai/qwen3-max",
)


def bare_model_name(model: str) -> str:
    """Everything after the first '/' segment, or the whole string if no '/'.

    Handles both proxy-alias form ('openai/thinking' -> 'thinking') and raw
    OpenRouter ids ('minimaxai/minimax-m3' -> 'minimax-m3'). This is the single
    source of truth for display/moniker-check/slug derivation.
    """
    bare = model.split("/", 1)[1] if "/" in model else model
    
    # Dynamically resolve to the "real" underlying model name if this is an alias
    from bench_cli.pricing.litellm_config import _load_litellm_alias_map
    litellm_map = _load_litellm_alias_map()
    
    if bare in litellm_map:
        orid = litellm_map[bare]
        return orid.split("/")[-1]
        
    return bare


def _build_suffix_map() -> dict[str, str]:
    """Build {bare_suffix: canonical_key} from live proxy config + local aliases.

    Proxy keys come back bare (e.g. 'qwen-local'); we add the 'openai/' prefix
    so resolve_model('qwen-local') -> 'openai/qwen-local'. Local-only entries
    are already in openai/<bare> form.
    """
    result: dict[str, str] = {}
    for bare in _load_litellm_alias_map():
        result[bare] = f"openai/{bare}"
    for canonical in LOCAL_ONLY_ALIASES:
        if "/" in canonical:
            suffix = canonical.split("/", 1)[1]
            result[suffix] = canonical
    return result


_SUFFIX_MAP = _build_suffix_map()


def resolve_model(raw: str) -> str:
    """Resolve user input to canonical openai/<alias> form.

    Rules:
    1. Contains '/' -> use as-is (backward compat)
    2. Exact match for alias suffix -> resolve
    3. Unique prefix match -> resolve
    4. Ambiguous prefix -> error with candidates
    5. No match -> return openai/{raw} (let downstream fail naturally)
    """
    if "/" in raw:
        return raw

    if raw in _SUFFIX_MAP:
        return _SUFFIX_MAP[raw]

    prefix_matches = [s for s in _SUFFIX_MAP if s.startswith(raw)]
    if len(prefix_matches) == 1:
        return _SUFFIX_MAP[prefix_matches[0]]

    if len(prefix_matches) > 1:
        candidates = ", ".join(prefix_matches[:5])
        raise click.BadParameter(f"Ambiguous '{raw}'. Did you mean: {candidates}?")

    close = difflib.get_close_matches(raw, _SUFFIX_MAP.keys(), n=3, cutoff=0.6)
    if close:
        candidates = ", ".join(close)
        raise click.BadParameter(f"Unknown model '{raw}'. Closest: {candidates}")

    return f"openai/{raw}"


def bare_name(canonical: str) -> str:
    """Return display name: openai/qwen-local -> qwen-local, minimaxai/minimax-m3 -> minimax-m3."""
    return bare_model_name(canonical)
