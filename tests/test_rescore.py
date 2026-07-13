"""Tests for bench_cli.rescore — offline rescore of existing .eval logs."""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bench_cli.rescore import RescoreResult, rescore_logs
from bench_cli.rescore.core import SkipInfo


def _make_eval_log(
    path: Path,
    *,
    n_samples: int = 1,
    correctness: float = 1.0,
    model_usage: dict | None = None,
    corrupt: bool = False,
    missing_samples: bool = False,
) -> Path:
    """Write a minimal Inspect EvalLog ZIP to ``path``.

    The minimum viable ZIP is:
      - header.json
      - samples/...
    Per Inspect, ``status='success'`` + at least one sample = valid for rescore.
    """
    header = {
        "eval": {"task": "t", "model": "m", "status": "success"},
        "created": "2026-07-11T00:00:00Z",
    }
    samples = []
    for i in range(n_samples):
        sample = {
            "id": i,
            "input": "x",
            "target": "y",
            "scores": {
                "verify_sh": {"value": correctness, "answer": ""},
            },
            "model_usage": model_usage if model_usage is not None else {},
        }
        samples.append(sample)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("header.json", json.dumps(header))
        if not missing_samples and not corrupt:
            z.writestr("samples/0.json", json.dumps(sample))

    if corrupt:
        # Overwrite with a truncated file (not a valid ZIP).
        path.write_bytes(b"not a zip")
    return path


def test_rescore_zero_api_calls(tmp_path: Path) -> None:
    """SC11: rescore_logs makes NO outbound requests / API calls.

    We patch the HTTP/SDK call surface and assert zero invocations across
    the whole rescore pass.
    """
    eval_dir = tmp_path / "logs"
    eval_dir.mkdir()
    _make_eval_log(eval_dir / "run.eval")

    with patch("urllib.request.urlopen") as u, \
         patch("httpx.Client") as h, \
         patch("openai.OpenAI") as oa:
        result = rescore_logs(str(eval_dir))

    # rescore_logs itself never returns None — total at least 1.
    assert result.total >= 1
    u.assert_not_called()
    h.assert_not_called()
    oa.assert_not_called()


def test_rescore_handles_corrupt_logs(tmp_path: Path) -> None:
    """SC12: corrupt logs are recorded as skips, do NOT crash the rescore."""
    eval_dir = tmp_path / "logs"
    eval_dir.mkdir()
    _make_eval_log(eval_dir / "good.eval")
    _make_eval_log(eval_dir / "bad.eval", corrupt=True)

    result = rescore_logs(str(eval_dir))

    assert result.total == 2
    assert result.skipped >= 1
    assert any(s.path.endswith("bad.eval") and s.reason == "corrupt_zip"
               for s in result.skips)
    # The good log is updated (or skipped for a benign reason); not flagged
    # as corrupt.
    assert not any(s.path.endswith("good.eval") and s.reason == "corrupt_zip"
                   for s in result.skips)


def test_rescore_dry_run_no_write(tmp_path: Path) -> None:
    """dry_run=True returns the result without rewriting the log file."""
    eval_dir = tmp_path / "logs"
    eval_dir.mkdir()
    log = _make_eval_log(eval_dir / "run.eval")
    original_mtime = log.stat().st_mtime

    result = rescore_logs(str(eval_dir), dry_run=True)

    assert result.total >= 1
    # mtime preserved (no rewrite happened).
    assert log.stat().st_mtime == original_mtime


def test_rescore_idempotent(tmp_path: Path) -> None:
    """Idempotency: first run rewrites the log; second run finds no diff and
    does NOT rewrite.

    Test asserts:
      - r1.updated == 1 (initial pass writes the refresh markers)
      - r2.updated == 0 (no diff on rerun)
      - file mtime does NOT change on the second run (no unnecessary rewrite)
    """
    eval_dir = tmp_path / "logs"
    eval_dir.mkdir()
    # Provide model_usage so the rescore has data to derive from.
    log = _make_eval_log(
        eval_dir / "run.eval",
        model_usage={"m": {"total_tokens": 100, "output_tokens": 10}},
    )

    r1 = rescore_logs(str(eval_dir))
    mtime_after_first = log.stat().st_mtime
    time.sleep(0.05)
    r2 = rescore_logs(str(eval_dir))
    mtime_after_second = log.stat().st_mtime

    assert r1.updated == 1, f"first run should update the log once, got {r1.updated}"
    assert r2.updated == 0, (
        f"second run should be a no-op (idempotency); got {r2.updated} updates"
    )
    assert mtime_after_second == mtime_after_first, (
        "second run rewrote the log — idempotency violated"
    )
