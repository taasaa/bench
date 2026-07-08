"""Tests for provider-aware cross-run resume (bench_cli/run/core.py::_completed_tasks).

Critical invariant: a log with a different `bench_provider` than the new run
is treated as a DISTINCT run and NOT marked done — different providers
must not replace one another under the same recorded identity.

Legacy logs (pre-feature, no `bench_provider` in header metadata) are
matched by recorded identity alone and emit a one-time warning.

Test fixtures are built by roundtripping a real eval log (copy + modify
eval.model, eval.metadata, top-level metadata, and filename) so we never
fight the inspect_ai EvalLog pydantic validator with hand-built JSON.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from bench_cli.run.core import _completed_tasks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_TPL_DIR = Path(__file__).resolve().parent.parent / "logs"


def _find_template_log() -> Path:
    """Find a real success log to use as a template for fixture generation."""
    candidates = sorted(
        _TPL_DIR.glob("*.eval"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in candidates:
        if p.stat().st_size > 1000:  # skip truncated/corrupt ones
            return p
    raise RuntimeError("No real eval log available to use as template")


def _clone_eval_log(
    src: Path,
    dst: Path,
    *,
    model: str,
    task_token: str,
    status: str = "success",
    provider: str | None = None,
) -> Path:
    """Copy src eval log to dst, overriding model/metadata/filename."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as zin:
        with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name == "header.json":
                    hdr = json.loads(data)
                    hdr["status"] = status
                    hdr["eval"]["model"] = model
                    hdr["eval"]["task"] = task_token
                    hdr["eval"]["task_display_name"] = task_token
                    meta = {"bench_provider": provider} if provider is not None else {}
                    hdr["eval"]["metadata"] = meta
                    hdr["metadata"] = meta
                    data = json.dumps(hdr).encode()
                zout.writestr(name, data)
    return dst


@pytest.fixture
def template_log() -> Path:
    """A real eval log we can clone + mutate for each test."""
    return _find_template_log()


def _write_log(
    template: Path,
    log_dir: Path,
    *,
    task_token: str,
    model: str,
    provider: str | None = None,
    status: str = "success",
    uuid_suffix: str = "AAAAAA",
) -> Path:
    """Write one fixture log into log_dir."""
    # Filename pattern: {ts}_{task}_{uuid}.eval — _FNAME_RE captures task as group 2
    name = f"2026-07-07T00-00-00-00-00_{task_token}_{uuid_suffix}.eval"
    return _clone_eval_log(
        template,
        log_dir / name,
        model=model,
        task_token=task_token,
        status=status,
        provider=provider,
    )


# ---------------------------------------------------------------------------
# Core: provider-aware dedup
# ---------------------------------------------------------------------------


def test_same_provider_dedups(tmp_path, template_log, capsys):
    """Log with same provider → marked done (skipped on resume)."""
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        provider="kilocode",
    )
    done = _completed_tasks(
        str(tmp_path),
        bench_alias="z-ai/glm-5.2",
        spec_dirs={"f1-multi-file-verify"},
        provider="kilocode",
    )
    assert "f1-multi-file-verify" in done


def test_different_provider_does_not_dedup(tmp_path, template_log, capsys):
    """Log with DIFFERENT provider → NOT marked done.

    This is THE critical invariant: kilocode and nvidia runs of the
    same model must not replace one another in dedup.
    """
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="nvidia/nemotron-3-super-120b",
        provider="kilocode",  # existing log was kilocode
    )
    done = _completed_tasks(
        str(tmp_path),
        bench_alias="nvidia/nemotron-3-super-120b",
        spec_dirs={"f1-multi-file-verify"},
        provider="nvidia",  # new run is nvidia
    )
    # Cross-provider: existing log is NOT marked done, new run proceeds
    assert done == set()


def test_legacy_log_without_provider_dedups_with_warning(tmp_path, template_log, capsys):
    """Legacy log (no bench_provider) → matched by recorded identity, warns once."""
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        provider=None,  # legacy
    )
    done = _completed_tasks(
        str(tmp_path),
        bench_alias="z-ai/glm-5.2",
        spec_dirs={"f1-multi-file-verify"},
        provider="kilocode",
    )
    # Legacy log is treated as same-provider
    assert "f1-multi-file-verify" in done
    # One-time warning was emitted
    err = capsys.readouterr().err
    assert "without bench_provider metadata" in err
    assert "kilocode" in err


def test_legacy_warning_emitted_only_once(tmp_path, template_log, capsys):
    """The legacy warning is per-run, not per-log."""
    for i in range(3):
        _write_log(
            template_log, tmp_path,
            task_token="f1-multi-file-verify",
            model="z-ai/glm-5.2",
            provider=None,
            uuid_suffix=f"{'A' * 5}{i}",
        )
    _completed_tasks(
        str(tmp_path),
        bench_alias="z-ai/glm-5.2",
        spec_dirs={"f1-multi-file-verify"},
        provider="kilocode",
    )
    err = capsys.readouterr().err
    # Exactly one warning, not three
    assert err.count("without bench_provider metadata") == 1


def test_legacy_logs_mixed_with_provider_logs(tmp_path, template_log, capsys):
    """When both legacy and provider-tagged logs exist:
    - legacy matches (warns once)
    - provider-tagged with different provider does NOT match
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
        provider="nvidia",  # different provider
        uuid_suffix="BBBBBB",
    )
    done = _completed_tasks(
        str(tmp_path),
        bench_alias="z-ai/glm-5.2",
        spec_dirs={"f1-multi-file-verify", "q3-answer-the-question"},
        provider="kilocode",
    )
    # Legacy f1 was matched (assume same provider)
    assert "f1-multi-file-verify" in done
    # Cross-provider q3 was NOT matched
    assert "q3-answer-the-question" not in done


# ---------------------------------------------------------------------------
# Errored / partial logs: still re-run regardless of provider
# ---------------------------------------------------------------------------


def test_errored_log_always_reruns(tmp_path, template_log):
    """status=error logs are never marked done, regardless of provider."""
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        status="error",
        provider="kilocode",
    )
    done = _completed_tasks(
        str(tmp_path),
        bench_alias="z-ai/glm-5.2",
        spec_dirs={"f1-multi-file-verify"},
        provider="kilocode",
    )
    assert done == set()


def test_partial_log_always_reruns(tmp_path, template_log):
    """status=started/partial logs always re-run (recover past failure point)."""
    statuses = ["started", "partial", "cancelled"]
    for i, status in enumerate(statuses):
        _write_log(
            template_log, tmp_path,
            task_token="f1-multi-file-verify",
            model="z-ai/glm-5.2",
            status=status,
            provider="kilocode",
            uuid_suffix=f"{'C' * 5}{i}",
        )
    done = _completed_tasks(
        str(tmp_path),
        bench_alias="z-ai/glm-5.2",
        spec_dirs={"f1-multi-file-verify"},
        provider="kilocode",
    )
    assert done == set()


# ---------------------------------------------------------------------------
# Defensive: bad log files don't crash
# ---------------------------------------------------------------------------


def test_corrupt_log_is_skipped(tmp_path, template_log):
    """A corrupt .eval file (no header.json, partial zip) doesn't crash dedup."""
    (tmp_path / "corrupt.eval").write_bytes(b"not a zip")
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        provider="kilocode",
    )
    # No crash, good log is still detected
    done = _completed_tasks(
        str(tmp_path),
        bench_alias="z-ai/glm-5.2",
        spec_dirs={"f1-multi-file-verify"},
        provider="kilocode",
    )
    assert "f1-multi-file-verify" in done


def test_different_model_does_not_dedup(tmp_path, template_log):
    """Logs for a different model don't count toward this run's done set."""
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        provider="kilocode",
    )
    done = _completed_tasks(
        str(tmp_path),
        bench_alias="nvidia/nemotron-3-super-120b",  # different model
        spec_dirs={"f1-multi-file-verify"},
        provider="kilocode",
    )
    assert done == set()


def test_no_provider_arg_uses_legacy_behavior(tmp_path, template_log, capsys):
    """If provider=None is passed, dedup falls back to recorded-name only.

    This preserves backwards compat for any internal callers (tests,
    scripts) that haven't been updated to pass provider.
    """
    _write_log(
        template_log, tmp_path,
        task_token="f1-multi-file-verify",
        model="z-ai/glm-5.2",
        provider="kilocode",  # exists
    )
    # Calling without provider arg
    done = _completed_tasks(
        str(tmp_path),
        bench_alias="z-ai/glm-5.2",
        spec_dirs={"f1-multi-file-verify"},
        # provider=None (default)
    )
    # Falls back to recorded-name only matching — no warning emitted
    # because no provider is being asserted
    assert "f1-multi-file-verify" in done
    err = capsys.readouterr().err
    assert err == ""  # no warning when no provider assertion is made
