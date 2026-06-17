"""Designated Tier-1 reference model for the ratio pillars (W3 coherence).

A single recorded model (e.g. openai/minimax-m3) becomes the unified reference
for token, latency, AND cost ratio pillars. Scorers and compare resolve ratios
against THIS model, not against the subject under test, so 'ratio=1.0' means one
thing across all columns (PRD Goal #5).

Persisted at baselines/reference_model.json (monkeypatchable via _REFERENCE_FILE).
"""

from __future__ import annotations

import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REFERENCE_FILE = _PROJECT_ROOT / "baselines" / "reference_model.json"


def get_reference_model_id() -> str | None:
    """Return the designated reference model id, or None if none is registered."""
    if not _REFERENCE_FILE.is_file():
        return None
    try:
        data = json.loads(_REFERENCE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    mid = data.get("model_id") if isinstance(data, dict) else None
    return mid if isinstance(mid, str) and mid else None


def set_reference_model_id(model_id: str) -> None:
    """Designate model_id as the unified Tier-1 reference for all ratio pillars."""
    _REFERENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _REFERENCE_FILE.write_text(
        json.dumps({"model_id": model_id}, indent=2) + "\n", encoding="utf-8"
    )
