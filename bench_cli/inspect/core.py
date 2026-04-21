"""Inspect eval logs — core logic for stats, compare, and deep-check.

Three modes:
  bench inspect stats        --model <alias>    Per-task pillar averages
  bench inspect compare      --model <alias>    New vs old scores with deltas
  bench inspect deep-check   --model <alias>    Full QA output for every task
"""

from __future__ import annotations

import math
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from inspect_ai.log import read_eval_log, list_eval_logs

from bench_cli.compare.core import (
    _extract_from_scorers,
    _fmt_avg_cost,
    _fmt_cost_ratio,
    _is_suppressed,
    _short_model,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LOG_DIR = _PROJECT_ROOT / "logs"

# ---------------------------------------------------------------------------
# Task directory map
# ---------------------------------------------------------------------------

_PILLAR_MAP: dict[str, str] = {}  # key = task-dir-name (hyphenated)
_PILLAR_MAP_NORMALIZED: dict[str, str] = {}  # key = underscore-ized


def _load_pillar_map() -> dict[str, str]:
    """Scan tasks/ directory to build task → pillar mapping."""
    global _PILLAR_MAP, _PILLAR_MAP_NORMALIZED
    if _PILLAR_MAP:
        return _PILLAR_MAP
    tasks_root = _PROJECT_ROOT / "tasks"
    for pillar_dir in tasks_root.iterdir():
        if not pillar_dir.is_dir():
            continue
        for task_dir in pillar_dir.iterdir():
            if task_dir.is_dir() and (task_dir / "task.py").is_file():
                _PILLAR_MAP[task_dir.name] = pillar_dir.name
                # Also index by underscore-ized name (logs use underscores)
                underscore_name = task_dir.name.replace("-", "_")
                _PILLAR_MAP_NORMALIZED[underscore_name] = pillar_dir.name
    return _PILLAR_MAP


def _get_task_dir(task_name: str) -> Path | None:
    """Find the directory for a task by scanning all pillars.

    Accepts both hyphenated (add-tests) and underscore (add_tests) names.
    Uses the cached pillar map so this is O(1) after the first call.
    """
    pillar_map = _load_pillar_map()
    norm_map = _PILLAR_MAP_NORMALIZED
    pillar = pillar_map.get(task_name) or norm_map.get(task_name)
    if pillar:
        return _PROJECT_ROOT / "tasks" / pillar / task_name
    return None


def _resolve_alias(raw: str) -> str:
    """Normalize a user-provided alias to the full openai/ prefix form."""
    cleaned = raw.strip().removeprefix("models/").removeprefix("openrouter/").removeprefix("openai/")
    return f"openai/{cleaned}"


# ---------------------------------------------------------------------------
# Score extraction
# ---------------------------------------------------------------------------

@dataclass
class SampleScore:
    task: str
    sample_id: str
    scorer_type: str  # verify_sh | llm_judge | hybrid_scorer
    correctness: float | None
    token_ratio: float | None
    time_ratio: float | None
    price_ratio: float | None
    actual_cost_usd: float | None
    reference_cost_usd: float | None
    is_free: bool
    verify_sh_score: float | None
    llm_judge_score: float | None
    input_tokens: int
    output_tokens: int
    working_time: float
    judge_explanation: str | None
    output_text: str | None
    suppressed_token: bool
    suppressed_time: bool


def _load_samples(
    model_alias: str,
    log_dir: Path | None = None,
    latest_only: bool = False,
) -> dict[str, list[SampleScore]]:
    """Load samples for a model from eval logs.

    Args:
        model_alias: Bench model alias to filter by.
        log_dir: Directory containing .eval files.
        latest_only: If True, only return samples from the latest run per task
                     (by eval log filename timestamp).

    Returns {task_name: [SampleScore, ...]}.
    """
    log_dir = log_dir or _LOG_DIR
    task_samples: dict[str, list[SampleScore]] = defaultdict(list)
    seen_tasks: set[str] = set()

    for info in list_eval_logs(log_dir=str(log_dir), descending=True):
        try:
            el = read_eval_log(info)
        except Exception as exc:
            warnings.warn(f"Skipping corrupt/unreadable eval log {info.name}: {exc}")
            continue

        if el.eval.model != model_alias:
            continue
        if el.status != "success" or not el.samples:
            continue

        task = el.eval.task

        # When latest_only, skip a task once we've seen it (logs are newest-first)
        if latest_only:
            if task in seen_tasks:
                continue
            seen_tasks.add(task)

        for s in el.samples:
            if not isinstance(s.scores, dict):
                continue

            correctness, token_ratio, time_ratio, actual_cost_usd = _extract_from_scorers(
                s.scores, getattr(s, "model_usage", None), model_alias
            )

            # Determine scorer type
            scorer_type = "unknown"
            if "hybrid_scorer" in s.scores:
                scorer_type = "hybrid_scorer"
            elif "llm_judge" in s.scores:
                scorer_type = "llm_judge"
            elif "verify_sh" in s.scores:
                scorer_type = "verify_sh"

            # Hybrid sub-scores
            verify_sh_score = None
            llm_judge_score = None
            pr_score = s.scores.get("price_ratio_scorer")
            hybrid_meta: dict = {}
            if scorer_type == "hybrid_scorer" and pr_score and hasattr(pr_score, "metadata"):
                hybrid_meta = pr_score.metadata or {}
                verify_sh_score = hybrid_meta.get("verify_sh_score")
                llm_judge_score = hybrid_meta.get("llm_judge_score")

            # Price ratio from scorer
            price_ratio = None
            reference_cost_usd = None
            is_free = False
            actual_cost = actual_cost_usd
            if pr_score and hasattr(pr_score, "metadata") and pr_score.metadata:
                price_ratio = pr_score.value if isinstance(pr_score.value, float) else None
                reference_cost_usd = pr_score.metadata.get("reference_cost_usd")
                is_free = pr_score.metadata.get("is_free", False)
                if actual_cost is None:
                    actual_cost = pr_score.metadata.get("actual_cost_usd")

            # Judge explanation
            judge_explanation = None
            judge_sc = s.scores.get("llm_judge") or s.scores.get("hybrid_scorer")
            if judge_sc and hasattr(judge_sc, "explanation"):
                judge_explanation = judge_sc.explanation

            # Output text
            output_text = None
            if hasattr(s, "output") and s.output:
                output_text = str(s.output.completion)[:2000] if hasattr(s.output, "completion") else str(s.output)[:2000]

            # Token/time
            input_tokens = 0
            output_tokens = 0
            if hasattr(s, "model_usage") and s.model_usage:
                for u in s.model_usage.values():
                    input_tokens += getattr(u, "input_tokens", 0) or 0
                    output_tokens += getattr(u, "output_tokens", 0) or 0
            working_time = getattr(s, "working_time", 0.0) or 0.0

            # Suppression flags
            suppressed_token = _is_suppressed(s.scores.get("token_ratio_scorer"))
            suppressed_time = _is_suppressed(s.scores.get("time_ratio_scorer"))

            task_samples[el.eval.task].append(SampleScore(
                task=el.eval.task,
                sample_id=s.id if hasattr(s, "id") else "?",
                scorer_type=scorer_type,
                correctness=correctness,
                token_ratio=token_ratio,
                time_ratio=time_ratio,
                price_ratio=price_ratio,
                actual_cost_usd=actual_cost,
                reference_cost_usd=reference_cost_usd,
                is_free=is_free,
                verify_sh_score=verify_sh_score,
                llm_judge_score=llm_judge_score,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                working_time=working_time,
                judge_explanation=judge_explanation,
                output_text=output_text,
                suppressed_token=suppressed_token,
                suppressed_time=suppressed_time,
            ))

    return dict(task_samples)


def _per_task_stats(samples: list[SampleScore]) -> dict:
    """Compute aggregate stats from a list of SampleScore objects."""
    n = len(samples)
    if n == 0:
        return {}

    correct_vals = [s.correctness for s in samples if s.correctness is not None]
    tok_vals = [s.token_ratio for s in samples if s.token_ratio is not None and not s.suppressed_token]
    time_vals = [s.time_ratio for s in samples if s.time_ratio is not None and not s.suppressed_time]
    price_vals = [s.price_ratio for s in samples if s.price_ratio is not None and not math.isnan(s.price_ratio)]
    cost_vals = [s.actual_cost_usd for s in samples if s.actual_cost_usd is not None]
    tok_count_vals = [s.input_tokens + s.output_tokens for s in samples]
    time_abs_vals = [s.working_time for s in samples]

    return {
        "n": n,
        "correctness_avg": sum(correct_vals) / len(correct_vals) if correct_vals else None,
        "correctness_min": min(correct_vals) if correct_vals else None,
        "correctness_max": max(correct_vals) if correct_vals else None,
        "token_ratio_avg": sum(tok_vals) / len(tok_vals) if tok_vals else None,
        "time_ratio_avg": sum(time_vals) / len(time_vals) if time_vals else None,
        "price_ratio_avg": sum(price_vals) / len(price_vals) if price_vals else None,
        "avg_cost_usd": sum(cost_vals) / len(cost_vals) if cost_vals else None,
        "avg_tokens": sum(tok_count_vals) / n,
        "avg_time": sum(time_abs_vals) / n,
        "n_tok_suppressed": sum(1 for s in samples if s.suppressed_token),
        "n_time_suppressed": sum(1 for s in samples if s.suppressed_time),
        "n_nan_tok": sum(1 for s in samples if s.token_ratio is not None and math.isnan(s.token_ratio)),
        "n_nan_time": sum(1 for s in samples if s.time_ratio is not None and math.isnan(s.time_ratio)),
        "scorer_type": samples[0].scorer_type,
        "n_verify_sh_samples": sum(1 for s in samples if s.scorer_type == "verify_sh" and s.correctness in (0.0, 1.0)),
        "n_llm_judge_samples": sum(1 for s in samples if s.scorer_type == "llm_judge"),
        "all_verify_sh_binary": all(s.correctness in (0.0, 1.0) for s in samples if s.scorer_type == "verify_sh" and s.correctness is not None),
        "all_correctness_one": all(s.correctness == 1.0 for s in samples if s.correctness is not None),
        "all_correctness_zero": all(s.correctness == 0.0 for s in samples if s.correctness is not None),
        "hybrid_verify_sh_avg": sum(s.verify_sh_score for s in samples if s.verify_sh_score is not None) / max(1, sum(1 for s in samples if s.verify_sh_score is not None)),
        "hybrid_llm_judge_avg": sum(s.llm_judge_score for s in samples if s.llm_judge_score is not None) / max(1, sum(1 for s in samples if s.llm_judge_score is not None)),
    }


def _load_baseline(model_alias: str, log_dir: Path | None = None) -> dict[str, float]:
    """Load baseline per-task correctness from all runs except the latest per task.

    For each task, collects samples from ALL runs except the most recent one
    (by eval log filename timestamp). Returns averaged correctness per task.
    Returns empty dict if there is only one run per task.
    """
    log_dir = log_dir or _LOG_DIR

    # First pass: identify the latest (newest) file per task.
    latest_file_per_task: dict[str, str] = {}
    for info in list_eval_logs(log_dir=str(log_dir), descending=True):
        try:
            el = read_eval_log(info)
        except Exception as exc:
            warnings.warn(f"Skipping corrupt/unreadable eval log {info.name}: {exc}")
            continue
        if el.eval.model != model_alias:
            continue
        if el.status != "success" or not el.samples:
            continue
        task = el.eval.task
        if task not in latest_file_per_task:
            latest_file_per_task[task] = str(info.name)

    if not latest_file_per_task:
        return {}

    # Store as strings for reliable equality comparison in the second pass.
    latest_files = set(str(v) for v in latest_file_per_task.values())

    # Second pass: collect samples from all OTHER (older) runs.
    task_correctness: dict[str, list[float]] = defaultdict(list)
    for info in list_eval_logs(log_dir=str(log_dir), descending=True):
        if str(info.name) in latest_files:
            continue  # skip the newest run per task
        try:
            el = read_eval_log(info)
        except Exception as exc:
            warnings.warn(f"Skipping corrupt/unreadable eval log {info.name}: {exc}")
            continue
        if el.eval.model != model_alias:
            continue
        if el.status != "success" or not el.samples:
            continue
        task = el.eval.task
        for s in el.samples:
            if not isinstance(s.scores, dict):
                continue
            c, _, _, _ = _extract_from_scorers(s.scores, getattr(s, "model_usage", None), model_alias)
            if c is not None:
                task_correctness[task].append(c)

    return {
        task: sum(vals) / len(vals)
        for task, vals in task_correctness.items()
        if vals
    }
