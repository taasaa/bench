"""Provider resolution for eval runs.

The "provider" of a bench eval run is the brand the user is paying for
service from — the credential in the LiteLLM proxy config. Recording it
explicitly makes per-provider analysis (latency, consistency, timeouts)
possible without changing how the run is identified or priced.

Resolution is strict and observable:

  1. Managed/local models → "local"  (no provider in the marketplace sense)
  2. Router-tier monikers (default/thinking/heavy/...) → None, hard-stop.
     These resolve dynamically at proxy time; no static provider exists.
  3. Proxy entry with litellm_credential_name → that credential name
     (e.g. "kilocode", "nvidia", "alibaba", "minimax"). This is the brand
     the user pays — the api key + base URL live under that name in
     credential_list.
  4. Proxy entry with inline api_key / api_base in litellm_params (no
     credential_name) → litellm_params.model's transport prefix
     (e.g. "nvidia_nim", "openai", "anthropic", "openrouter").
  5. Anything else → None, hard-stop. The run MUST be representable as
     (model, provider) per Tasa's "no silent defaults" rule.

No OR id fallback. If the user passes a raw OR id with no proxy entry,
the resolver returns None and the caller must surface a hard-stop with
an actionable fix.

This module is pure: it reads ~/dev/litellm/config.yaml (cached) and
returns a string. It does no I/O against OpenRouter, no proxy calls.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# Re-export for tests that patch the path. Both provider and litellm_config
# point at the same file; tests patch the path on the litellm_config side
# (which is the canonical location) and we read from that same file here.
from bench_cli.pricing.litellm_config import _LITELLM_CONFIG_PATH


@lru_cache(maxsize=1)
def _load_litellm_config() -> dict[str, Any] | None:
    """Load ~/dev/litellm/config.yaml. Returns None if missing or invalid."""
    path = Path(_LITELLM_CONFIG_PATH)
    if not path.is_file():
        return None
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None
    return data if isinstance(data, dict) else None


@lru_cache(maxsize=1)
def _build_proxy_index() -> dict[str, dict[str, Any]]:
    """Map {model_name: litellm_params} for every proxy entry.

    `model_name` is the alias registered in LiteLLM (e.g. "kilocode-nemotron-120b"),
    NOT the openai/-prefixed form. Callers strip the openai/ prefix before lookup.
    Skips entries with empty model_name or litellm_params.model.
    """
    cfg = _load_litellm_config()
    if not cfg:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for entry in cfg.get("model_list", []) or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("model_name")
        params = entry.get("litellm_params")
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(params, dict):
            continue
        if not params.get("model"):
            continue
        index[name] = params
    return index


def _strip_openai_prefix(alias: str) -> str:
    """Strip the openai/ prefix that bench prepends to routed aliases.

    `openai/kilocode-nemotron-120b` → `kilocode-nemotron-120b` for proxy lookup.
    """
    if alias.startswith("openai/"):
        return alias[len("openai/"):]
    return alias


def _is_local_api_base(api_base: object) -> bool:
    """DEPRECATED — kept for compatibility; not used in resolution anymore.

    Localness is determined by `is_managed_model()`, not by api_base prefix.
    A non-managed alias with a loopback api_base is still a real provider
    (the transport contract), just served locally.
    """
    if not isinstance(api_base, str):
        return False
    return any(api_base.startswith(p) for p in (
        "http://localhost",
        "http://127.0.0.1",
        "http://0.0.0.0",
        "http://[::1]",
    ))


def _provider_from_inline_credentials(params: dict[str, Any]) -> str | None:
    """Resolve provider from a proxy entry with NO litellm_credential_name.

    Strategy: take the transport prefix of params.model
    (e.g. "nvidia_nim", "openrouter", "openai", "anthropic"). If no slash,
    the model name IS the transport (e.g. params.model = "openai" with no
    upstream route) — return None.
    """
    model_field = params.get("model", "")
    if not isinstance(model_field, str) or "/" not in model_field:
        return None
    transport = model_field.split("/", 1)[0].strip()
    return transport or None


def resolve_provider(routed_name: str) -> str | None:
    """Resolve the provider of a bench eval run from the LiteLLM config.

    Args:
        routed_name: the --model value sent to the proxy (e.g.
            "openai/kilocode-nemotron-120b" or "openai/qwen-local").

    Returns:
        Provider string (e.g. "kilocode", "nvidia", "nvidia_nim", "openai",
        "anthropic", "openrouter", "local"), or None if unresolvable.
        None means the caller MUST hard-stop with a question — the run
        cannot be attributed to a provider.
    """
    from bench_cli.pricing.litellm_config import is_managed_model
    from bench_cli.results.core import is_moniker_alias

    # 1. Managed/local short-circuit. These are explicitly local runs
    #    (qwen-local, gemma-*-local, omlx-*, etc.) — no marketplace provider.
    if is_managed_model(routed_name):
        return "local"

    # 2. Router-tier monikers (default/thinking/heavy/background/smart-router)
    #    resolve dynamically at proxy time. No static provider can be
    #    attributed; hard-stop so Tasa picks an explicit alias.
    if is_moniker_alias(routed_name):
        return None

    # 3+4. Look up proxy entry.
    index = _build_proxy_index()
    params = index.get(_strip_openai_prefix(routed_name))
    if params is None:
        return None  # not in proxy config — caller hard-stops

    # 3. credential name = the brand the user is paying.
    cred = params.get("litellm_credential_name")
    if isinstance(cred, str) and cred.strip():
        return cred.strip()

    # 4. Inline api_key / api_base → use the transport prefix.
    if params.get("api_key") or params.get("api_base"):
        return _provider_from_inline_credentials(params)

    # 4b. chatgpt/* transport fallback (0.3.245 upgrade). The Codex/ChatGPT
    # LiteLLM endpoint declares `model: chatgpt/gpt-5.5` WITHOUT inline
    # api_key/api_base or a litellm_credential_name — it authenticates via
    # ~/.chatgpt_token/ OAuth. So the check must live in the fall-through
    # path, NOT inside the inline-credentials branch above (where it would
    # be unreachable for the real proxy config). Surface the transport as
    # the provider so per-provider analysis attributes these runs to
    # `chatgpt` rather than hard-stopping on missing credentials.
    model_field = params.get("model")
    if isinstance(model_field, str) and model_field.startswith("chatgpt/"):
        return "chatgpt"

    # 5. Proxy entry exists but has no credential info whatsoever.
    return None


def format_provider_error(routed_name: str) -> str:
    """Build the hard-stop message for an unresolvable provider.

    Specific, actionable, points at the LiteLLM config and shows the
    required shape. The user is told exactly what to do.
    """
    short = _strip_openai_prefix(routed_name)
    return (
        f"Cannot determine provider for model '{routed_name}'.\n"
        f"\n"
        f"Provider must be derivable from ~/dev/litellm/config.yaml — either\n"
        f"a credential name (the brand you pay) or an inline api_key/api_base.\n"
        f"\n"
        f"To fix, add a proxy entry with a credential. Example:\n"
        f"  - model_name: {short}\n"
        f"    litellm_params:\n"
        f"      model: openrouter/<vendor>/<model-id>\n"
        f"      litellm_credential_name: <credential-name>\n"
        f"\n"
        f"Or pass a different alias that already has a known credential."
    )
