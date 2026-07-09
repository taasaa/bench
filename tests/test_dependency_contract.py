"""Pinned dep floors for the Inspect AI 0.3.245 upgrade.

These tests assert that `pyproject.toml` declares the exact floors the
upgrade plan requires. They run hermetically against the on-disk text
(no pip install needed) so they catch accidental floor regressions in
CI without waiting for a full `pip install -U`.

The actual importable versions are checked separately in test_inspect_compat.py
and via `.venv/bin/python -c "import inspect_ai; print(...)"`.
"""

from __future__ import annotations

from pathlib import Path


def test_inspect_upgrade_dependency_floors_are_explicit() -> None:
    text = Path("pyproject.toml").read_text()
    assert '"inspect-ai>=0.3.245,<0.4"' in text
    assert '"openai>=2.40.0"' in text
    assert '"inspect-swe>=0.2.65"' in text
