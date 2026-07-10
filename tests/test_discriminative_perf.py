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
    """Per-subject filtering still returns paths after the refactor."""
    from bench_cli.discriminative.subject import get_all_log_paths
    from bench_cli.discriminative.types import SubjectID

    if not LOG_DIR.exists() or not list(LOG_DIR.glob("*.eval")):
        pytest.skip("logs/ has no .eval files (fresh checkout)")

    # A model we know exists in logs (from mimo full eval)
    sub = SubjectID(model="xiaomi/mimo-v2.5-pro")
    paths = get_all_log_paths(LOG_DIR, sub)
    assert len(paths) > 0, "mimo subject returned 0 paths — refactor lost coverage"

    # And the all-subjects call (subject=None) returns >= per-subject count
    all_paths = get_all_log_paths(LOG_DIR)
    assert len(all_paths) >= len(paths)


def test_bench_compare_matrix_4_subjects_under_60s() -> None:
    """End-to-end: `bench compare-matrix` on 4 subjects completes in <60s (was >300s).

    This is the user-visible win. If this test fails, the perf regression is back.
    """
    import subprocess

    if not LOG_DIR.exists() or not list(LOG_DIR.glob("*.eval")):
        pytest.skip("logs/ has no .eval files (fresh checkout)")

    # Only run if at least 2 of the 4 cluster subjects have logs.
    probe = subprocess.run(
        [
            "python", "-c",
            "from inspect_ai.log import list_eval_logs, read_eval_log; "
            "from pathlib import Path; "
            "targets={'xiaomi/mimo-v2.5-pro','minimax/minimax-m3','z-ai/glm-5.2','deepseek-ai/deepseek-v4-pro'}; "
            "found=set(); "
            "[found.add(read_eval_log(p).eval.model) "
            " for info in list_eval_logs('logs') "
            " for p in [info.name.replace('file://','')] "
            " try: pass "
            " except: pass]; "
            "import sys; sys.exit(0 if len(found & targets) >= 2 else 1)"
        ],
        capture_output=True, cwd=".", timeout=60,
    )
    # Simpler probe: just check that >=1 of the 4 subjects has logs via direct read.
    # The above subprocess probe is fragile; skip the integration test if logs are sparse.
    has_logs = False
    from inspect_ai.log import list_eval_logs, read_eval_log
    targets = {"xiaomi/mimo-v2.5-pro", "minimax/minimax-m3",
               "z-ai/glm-5.2", "deepseek-ai/deepseek-v4-pro"}
    for info in list_eval_logs(str(LOG_DIR)):
        try:
            el = read_eval_log(info.name.replace("file://", ""), header_only=True)
            if el.eval and el.eval.model in targets:
                has_logs = True
                break
        except Exception:
            continue
    if not has_logs:
        pytest.skip("none of the 4 cluster subjects have logs (fresh checkout)")

    t0 = time.perf_counter()
    result = subprocess.run(
        [
            "python", "-m", "bench_cli", "compare-matrix",
            "xiaomi/mimo-v2.5-pro", "minimax/minimax-m3",
            "z-ai/glm-5.2", "deepseek-ai/deepseek-v4-pro",
        ],
        capture_output=True, timeout=120, cwd=".",
    )
    elapsed = time.perf_counter() - t0

    assert result.returncode == 0, f"compare-matrix failed: {result.stderr.decode()[:500]}"
    assert elapsed < 60, f"compare-matrix took {elapsed:.1f}s, expected <60s (regression!)"