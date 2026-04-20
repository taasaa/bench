"""Inspect eval logs — stats, compare, and deep-check for a model.

Three modes:
  bench inspect stats      --model <alias>    Per-task pillar averages
  bench inspect compare  --model <alias>    New vs old scores with deltas
  bench inspect deep-check --model <alias>  Full QA output for every task
"""

from __future__ import annotations

import math
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass
from inspect_ai.log import read_eval_log, list_eval_logs
from pathlib import Path

import click

from bench_cli.compare import (
    CompareData,
    load_compare_data,
    _extract_from_scorers,
    _is_suppressed,
    _fmt,
    _fmt_ratio,
    _fmt_time,
    _fmt_tokens,
    _fmt_cost_ratio,
    _fmt_avg_cost,
    _short_model,
)
from bench_cli.pricing.model_aliases import MODEL_ALIAS_MAP

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
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
    # pillar_map keys are hyphenated; norm_map keys are underscore-ized
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


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------

def _load_baseline(model_alias: str, log_dir: Path | None = None) -> dict[str, float]:
    """Load baseline per-task correctness from all runs except the latest per task.

    For each task, collects samples from ALL runs except the most recent one
    (by eval log filename timestamp). Returns averaged correctness per task.
    Returns empty dict if there is only one run per task.
    """
    log_dir = log_dir or _LOG_DIR

    # First pass: identify the latest (newest) file per task.
    # list_eval_logs returns newest-first (descending=True).
    # info.name is a full file URI (file:///...). Use str() for reliable comparison.
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


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group("inspect")
def inspect() -> None:
    """Inspect eval logs — stats, compare, and deep-check for a model."""
    pass


# ---------------------------------------------------------------------------
# inspect stats
# ---------------------------------------------------------------------------

@inspect.command("stats")
@click.option(
    "--model",
    "model_alias",
    required=True,
    help="Full bench alias (e.g. openai/nvidia-nemotron-30b) or short name.",
)
@click.option(
    "--log-dir",
    default=str(_LOG_DIR),
    show_default=True,
    type=click.Path(),
    help="Directory containing .eval log files.",
)
def stats(model_alias: str, log_dir: str) -> None:
    """Print per-task pillar averages for a model."""
    model_alias = _resolve_alias(model_alias)
    log_path = Path(log_dir)
    task_samples = _load_samples(model_alias, log_path, latest_only=True)
    pillar_map = _load_pillar_map()
    pillar_map_norm = _PILLAR_MAP_NORMALIZED.copy()
    pillar_map_norm.update({k.replace("-", "_"): v for k, v in pillar_map.items()})

    if not task_samples:
        click.echo(f"No eval logs found for {model_alias}.", err=True)
        raise SystemExit(1)

    click.echo(f"{'─'*100}")
    click.echo(f" MODEL: {_short_model(model_alias)}")
    click.echo(f" TASKS: {len(task_samples)}")
    click.echo(f"{'─'*100}")
    click.echo(f" {'Task':<35} {'Pillar':<12} {'Scorer':<14} {'N':>3}  {'Correct':>8}  {'TokRatio':>9}  {'TimeRatio':>10}  {'CostRatio':>10}  {'Cost/sample':>12}")
    click.echo(f" {'-'*35} {'-'*12} {'-'*14} {'-'*3}  {'-'*8}  {'-'*9}  {'-'*10}  {'-'*10}  {'-'*12}")

    task_list = sorted(task_samples.keys())
    for task in task_list:
        samples = task_samples[task]
        stats_ = _per_task_stats(samples)
        pillar = pillar_map_norm.get(task, "?")
        scorer = stats_.get("scorer_type", "?")
        n = stats_.get("n", 0)

        corr = stats_.get("correctness_avg")
        corr_str = f"{corr:.3f}" if corr is not None else "--"

        tr = stats_.get("token_ratio_avg")
        tr_str = f"{tr:.3f}" if tr is not None else "--"

        lr = stats_.get("time_ratio_avg")
        lr_str = f"{lr:.3f}" if lr is not None else "--"

        pr = stats_.get("price_ratio_avg")
        pr_str = _fmt_cost_ratio(pr) if pr is not None else "--"

        cost = stats_.get("avg_cost_usd")
        cost_str = _fmt_avg_cost(cost) if cost is not None else "--"

        flags = []
        if stats_.get("n_nan_tok"):
            flags.append(f"NaNtok={stats_['n_nan_tok']}")
        if stats_.get("n_nan_time"):
            flags.append(f"NaNtime={stats_['n_nan_time']}")
        if stats_.get("n_tok_suppressed"):
            flags.append(f"tokSup={stats_['n_tok_suppressed']}")
        if stats_.get("n_time_suppressed"):
            flags.append(f"timeSup={stats_['n_time_suppressed']}")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        click.echo(f" {task:<35} {pillar:<12} {scorer:<14} {n:>3}  {corr_str:>8}  {tr_str:>9}  {lr_str:>10}  {pr_str:>10}  {cost_str:>12}{flag_str}")

    click.echo(f"{'─'*100}")


# ---------------------------------------------------------------------------
# inspect compare
# ---------------------------------------------------------------------------

@inspect.command("compare")
@click.option(
    "--model",
    "model_alias",
    required=True,
    help="Full bench alias or short name.",
)
@click.option(
    "--log-dir",
    default=str(_LOG_DIR),
    show_default=True,
    type=click.Path(),
    help="Directory containing .eval log files.",
)
@click.option(
    "--delta-threshold",
    default=0.15,
    show_default=True,
    type=float,
    help="Flag tasks where correctness delta exceeds this value.",
)
def compare_cmd(model_alias: str, log_dir: str, delta_threshold: float) -> None:
    """Compare new eval scores against the old baseline for a model.

    Today's run is excluded from the baseline. Tasks with correctness delta
    > --delta-threshold are flagged as SIGNIFICANT.
    """
    model_alias = _resolve_alias(model_alias)
    log_path = Path(log_dir)

    # Load current run samples (today only)
    task_samples = _load_samples(model_alias, log_path, latest_only=True)

    if not task_samples:
        click.echo(f"No eval logs found for {model_alias}.", err=True)
        raise SystemExit(1)

    # Load baseline (all runs except today)
    baseline = _load_baseline(model_alias, log_path)

    click.echo(f"{'─'*90}")
    click.echo(f" MODEL: {_short_model(model_alias)}  |  Delta threshold: {delta_threshold}")
    click.echo(f" BASELINE: {len(baseline)} tasks  |  CURRENT: {len(task_samples)} tasks")
    click.echo(f"{'─'*90}")
    click.echo(f" {'Task':<35} {'Old':>8}  {'New':>8}  {'Delta':>8}  {'Flag':<15} Notes")
    click.echo(f" {'-'*35} {'-'*8}  {'-'*8}  {'-'*8}  {'-'*15} {'-'*30}")

    new_tasks = set(task_samples.keys()) - set(baseline.keys())
    gone_tasks = set(baseline.keys()) - set(task_samples.keys())

    # Sort: significant deltas first, then unchanged
    deltas: list[tuple[str, float | None, float | None, float, str, str]] = []
    for task in sorted(task_samples.keys()):
        samples = task_samples[task]
        stats_ = _per_task_stats(samples)
        new_avg = stats_.get("correctness_avg")

        old_avg = baseline.get(task)
        if old_avg is None:
            deltas.append((task, None, new_avg, 0.0, "NEW TASK", ""))
        else:
            delta = (new_avg - old_avg) if new_avg is not None else 0.0
            abs_d = abs(delta)
            if abs_d > delta_threshold:
                flag = "*** SIGNIFICANT"
            elif abs_d > 0.05:
                flag = "* notable"
            else:
                flag = ""
            deltas.append((task, old_avg, new_avg, delta, flag, ""))

    # Sort: significant first, then notable, then rest
    def sort_key(item: tuple) -> tuple[int, float]:
        _, old, new, delta, flag, _ = item
        priority = 0 if "SIGNIFICANT" in flag else (1 if "* notable" in flag else 2)
        return (priority, -abs(delta))
    deltas.sort(key=sort_key)

    has_issues = False
    for task, old_avg, new_avg, delta, flag, notes in deltas:
        old_str = f"{old_avg:.3f}" if old_avg is not None else "N/A"
        new_str = f"{new_avg:.3f}" if new_avg is not None else "N/A"
        delta_str = f"{delta:+.3f}" if new_avg is not None and old_avg is not None else "N/A"
        flag_str = flag
        if "SIGNIFICANT" in flag or "notable" in flag:
            has_issues = True
        click.echo(f" {task:<35} {old_str:>8}  {new_str:>8}  {delta_str:>8}  {flag_str:<15}")

    if new_tasks:
        click.echo(f"\n NEW TASKS (not in baseline): {', '.join(sorted(new_tasks))}")
    if gone_tasks:
        click.echo(f"\n GONE TASKS (in baseline, not in current): {', '.join(sorted(gone_tasks))}")

    click.echo(f"{'─'*90}")
    if has_issues:
        click.echo(" ⚠ Some tasks have notable deltas — run deep-check to investigate.")


# ---------------------------------------------------------------------------
# inspect deep-check
# ---------------------------------------------------------------------------

@inspect.command("deep-check")
@click.option(
    "--model",
    "model_alias",
    required=True,
    help="Full bench alias or short name.",
)
@click.option(
    "--log-dir",
    default=str(_LOG_DIR),
    show_default=True,
    type=click.Path(),
    help="Directory containing .eval log files.",
)
@click.option(
    "--output",
    type=click.Path(),
    default=None,
    help="Write QA report to file instead of stdout.",
)
def deep_check(model_alias: str, log_dir: str, output: str | None) -> None:
    """Full QA pass — read every sample output and judge explanation for a model.

    For each task, verifies:
    - Score correctness (does the score match the output?)
    - Judge quality (reasoning vs rubber-stamping)
    - Task design quality
    - Scorer-specific sanity

    Writes a structured report. Use --output to save to a file.
    """
    model_alias = _resolve_alias(model_alias)
    log_path = Path(log_dir)
    task_samples = _load_samples(model_alias, log_path, latest_only=True)
    pillar_map = _load_pillar_map()
    pillar_map_norm = _PILLAR_MAP_NORMALIZED.copy()
    pillar_map_norm.update({k.replace("-", "_"): v for k, v in pillar_map.items()})

    if not task_samples:
        click.echo(f"No eval logs found for {model_alias}.", err=True)
        raise SystemExit(1)

    lines: list[str] = []
    lines.append(f"# Deep QA Report — {model_alias}")
    lines.append(f"**Date:** {__import__('datetime').date.today().isoformat()}")
    lines.append(f"**Tasks:** {len(task_samples)}")
    lines.append("")

    # ── Anomaly summary ──────────────────────────────────────────────────────
    anomalies: list[str] = []
    all_tasks = sorted(task_samples.keys())

    for task in all_tasks:
        samples = task_samples[task]
        stats_ = _per_task_stats(samples)
        n = stats_.get("n", 0)

        # Hard anomalies
        if stats_.get("all_correctness_one") and n > 1:
            anomalies.append(f"{task}: ALL-PERFECT correctness (1.0) — verify scorer isn't broken")
        if stats_.get("all_correctness_zero"):
            anomalies.append(f"{task}: ALL-ZERO correctness — scorer bug or model failure")
        if stats_.get("n_nan_tok") == n and n > 0:
            anomalies.append(f"{task}: ALL NaN token_ratio — missing reference budget in task_budgets.py")
        if stats_.get("n_nan_time") == n and n > 0:
            anomalies.append(f"{task}: ALL NaN time_ratio — noise floor triggering incorrectly")

        # Scorer-specific
        if stats_.get("scorer_type") == "verify_sh" and not stats_.get("all_verify_sh_binary"):
            anomalies.append(f"{task}: verify_sh score not binary (0.0/1.0) — scorer bug")

        # Judge quality
        for s in samples:
            if s.scorer_type in ("llm_judge", "hybrid_scorer") and s.judge_explanation:
                if len(s.judge_explanation) < 30:
                    anomalies.append(f"{task}/{s.sample_id}: judge explanation too short (<30 chars)")
                    break

    if anomalies:
        lines.append("## Anomalies")
        for a in anomalies:
            lines.append(f"- {a}")
        lines.append("")

    # ── Per-task deep check ───────────────────────────────────────────────────
    lines.append("## Per-Task Deep Check")
    lines.append("")

    task_verdicts: list[dict] = []

    for task in all_tasks:
        samples = task_samples[task]
        stats_ = _per_task_stats(samples)
        pillar = pillar_map_norm.get(task, "?")
        scorer_type = stats_.get("scorer_type", "?")
        n = stats_.get("n", 0)
        corr_avg = stats_.get("correctness_avg")
        n_llm = stats_.get("n_llm_judge_samples", 0)
        n_verify = stats_.get("n_verify_sh_samples", 0)

        # Read task files
        task_dir = _get_task_dir(task)
        task_py = ""
        scorer_file = ""
        scorer_content = ""

        if task_dir:
            task_py = (task_dir / "task.py").read_text()[:800] if (task_dir / "task.py").is_file() else ""
            if scorer_type == "llm_judge" or scorer_type == "hybrid_scorer":
                for f in ("judge.md", "judge.yaml"):
                    p = task_dir / f
                    if p.is_file():
                        scorer_file = f
                        scorer_content = p.read_text()[:600]
                        break
            elif scorer_type == "verify_sh":
                verify_script = task_dir / "verify.sh"
                if verify_script.is_file():
                    scorer_file = "verify.sh"
                    scorer_content = verify_script.read_text()[:600]

        # Judge quality analysis
        judge_quality = "N/A"
        judge_notes = ""
        if n_llm > 0:
            explanations = [s.judge_explanation for s in samples if s.judge_explanation]
            if not explanations:
                judge_quality = "BROKEN"
                judge_notes = "No explanations found"
            else:
                lens = [len(e) for e in explanations]
                avg_len = sum(lens) / len(lens)
                unique = len(set(explanations))
                if avg_len < 50:
                    judge_quality = "BROKEN"
                    judge_notes = f"Explanations too short (avg {avg_len:.0f} chars)"
                elif unique == 1 and len(explanations) > 1:
                    judge_quality = "BROKEN"
                    judge_notes = "All explanations identical — rubber stamping"
                elif unique <= 2 and len(explanations) > 4:
                    judge_quality = "WEAK"
                    judge_notes = f"Only {unique} unique explanations for {len(explanations)} samples"
                else:
                    judge_quality = "SOUND"
                    judge_notes = f"Avg explanation length: {avg_len:.0f} chars, {unique} unique"

        # Score correctness
        score_sound = "SOUND"
        score_notes = ""
        if scorer_type == "verify_sh":
            non_binary = [s for s in samples if s.correctness is not None and s.correctness not in (0.0, 1.0)]
            if non_binary:
                score_sound = "FLAWED"
                score_notes = f"{len(non_binary)} non-binary scores"
            else:
                score_sound = "SOUND"
        elif scorer_type in ("llm_judge", "hybrid_scorer"):
            # Check judge explanation matches score
            mismatches = 0
            for s in samples:
                if s.judge_explanation and s.correctness is not None:
                    text_lower = s.judge_explanation.lower()
                    # Rough heuristic: does the explanation mention the score?
                    if s.correctness >= 0.75 and not any(w in text_lower for w in ["good", "correct", "pass", "acceptable", "well"]):
                        mismatches += 1
                    elif s.correctness < 0.5 and not any(w in text_lower for w in ["incorrect", "wrong", "fail", "poor", "bad"]):
                        mismatches += 1
            if mismatches > len(samples) * 0.5:
                score_sound = "UNCERTAIN"
                score_notes = f"{mismatches}/{len(samples)} explanations don't match score"
            else:
                score_sound = "SOUND"

        # Hybrid check
        hybrid_ok = True
        hybrid_notes = ""
        if scorer_type == "hybrid_scorer":
            for s in samples:
                if s.verify_sh_score is not None and s.llm_judge_score is not None and s.correctness is not None:
                    expected = s.verify_sh_score * 0.7 + s.llm_judge_score * 0.3
                    if abs(expected - s.correctness) > 0.01:
                        hybrid_ok = False
                        hybrid_notes = f"Hybrid mismatch: verify={s.verify_sh_score}, judge={s.llm_judge_score}, combined={s.correctness}"
                        break
            if hybrid_ok:
                hybrid_notes = "Hybrid weights correct"

        # Task design
        task_design = "REASONABLE"
        design_notes = ""
        prompt_lines = [l for l in task_py.split("\n") if l.strip() and not l.strip().startswith("#")]
        if not prompt_lines:
            task_design = "UNCERTAIN"
            design_notes = "Could not read task prompt"
        elif corr_avg is not None and corr_avg >= 0.95 and n >= 4:
            task_design = "TOO EASY"
            design_notes = f"All models score {corr_avg:.0%} — task provides no signal"
        elif corr_avg is not None and corr_avg <= 0.2 and n >= 4:
            task_design = "TOO HARD"
            design_notes = f"All models score {corr_avg:.0%} — task may be unrealistic"

        # Overall verdict
        if judge_quality == "BROKEN" or score_sound == "FLAWED":
            verdict = "FLAWED"
        elif judge_quality == "WEAK" or score_sound == "UNCERTAIN" or task_design in ("TOO EASY", "TOO HARD"):
            verdict = "UNCERTAIN"
        else:
            verdict = "SOUND"

        lines.append(f"### {task} (`{pillar}`)")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| **Scorer** | {scorer_type} |")
        lines.append(f"| **Samples** | {n} |")
        corr_str = f"{corr_avg:.3f}" if corr_avg is not None else "N/A"
        lines.append(f"| **Correctness avg** | {corr_str} |")
        lines.append(f"| **Judge quality** | {judge_quality} |")
        if judge_notes:
            lines.append(f"| **Judge notes** | {judge_notes} |")
        lines.append(f"| **Score sound?** | {score_sound} |")
        if score_notes:
            lines.append(f"| **Score notes** | {score_notes} |")
        if scorer_type == "hybrid_scorer":
            lines.append(f"| **Hybrid** | {hybrid_notes} |")
        lines.append(f"| **Task design** | {task_design} |")
        if design_notes:
            lines.append(f"| **Design notes** | {design_notes} |")
        lines.append(f"| **Verdict** | {verdict} |")
        lines.append("")

        # Sample outputs (first 2)
        lines.append(f"**Sample outputs** (first 2 of {n}):")
        for s in samples[:2]:
            lines.append(f"```")
            lines.append(f"  Sample: {s.sample_id}  correctness={s.correctness}  working_time={s.working_time:.1f}s")
            if s.output_text:
                out_snippet = s.output_text[:400].replace("\n", "\n  ")
                lines.append(f"  Output:\n  {out_snippet}")
            else:
                lines.append(f"  Output: (empty)")
            if s.judge_explanation:
                lines.append(f"  Judge:\n  {s.judge_explanation[:300]}")
            lines.append(f"```")
            lines.append("")

        task_verdicts.append({
            "task": task,
            "pillar": pillar,
            "verdict": verdict,
            "judge_quality": judge_quality,
            "score_sound": score_sound,
            "task_design": task_design,
        })

    # ── Summary table ─────────────────────────────────────────────────────────
    lines.append("## Verdict Summary")
    lines.append("")
    lines.append(f"| Task | Pillar | Judge Quality | Score Sound | Task Design | Verdict |")
    lines.append(f"|------|--------|--------------|-------------|-------------|---------|")
    for v in task_verdicts:
        lines.append(f"| {v['task']} | {v['pillar']} | {v['judge_quality']} | {v['score_sound']} | {v['task_design']} | {v['verdict']} |")

    report = "\n".join(lines)

    if output:
        Path(output).write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output}")
    else:
        click.echo(report)
