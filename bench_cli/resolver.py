"""Resolve user-supplied model names to canonical openai/<alias> form.

Enables bare names like 'qwen-local' instead of requiring 'openai/qwen-local'.
"""

from __future__ import annotations

import difflib

import click

from bench_cli.pricing.model_aliases import MODEL_ALIAS_MAP


def _build_suffix_map() -> dict[str, str]:
    """Build {bare_suffix: canonical_key} from MODEL_ALIAS_MAP."""
    result: dict[str, str] = {}
    for canonical in MODEL_ALIAS_MAP:
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
    """Return display name: openai/qwen-local -> qwen-local."""
    return canonical.removeprefix("openai/")
