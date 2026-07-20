"""Invariant test for compare's per-(task, model) run dedup.

load_compare_data keeps the LATEST (most recent) run for each (task, model)
pair — logs are loaded newest-first (list_eval_logs(descending=True)) and the
first run encountered per pair wins. Earlier runs are discarded, NEVER averaged
and NEVER best-of-N selected.

This matters because several early models (nemotron-nano-30b, devstral-2512)
have 4-9 historical runs per task from harness-development re-runs. If the dedup
ever became best-of-N (as the old docstring incorrectly claimed) or averaging,
those models would be silently inflated relative to models with a single run.

The test builds two logs for the same (task, model): the OLDER run has a HIGH
correctness (1.0), the NEWER run has a LOW correctness (0.0). The kept value
must be 0.0 — which uniquely identifies "latest" (best-of-N would give 1.0,
averaging would give 0.5).

Fixtures clone a real eval log (roundtrip through zipfile) so we never fight the
inspect_ai EvalLog pydantic validator with hand-built JSON.
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

from bench_cli.compare.core import load_compare_data


_TPL_DIR = Path(__file__).resolve().parent.parent / "logs"

# Correctness scorer keys in priority order (matches _extract_from_scorers).
_CORRECTNESS_KEYS = ("hybrid_scorer", "llm_judge", "verify_sh", "exact", "includes")


def _find_template_log() -> Path:
    """Find a real success log to use as a template for fixture generation."""
    candidates = sorted(
        _TPL_DIR.glob("*.eval"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in candidates:
        if p.stat().st_size > 1000:  # skip truncated/corrupt ones
            try:
                with zipfile.ZipFile(p) as zf:
                    if "header.json" in zf.namelist():
                        return p
            except Exception:
                continue
    raise RuntimeError("No real eval log available to use as template")


def _clone_with_correctness(
    src: Path,
    dst: Path,
    *,
    model: str,
    task: str,
    correctness: float,
) -> Path:
    """Clone src eval log to dst, overriding model/task and per-sample correctness.

    Sets every present correctness scorer's value in each sample to `correctness`
    so _extract_from_scorers reads it back regardless of scorer priority.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as zin:
        with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name == "header.json":
                    hdr = json.loads(data)
                    hdr["status"] = "success"
                    hdr["eval"]["model"] = model
                    hdr["eval"]["task"] = task
                    hdr["eval"]["task_display_name"] = task
                    data = json.dumps(hdr).encode()
                elif name.startswith("samples/") and name.endswith(".json"):
                    sample = json.loads(data)
                    scores = sample.get("scores")
                    if isinstance(scores, dict):
                        for key in _CORRECTNESS_KEYS:
                            sc = scores.get(key)
                            if isinstance(sc, dict):
                                sc["value"] = correctness
                    data = json.dumps(sample).encode()
                zout.writestr(name, data)
    return dst


@pytest.fixture
def template_log() -> Path:
    return _find_template_log()


def test_keeps_latest_run_not_highest_mean(tmp_path, template_log):
    """The newest run wins even when an older run scored higher.

    older (2026-01-01) correctness=1.0  vs  newer (2026-12-31) correctness=0.0
    Result must be 0.0 (latest). 1.0 would mean best-of-N; 0.5 would mean averaging.
    """
    task = "f1-multi-file-verify"
    model = "z-ai/glm-5.2"

    older = _clone_with_correctness(
        template_log,
        tmp_path / f"2026-01-01T00-00-00-00-00_{task}_OLDER1.eval",
        model=model, task=task, correctness=1.0,
    )
    newer = _clone_with_correctness(
        template_log,
        tmp_path / f"2026-12-31T00-00-00-00-00_{task}_NEWER1.eval",
        model=model, task=task, correctness=0.0,
    )
    # Make mtime agree with filename ordering (belt-and-suspenders for the sort key).
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))

    data = load_compare_data(str(tmp_path))
    ps = data.matrix[task][model]
    assert ps.correctness == 0.0, (
        f"dedup kept correctness={ps.correctness}; expected 0.0 (latest run). "
        "1.0 => best-of-N regression, 0.5 => averaging regression."
    )


def test_latest_wins_regardless_of_insertion_count(tmp_path, template_log):
    """With three runs, the single newest run is kept (not averaged across all)."""
    task = "q3-answer-the-question"
    model = "z-ai/glm-5.2"

    # Three runs: two older high-score, one newest low-score.
    for ts, suffix, corr in [
        ("2026-01-01T00-00-00-00-00", "RUN_A", 1.0),
        ("2026-02-01T00-00-00-00-00", "RUN_B", 1.0),
        ("2026-12-31T00-00-00-00-00", "RUN_C", 0.25),
    ]:
        p = _clone_with_correctness(
            template_log,
            tmp_path / f"{ts}_{task}_{suffix}.eval",
            model=model, task=task, correctness=corr,
        )
        # ascending mtime matching filename order
        mt = {"RUN_A": 1_000_000, "RUN_B": 1_500_000, "RUN_C": 2_000_000}[suffix]
        os.utime(p, (mt, mt))

    data = load_compare_data(str(tmp_path))
    ps = data.matrix[task][model]
    # Latest (RUN_C, 0.25) wins; averaging would give ~0.75, best-of-N would give 1.0.
    assert ps.correctness == 0.25, (
        f"dedup kept correctness={ps.correctness}; expected 0.25 (latest of 3 runs)."
    )
