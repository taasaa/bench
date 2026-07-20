"""Regression tests for the discriminative layer's log-scan performance.

Background (2026-07-09): `bench recommend`, `bench compare-matrix`, and
`bench task-correlations` were doing N x 1440 full ZIP reads per CLI invocation
(both `get_all_log_paths` AND `resolve_subject_from_log` did full `read_eval_log`
just to read `eval.model`). For 4 subjects this was >300s on compare-matrix
and >900s on task-correlations.

Fix: `_scan_log_dir` uses `header_only=True` (9.5x faster) and is wrapped in
`lru_cache(maxsize=8)` so N subjects in one process share a single scan. Plus
`resolve_subject_from_log` now uses `header_only` with a one-shot full-read
fallback only for legacy logs missing `eval.model`.

These tests assert:
  1. `_scan_log_dir` completes in well under 30s on the real logs/ (was 45s).
  2. A second call is a cache hit (< 1s; was 45s).
  3. Per-subject filtering returns the same paths as before the refactor.
  4. `bench compare-matrix` end-to-end on 4 subjects completes in <60s (was >300s).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from click.testing import CliRunner
from bench_cli.main import cli

LOG_DIR = Path("logs")


@pytest.fixture(autouse=True)
def _clear_scan_cache():
    """Clear the lru_cache before/after each test to make timings reproducible."""
    from bench_cli.discriminative.subject import _scan_log_dir
    _scan_log_dir.cache_clear()
    yield
    _scan_log_dir.cache_clear()


def test_scan_log_dir_cold_call_under_30s() -> None:
    """A fresh scan of the real logs/ completes in <30s (was ~45s full-read)."""
    from bench_cli.discriminative.subject import _scan_log_dir

    if not LOG_DIR.exists() or not list(LOG_DIR.glob("*.eval")):
        pytest.skip("logs/ has no .eval files (fresh checkout)")

    t0 = time.perf_counter()
    mapping = _scan_log_dir(str(LOG_DIR))
    elapsed = time.perf_counter() - t0

    assert elapsed < 30, f"cold scan took {elapsed:.1f}s, expected <30s"
    assert len(mapping) > 0, "scan returned empty mapping"


def test_scan_log_dir_warm_call_under_1s() -> None:
    """A cached scan call returns in <1s (was 45s full-read, N times)."""
    from bench_cli.discriminative.subject import _scan_log_dir

    if not LOG_DIR.exists() or not list(LOG_DIR.glob("*.eval")):
        pytest.skip("logs/ has no .eval files (fresh checkout)")

    # prime the cache
    _scan_log_dir(str(LOG_DIR))
    # second call should hit cache
    t0 = time.perf_counter()
    mapping = _scan_log_dir(str(LOG_DIR))
    elapsed = time.perf_counter() - t0

    assert elapsed < 1.0, f"warm scan took {elapsed:.3f}s, expected <1s (lru_cache hit)"
    assert len(mapping) > 0


def test_get_all_log_paths_per_subject_filter_stable() -> None:
    """Per-subject filtering returns a subset of the all-subjects result.

    Picks the most-logged subject dynamically rather than pinning to a
    specific model, so the test is robust to log rotation.
    """
    from bench_cli.discriminative.subject import get_all_log_paths
    from bench_cli.discriminative.types import SubjectID

    if not LOG_DIR.exists() or not list(LOG_DIR.glob("*.eval")):
        pytest.skip("logs/ has no .eval files (fresh checkout)")

    all_paths = get_all_log_paths(LOG_DIR)
    assert len(all_paths) > 0, "scan returned 0 paths"

    # Pick the subject with the most logs; per-subject filtering for it
    # must return <= all_paths and > 0.
    from bench_cli.discriminative.subject import _scan_log_dir
    counts: dict[str, int] = {}
    for task, m, p in _scan_log_dir(str(LOG_DIR)):
        counts[m] = counts.get(m, 0) + 1
    top_model = max(counts, key=counts.get)
    sub = SubjectID(model=top_model)
    paths = get_all_log_paths(LOG_DIR, sub)
    assert len(paths) > 0, f"top-logged subject {top_model!r} returned 0 paths"
    assert len(paths) <= len(all_paths)


def test_bench_compare_matrix_perf() -> None:
    """End-to-end: `bench compare-matrix` on 4 real subjects completes quickly.

    Picks the 4 most-logged subjects dynamically; perf regression (vs the
    2026-07-09 header_only+lru_cache fix) is what this test guards.
    """
    import subprocess
    from inspect_ai.log import list_eval_logs, read_eval_log

    if not LOG_DIR.exists() or not list(LOG_DIR.glob("*.eval")):
        pytest.skip("logs/ has no .eval files (fresh checkout)")

    from bench_cli.discriminative.subject import _scan_log_dir
    counts: dict[str, int] = {}
    for task, m, p in _scan_log_dir(str(LOG_DIR)):
        counts[m] = counts.get(m, 0) + 1

    if len(counts) < 4:
        pytest.skip(f"need >=4 distinct subjects in logs/, found {len(counts)}")

    top4 = sorted(counts, key=counts.get, reverse=True)[:4]
    t0 = time.perf_counter()
    runner = CliRunner()
    result = runner.invoke(cli, ["compare-matrix", *top4])
    elapsed = time.perf_counter() - t0

    assert result.exit_code == 0, f"compare-matrix failed: {result.output[:500]}"
    assert elapsed < 10.0, f"compare-matrix took {elapsed:.1f}s, expected <10s (regression!)"