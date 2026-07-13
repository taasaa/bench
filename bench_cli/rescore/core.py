"""Offline rescore of existing .eval logs.

Rescore makes zero API calls — it walks every ``.eval`` ZIP in ``log_dir``,
extracts per-sample ``model_usage`` already on disk, and re-derives the
efficiency scores using the current pricing resolution pipeline. Correctness
is never modified. Logs with status != 'success' or with a corrupt ZIP are
recorded in the skips list and skipped without raising.

Public surface:
    - ``RescoreResult``: summary of the rescore pass
    - ``SkipInfo``: per-skip detail (path, reason)
    - ``rescore_logs(log_dir, *, dry_run=False)``: the main entry point
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkipInfo:
    """Why a single log was skipped during rescore."""

    path: str
    reason: str  # "corrupt_zip", "missing_samples", "status_not_success", etc.


@dataclass
class RescoreResult:
    """Summary of a rescore pass."""

    total: int
    updated: int
    skipped: int
    skips: list[SkipInfo]


def _read_eval_log(path: Path) -> tuple[dict | None, list[dict] | None, str | None]:
    """Return (header, samples, status) or (None, None, reason)."""
    try:
        with zipfile.ZipFile(path, "r") as z:
            if "header.json" not in z.namelist():
                return None, None, "missing_header"
            with z.open("header.json") as f:
                header = json.loads(f.read().decode("utf-8"))
            sample_files = [n for n in z.namelist() if n.startswith("samples/")]
            if not sample_files:
                return header, [], "missing_samples"
            samples = []
            for n in sorted(sample_files):
                with z.open(n) as f:
                    samples.append(json.loads(f.read().decode("utf-8")))
            return header, samples, None
    except (zipfile.BadZipFile, json.JSONDecodeError):
        return None, None, "corrupt_zip"
    except OSError:
        return None, None, "read_error"


def _derive_efficiency(
    sample: dict,
    *,
    total_tokens: int | None,
    answer_tokens: int | None,
    working_time: float | None,
) -> dict:
    """Reconstruct the efficiency-derived fields we want to write back.

    Note: ``avg_cost_usd`` recomputation is intentionally OUT OF SCOPE for
    Phase 0 rescore — see the deferred-cost note on Task 6 above. The fields
    written here are tokens, answer-tokens, and time only.

    Returns a dict with keys: ``avg_tokens``, ``avg_answer_tokens``,
    ``avg_time``. Any field whose source is None becomes None in the result.
    """
    return {
        "avg_tokens": float(total_tokens) if total_tokens is not None else None,
        "avg_answer_tokens": (
            float(answer_tokens) if answer_tokens is not None else None
        ),
        "avg_time": working_time,
    }


def _rescore_sample(sample: dict) -> dict:
    """Return updated efficiency fields for one sample, or {} if nothing to update."""
    model_usage = sample.get("model_usage") or {}
    if not isinstance(model_usage, dict):
        return {}
    # Aggregate usage across all model entries.
    total_tokens = 0
    answer_tokens_total = 0
    has_answer_split = False
    for entry in model_usage.values():
        if not isinstance(entry, dict):
            continue
        total_tokens += int(entry.get("total_tokens", 0) or 0)
        # inspect_ai may carry per-type counts as ``output_tokens`` or
        # ``output_tokens_details`` etc.; treat any explicit
        # ``answer_tokens`` / ``output_tokens`` as the answer count when
        # present, falling back to None.
        out = entry.get("output_tokens")
        if out is not None:
            answer_tokens_total += int(out or 0)
            has_answer_split = True
    return {
        "total_tokens": total_tokens,
        "answer_tokens": answer_tokens_total if has_answer_split else None,
    }


def _write_eval_log(path: Path, header: dict, samples: list[dict]) -> None:
    """Rewrite the .eval ZIP with the updated samples."""
    # Write to a temp file then atomically replace to avoid truncated logs
    # on failure.
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("header.json", json.dumps(header))
        for i, sample in enumerate(samples):
            z.writestr(f"samples/{i}.json", json.dumps(sample))
    tmp.replace(path)


def rescore_logs(log_dir: str, *, dry_run: bool = False) -> RescoreResult:
    """Rescore every ``.eval`` log in ``log_dir``.

    Steps per log:
        1. Read the binary ZIP, extract header + samples.
        2. If status != 'success' or ZIP is corrupt, record a SkipInfo and
           continue.
        3. For each sample, recompute efficiency-derived values from
           ``sample.model_usage``. Correctness is NEVER touched.
        4. If the recomputed values differ from what's already in the log,
           write the log back.

    Rescore makes zero API calls. No outbound network is required.

    Args:
        log_dir: directory containing ``.eval`` files (recursive).
        dry_run: when True, no files are written; the result still reports
                 what would be updated.

    Returns:
        RescoreResult with counts and a per-skip list.
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return RescoreResult(total=0, updated=0, skipped=0, skips=[])

    eval_files = sorted(log_path.rglob("*.eval"))
    result = RescoreResult(total=0, updated=0, skipped=0, skips=[])

    for log in eval_files:
        result.total += 1
        header, samples, err = _read_eval_log(log)
        if err is not None:
            result.skipped += 1
            result.skips.append(SkipInfo(path=str(log), reason=err))
            continue
        status = (header.get("eval") or {}).get("status") if isinstance(header, dict) else None
        if status != "success":
            result.skipped += 1
            result.skips.append(SkipInfo(path=str(log), reason="status_not_success"))
            continue
        if not samples:
            result.skipped += 1
            result.skips.append(SkipInfo(path=str(log), reason="missing_samples"))
            continue

        # Re-derive efficiency for each sample. Track whether anything
        # changed in order to compute updated count.
        changed = False
        for sample in samples:
            new_vals = _rescore_sample(sample)
            if not new_vals:
                continue
            updated = _derive_efficiency(
                sample,
                total_tokens=new_vals["total_tokens"],
                answer_tokens=new_vals["answer_tokens"],
                working_time=sample.get("working_time"),
            )
            # Mark change only when we actually write something different —
            # the first rescore after a log loads should write the missing
            # ``avg_tokens`` / ``avg_answer_tokens`` to the scores dict.
            scores = sample.setdefault("scores", {})
            if updated.get("avg_tokens") is not None and \
                    scores.get("_rescore_avg_tokens") != updated["avg_tokens"]:
                scores["_rescore_avg_tokens"] = updated["avg_tokens"]
                scores["_rescore_avg_answer_tokens"] = updated.get("avg_answer_tokens")
                changed = True

        if changed and not dry_run:
            try:
                _write_eval_log(log, header, samples)
                result.updated += 1
            except OSError:
                result.skipped += 1
                result.skips.append(SkipInfo(path=str(log), reason="write_error"))

    return result
