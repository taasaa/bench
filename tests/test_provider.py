"""Tests for the provider resolver (bench_cli/provider.py).

Provider = the brand the user pays for service from, derived strictly
from ~/dev/litellm/config.yaml. The resolver MUST hard-stop on anything
unresolvable — no silent defaults (Tasa's rule, 2026-07-07).

Each test patches the proxy-config loader with a tmp YAML so the resolver
runs against a known fixture config, not the live proxy.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bench_cli.provider import (
    _build_proxy_index,
    format_provider_error,
    resolve_provider,
)


# ---------------------------------------------------------------------------
# Fixtures: tmp LiteLLM config + cached state reset
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_litellm_caches():
    """The provider module caches parsed configs. Clear between tests."""
    from bench_cli import provider as prov_mod

    prov_mod._load_litellm_config.cache_clear()
    prov_mod._build_proxy_index.cache_clear()
    yield
    prov_mod._load_litellm_config.cache_clear()
    prov_mod._build_proxy_index.cache_clear()


def _write_config(tmp_path: Path, yaml_text: str) -> Path:
    """Write a fake ~/dev/litellm/config.yaml and patch the resolver to see it."""
    p = tmp_path / "litellm_config.yaml"
    p.write_text(yaml_text)
    return p


def _patch_config_path(p: Path):
    """Context manager that patches _LITELLM_CONFIG_PATH in both modules."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("bench_cli.pricing.litellm_config._LITELLM_CONFIG_PATH", p))
    stack.enter_context(patch("bench_cli.provider._LITELLM_CONFIG_PATH", p))
    return stack


# ---------------------------------------------------------------------------
# Resolution matrix
# ---------------------------------------------------------------------------


def test_managed_model_returns_local(tmp_path):
    """Local/managed aliases return 'local' (no marketplace provider)."""
    cfg = """\
credential_list:
  - credential_name: qwen-local
    credential_values:
      api_key: os.environ/QWEN_LOCAL_KEY
model_list:
  - model_name: qwen-local
    litellm_params:
      model: openai/qwen-local
      litellm_credential_name: qwen-local
      api_base: http://localhost:1234/v1
"""
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        assert resolve_provider("openai/qwen-local") == "local"


def test_moniker_returns_none_for_hard_stop(tmp_path):
    """Router-tier monikers (default/thinking/heavy/...) hard-stop.

    These resolve dynamically at proxy time — no static provider exists.
    """
    cfg = "model_list: []\n"
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        assert resolve_provider("openai/default") is None
        assert resolve_provider("openai/thinking") is None
        assert resolve_provider("openai/heavy") is None
        assert resolve_provider("openai/background") is None
        assert resolve_provider("openai/smart-router") is None


def test_proxy_entry_with_credential_name(tmp_path):
    """The credential name is the provider (brand the user pays)."""
    cfg = """\
credential_list:
  - credential_name: kilocode
    credential_values:
      api_key: os.environ/KILOCODE_API_KEY
      api_base: https://api.kilo.ai/api/openrouter/
model_list:
  - model_name: kilocode-nemotron-120b
    litellm_params:
      model: openrouter/kilocode/nemotron-3-super-120b
      litellm_credential_name: kilocode
"""
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        assert resolve_provider("openai/kilocode-nemotron-120b") == "kilocode"


def test_proxy_entry_with_nvidia_credential(tmp_path):
    """The 'nvidia' credential resolves as the brand for NIM-direct entries."""
    cfg = """\
credential_list:
  - credential_name: nvidia
    credential_values:
      api_key: os.environ/NVIDIA_API_KEY
model_list:
  - model_name: nvidia-nemotron-120b
    litellm_params:
      model: nvidia_nim/nvidia/nemotron-3-super-120b
      litellm_credential_name: nvidia
"""
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        assert resolve_provider("openai/nvidia-nemotron-120b") == "nvidia"


def test_proxy_entry_with_inline_api_key_uses_transport_prefix(tmp_path):
    """No credential_name but inline api_key → transport prefix is the provider."""
    cfg = """\
model_list:
  - model_name: direct-anthropic
    litellm_params:
      model: anthropic/claude-opus-4.6
      api_key: os.environ/ANTHROPIC_API_KEY
"""
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        assert resolve_provider("openai/direct-anthropic") == "anthropic"


def test_proxy_entry_with_inline_api_base_uses_transport_prefix(tmp_path):
    """No credential_name but inline api_base → transport prefix is the provider."""
    cfg = """\
model_list:
  - model_name: nim-direct
    litellm_params:
      model: nvidia_nim/minimaxai/minimax-m3
      api_key: fake
      api_base: https://integrate.api.nvidia.com/v1
"""
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        assert resolve_provider("openai/nim-direct") == "nvidia_nim"


def test_local_api_base_uses_transport_prefix(tmp_path):
    """A non-managed alias with loopback api_base still records the transport
    prefix as provider. Localness is `is_managed_model()`'s job, not ours.

    If a user wants the run attributed as 'local', they should add the alias
    to `is_managed_model()`. A non-managed alias with a loopback api_base is
    a real provider (transport contract), just served locally.
    """
    cfg = """\
model_list:
  - model_name: omlx-some-model
    litellm_params:
      model: openai/some-model
      api_key: fake
      api_base: http://localhost:8000/v1
"""
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        assert resolve_provider("openai/omlx-some-model") == "openai"


def test_no_proxy_entry_returns_none(tmp_path):
    """A routed alias not in the proxy config hard-stops."""
    cfg = "model_list: []\n"
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        # Not a managed model, not a moniker, not in proxy → hard-stop
        assert resolve_provider("openai/some-unknown-alias") is None


def test_proxy_entry_with_no_credential_returns_none(tmp_path):
    """Proxy entry exists but has NO credential info → hard-stop.

    This is the case the user MUST NOT silently fall through on.
    """
    cfg = """\
model_list:
  - model_name: bare-entry
    litellm_params:
      model: openrouter/some/model
"""
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        assert resolve_provider("openai/bare-entry") is None


def test_proxy_entry_with_empty_credential_returns_none(tmp_path):
    """Empty/whitespace credential name treated as no credential."""
    cfg = """\
model_list:
  - model_name: empty-cred
    litellm_params:
      model: openrouter/some/model
      litellm_credential_name: "   "
"""
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        assert resolve_provider("openai/empty-cred") is None


def test_proxy_index_skips_invalid_entries(tmp_path):
    """Malformed proxy entries (no model_name, no litellm_params) are skipped."""
    cfg = """\
model_list:
  - model_name: valid
    litellm_params:
      model: openrouter/valid/model
      litellm_credential_name: kilocode
  - model_name: ""
    litellm_params:
      model: openrouter/invalid/model
  - not_a_dict: true
"""
    p = _write_config(tmp_path, cfg)
    with _patch_config_path(p):
        idx = _build_proxy_index()
        assert "valid" in idx
        assert "" not in idx
        # Only one valid entry survived
        assert len(idx) == 1


def test_missing_config_file_returns_none(tmp_path):
    """If the config file doesn't exist, ALL non-managed lookups hard-stop."""
    # No file written
    nonexistent = tmp_path / "does_not_exist.yaml"
    with _patch_config_path(nonexistent):
        # Managed short-circuits first, so qwen-local still returns 'local'
        assert resolve_provider("openai/qwen-local") == "local"
        # Everything else hard-stops
        assert resolve_provider("openai/kilocode-nemotron-120b") is None


def test_malformed_yaml_returns_none(tmp_path):
    """If the config is unparseable, all non-managed lookups hard-stop."""
    p = _write_config(tmp_path, "credential_list: [this: is: not: valid: yaml:")
    with _patch_config_path(p):
        assert resolve_provider("openai/qwen-local") == "local"
        assert resolve_provider("openai/anything-else") is None


# ---------------------------------------------------------------------------
# Error message format
# ---------------------------------------------------------------------------


def test_format_provider_error_is_actionable():
    """The hard-stop message points at the config file and shows the fix shape."""
    msg = format_provider_error("openai/kilocode-nemotron-120b")
    assert "kilocode-nemotron-120b" in msg  # alias is named
    assert "litellm/config.yaml" in msg  # config file is named
    assert "litellm_credential_name" in msg  # fix shape is shown
    assert "model_name" in msg  # proxy entry shape is shown
    assert "Cannot determine provider" in msg  # clear why


def test_format_provider_error_strips_openai_prefix():
    """The model_name in the suggested fix uses the bare alias, not openai/X."""
    msg = format_provider_error("openai/foo-bar")
    assert "model_name: foo-bar" in msg
    # The routed name with prefix is in the message too, as the identifier
    assert "openai/foo-bar" in msg
