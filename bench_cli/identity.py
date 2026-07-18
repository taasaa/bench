"""Canonical identity reconciliation for models.

Resolves raw model names found in logs to their backing canonical identities
using the litellm config mapping. Helps merge duplicate or routed aliases.
"""

from __future__ import annotations

from pathlib import Path
from inspect_ai.log import list_eval_logs, read_eval_log
from bench_cli.run.core import resolve_recorded_name


def reconcile_identities(log_dir: str, models: list[str] | None = None) -> dict[str, str]:
    """Scan log directory or use provided model list and map raw names to canonical backing names.

    Returns:
        dict of raw_model_name -> canonical_model_name.
    """
    if models is not None:
        unique_names = set(models)
    else:
        log_path = Path(log_dir)
        if not log_path.is_dir():
            return {}

        unique_names = set()
        infos = list_eval_logs(log_dir=str(log_path))
        for info in infos:
            try:
                el = read_eval_log(info, header_only=True)
                if el.eval and el.eval.model:
                    unique_names.add(el.eval.model)
            except Exception:
                continue

    mapping: dict[str, str] = {}
    for name in unique_names:
        canonical = resolve_recorded_name(name, None)
        mapping[name] = canonical

    return mapping
