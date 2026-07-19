"""Tests for the pre-flight provider-collision check
(bench_cli/run/cli.py::_check_provider_collision).

If a log already exists under the same recorded identity from a DIFFERENT
provider, the new run MUST not silently replace it. The check reads
header_only (cheap) and returns a collision descriptor on first conflict
found, which the CLI turns into a click.ClickException with a clear fix.

Legacy logs (no `bench_provider` in header) are ignored by the collision
check \u2014 they may legitimately belong to the new provider. The per-task
dedup handles those via a one-time warning.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from bench_cli.run.cli import _check_provider_collision


# ---------------------------------------------------------------------------
# Fixtures (same pattern as test_dedup_provider.py)
# ---------------------------------------------------------------------------


_TPL_DIR = Path(__file__).resolve().parent.parent / "logs"


def _find_template_log() -> Path:
    candidates = sorted(
        _TPL_DIR.glob("*.eval"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in candidates:
        if p.stat().st_size > 1000:
            try:
                with zipfile.ZipFile(p) as zf:
                    if "header.json" in zf.namelist():
                        return p
            except Exception:
                continue
    raise RuntimeError("No real eval log available to use as template")



def _write_log(
    template: Path,
    log_dir: Path,
    *,
    task_token: str,
    model: str,
    provider: str | None = None,
    uuid_suffix: str = "AAAAAA",
) -> Path:
    name = f"2026-07-07T00-00-00-00-00_{task_token}_{uuid_suffix}.eval"
    log_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template) as zin:
        with zipfile.ZipFile(log_dir / name, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for inner in zin.namelist():
                data = zin.read(inner)
                if inner == "header.json":
                    hdr = json.loads(data)
                    hdr["status"] = "success"
                    hdr["eval"]["model"] = model
                    hdr["eval"]["task"] = task_token
                    hdr["eval"]["task_display_name"] = task_token
                    meta = {"bench_provider": provider} if provider is not None else {}
                    hdr["eval"]["metadata"] = meta
                    hdr["metadata"] = meta
                    data = json.dumps(hdr).encode()
                zout.writestr(inner, data)
    return log_dir / name


@pytest.fixture
def template_log() -> Path:
    return _find_template_log()


# ---------------------------------------------------------------------------
# Core: collision detection
# ---------------------------------------------------------------------------


def test_no_collision_when_no_logs(tmp_path):
    """Empty log dir → no collision."""
    assert (
        _check_provider_collision(str(tmp_path), "z-ai/glm-5.2", "kilocode") is None
    )


def test_no_collision_for_different_model(tmp_path, template_log):
    """Logs for a different model don't trigger collision."""
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="nvidia/nemotron-3-super-120b",
        provider="kilocode",
    )
    # New run is for a different model → no collision
    assert (
        _check_provider_collision(str(tmp_path), "z-ai/glm-5.2", "kilocode") is None
    )


def test_no_collision_when_providers_match(tmp_path, template_log):
    """Same provider for the same model → no collision (normal resume case)."""
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        provider="kilocode",
    )
    # Same provider → not a collision, the dedup path will skip it
    assert (
        _check_provider_collision(str(tmp_path), "z-ai/glm-5.2", "kilocode") is None
    )


def test_collision_detected_for_different_provider(tmp_path, template_log):
    """THE critical test: same model, different provider → collision.

    Kilocode and nvidia runs of the same model must not silently replace
    one another. The check returns a collision descriptor; the CLI turns
    this into a hard-stop with a clear fix.
    """
    existing_path = _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        provider="kilocode",  # existing was kilocode
    )
    collision = _check_provider_collision(
        str(tmp_path), "z-ai/glm-5.2", "nvidia"  # new is nvidia
    )
    assert collision is not None
    assert collision["existing_provider"] == "kilocode"
    assert "f1-multi-file-verify" in collision["path"]


def test_legacy_log_does_not_trigger_collision(tmp_path, template_log, capsys):
    """Legacy log (no bench_provider) is treated as 'unknown' → no collision.

    The new run is allowed to proceed; the per-task dedup will handle
    legacy logs with a one-time warning.
    """
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        provider=None,  # legacy
    )
    collision = _check_provider_collision(
        str(tmp_path), "z-ai/glm-5.2", "nvidia"
    )
    assert collision is None


def test_mixed_legacy_and_provider_logs(tmp_path, template_log):
    """Legacy log + provider-tagged log with different provider:
    - Legacy doesn't trigger collision
    - Provider-tagged DOES trigger collision
    """
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        provider=None,  # legacy
    )
    _write_log(
        template_log, tmp_path,
        task_token="q3-answer-the-question",
        model="z-ai/glm-5.2",
        provider="kilocode",  # different provider
        uuid_suffix="BBBBBB",
    )
    collision = _check_provider_collision(
        str(tmp_path), "z-ai/glm-5.2", "nvidia"
    )
    # The kilocode log is the collision (legacy is silently allowed)
    assert collision is not None
    assert collision["existing_provider"] == "kilocode"
    assert "q3-answer-the-question" in collision["path"]


# ---------------------------------------------------------------------------
# Defensive: don't crash on bad logs
# ---------------------------------------------------------------------------


def test_corrupt_log_does_not_crash(tmp_path, template_log):
    """A bad .eval file in the log dir doesn't crash the check."""
    (tmp_path / "corrupt.eval").write_bytes(b"not a zip")
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        provider="kilocode",
    )
    # No crash, collision is still detected
    collision = _check_provider_collision(
        str(tmp_path), "z-ai/glm-5.2", "nvidia"
    )
    assert collision is not None
    assert collision["existing_provider"] == "kilocode"


def test_nonexistent_log_dir_returns_none(tmp_path):
    """If log_dir doesn't exist, no collision (nothing to collide with)."""
    nonexistent = tmp_path / "does_not_exist"
    assert (
        _check_provider_collision(str(nonexistent), "z-ai/glm-5.2", "kilocode")
        is None
    )


def test_multiple_collisions_returns_first(tmp_path, template_log):
    """If multiple colliding logs exist, return the first found.

    The CLI hard-stops on the first one; the user resolves it and re-runs,
    at which point the next collision (if any) surfaces.
    """
    for i, task in enumerate(["f1-multi-file-verify", "q3-answer-the-question"]):
        _write_log(
            template_log, tmp_path,
            task_token=task,
            model="z-ai/glm-5.2",
            provider="kilocode",
            uuid_suffix=f"{'A' * 5}{i}",
        )
    collision = _check_provider_collision(
        str(tmp_path), "z-ai/glm-5.2", "nvidia"
    )
    # One of the two logs surfaces first (filesystem-order)
    assert collision is not None
    assert collision["existing_provider"] == "kilocode"
