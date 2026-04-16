"""EvalLog reading, pillar extraction, and pillar-table comparison.

Each task has 3 independent scorers producing separate Score objects:
  - verify_sh or llm_judge → correctness (value = 0..1)
  - token_ratio_scorer     → efficiency (value = ref_tokens/actual_tokens)
  - time_ratio_scorer      → latency    (value = ref_seconds/actual_seconds)

Correctness comes from whichever scorer is present: verify_sh for script-graded
tasks, llm_judge for LLM-graded tasks. Tasks use one or the other, not both.

load_compare_data iterates ALL scorers per sample to extract each pillar
from its dedicated scorer, rather than trying to parse everything from
scores[0] (which was the old broken approach).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PillarScores:
    """Score breakdown for one (task, model) pair — averaged over samples."""

    correctness: float
    token_ratio: float
    time_ratio: float
    avg_tokens: float      # mean total tokens per sample
    avg_time: float        # mean working_time per sample in seconds
    samples: int

    # Per-sample counts for suppression/bookkeeping
    token_suppressed: int = 0
    time_suppressed: int = 0


@dataclass
class CompareData:
    """All comparison data extracted from logs."""
    # task_name -> model_name -> PillarScores (best run per pair)
    matrix: dict[str, dict[str, PillarScores]] = field(default_factory=dict)
    tasks: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Score extraction helpers
# ---------------------------------------------------------------------------

_RE_EFF_RATIO = re.compile(r"efficiency_ratio=([\d.]+)")
_RE_LAT_RATIO = re.compile(r"latency_ratio=([\d.]+)")
_RE_LOOP = re.compile(r"potential_loop=(true|false)")


def _numeric_val(score: object) -> float | None:
    """Extract a non-NaN numeric value from a score object, or None."""
    if score is None:
        return None
    val = getattr(score, "value", None)
    if isinstance(val, (int, float)) and val == val:  # not NaN
        return float(val)
    return None


def _extract_from_scorers(
    sample_scores: dict,
) -> tuple[float | None, float | None, float | None]:
    """Extract (correctness, token_ratio, time_ratio) from a sample's score dict.

    Each scorer has its own entry keyed by scorer name:
      - "llm_judge"          → .value = correctness (0..1), takes precedence
      - "verify_sh"          → .value = correctness (0..1), fallback
      - "token_ratio_scorer" → .value = ratio (may be NaN if suppressed)
      - "time_ratio_scorer"  → .value = ratio (may be NaN if suppressed)

    Correctness: llm_judge is checked first, then verify_sh. Tasks use
    one or the other, not both.
    """
    # Correctness: prefer llm_judge, fall back to verify_sh
    correctness = _numeric_val(sample_scores.get("llm_judge"))
    if correctness is None:
        correctness = _numeric_val(sample_scores.get("verify_sh"))

    token_ratio = _numeric_val(sample_scores.get("token_ratio_scorer"))
    time_ratio = _numeric_val(sample_scores.get("time_ratio_scorer"))

    return correctness, token_ratio, time_ratio


def _is_suppressed(score: object) -> bool:
    """Check if a scorer marked its result as suppressed (noise floor)."""
    if hasattr(score, "metadata") and isinstance(score.metadata, dict):
        return score.metadata.get("suppressed", False)
    return False


# ---------------------------------------------------------------------------
# Log loading
# ---------------------------------------------------------------------------

def load_compare_data(log_dir: str, latest: int | None = None) -> CompareData:
    """Read eval logs and extract pillar-scored data.

    For each (task, model) pair, keeps the run with the highest mean
    correctness. Reads ALL scorers per sample — not just scores[0].
    """
    from inspect_ai.log import list_eval_logs, read_eval_log

    log_path = Path(log_dir)
    if not log_path.is_dir():
        return CompareData()

    infos = list_eval_logs(log_dir=str(log_path), descending=True)
    if latest is not None:
        infos = infos[:latest]

    # Accumulate per-sample data per (task, model, run_name)
    # Each entry: list of (correctness, token_ratio, time_ratio, total_tokens, working_time, token_suppressed, time_suppressed)
    run_samples: dict[
        tuple[str, str, str],
        list[tuple[float | None, float | None, float | None, int, float, bool, bool]],
    ] = {}

    for info in infos:
        try:
            el = read_eval_log(info)
        except Exception:
            continue

        if el.status != "success" or not el.results or not el.results.scores:
            continue

        task = el.eval.task
        model = el.eval.model
        run_key = (task, model, info.name)

        samples_list: list[
            tuple[float | None, float | None, float | None, int, float, bool, bool]
        ] = []

        for sample in el.samples:
            if not isinstance(sample.scores, dict):
                continue

            correctness, token_ratio, time_ratio = _extract_from_scorers(sample.scores)

            total_tokens = (
                sum(u.total_tokens for u in sample.model_usage.values())
                if sample.model_usage
                else 0
            )
            working_time = sample.working_time or 0.0

            tok_supp = _is_suppressed(sample.scores.get("token_ratio_scorer"))
            time_supp = _is_suppressed(sample.scores.get("time_ratio_scorer"))

            samples_list.append((
                correctness, token_ratio, time_ratio,
                total_tokens, working_time,
                tok_supp, time_supp,
            ))

        if samples_list:
            run_samples[run_key] = samples_list

    # For each (task, model), pick the best run by mean correctness
    best: dict[tuple[str, str], PillarScores] = {}

    for (task, model, _log_name), samples_list in run_samples.items():
        # Mean correctness for run ranking
        valid_c = [s[0] for s in samples_list if s[0] is not None]
        mean_c = sum(valid_c) / len(valid_c) if valid_c else 0.0

        key = (task, model)
        if key in best and mean_c <= best[key].correctness:
            continue

        n = len(samples_list)

        # Correctness average
        avg_correctness = sum(valid_c) / len(valid_c) if valid_c else 0.0

        # Token ratio average (skip None/NaN)
        valid_tr = [s[1] for s in samples_list if s[1] is not None]
        avg_token_ratio = sum(valid_tr) / len(valid_tr) if valid_tr else 0.0

        # Time ratio average (skip None/NaN)
        valid_lr = [s[2] for s in samples_list if s[2] is not None]
        avg_time_ratio = sum(valid_lr) / len(valid_lr) if valid_lr else 0.0

        # Absolute metrics
        avg_tokens = sum(s[3] for s in samples_list) / n
        avg_time = sum(s[4] for s in samples_list) / n

        token_suppressed = sum(1 for s in samples_list if s[5])
        time_suppressed = sum(1 for s in samples_list if s[6])

        best[key] = PillarScores(
            correctness=avg_correctness,
            token_ratio=avg_token_ratio,
            time_ratio=avg_time_ratio,
            avg_tokens=avg_tokens,
            avg_time=avg_time,
            samples=n,
            token_suppressed=token_suppressed,
            time_suppressed=time_suppressed,
        )

    # Build ordered task and model lists
    tasks = sorted({t for t, _ in best})
    models = sorted({m for _, m in best})

    matrix: dict[str, dict[str, PillarScores]] = {}
    for task in tasks:
        matrix[task] = {}
        for model in models:
            if (task, model) in best:
                matrix[task][model] = best[(task, model)]

    return CompareData(matrix=matrix, tasks=tasks, models=models)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _short_model(name: str) -> str:
    """Strip 'openai/' prefix for display."""
    return name.removeprefix("openai/")


def _fmt(val: float) -> str:
    if math.isnan(val):
        return "  --"
    return f"{val:.2f}"


def _fmt_ratio(val: float) -> str:
    """Format a ratio value."""
    if math.isnan(val):
        return "  --"
    if val <= 0.0:
        return " <0.1"
    if val < 0.1:
        return f"<{val:.2f}"
    return f"{val:.2f}"


def _fmt_time(seconds: float) -> str:
    if math.isnan(seconds):
        return "  --"
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}m{secs:.0f}s"


def _fmt_tokens(tokens: float) -> str:
    if math.isnan(tokens):
        return "  --"
    if tokens >= 1000:
        return f"{tokens/1000:.1f}k"
    return f"{tokens:.0f}"


def _geometric_mean(vals: list[float]) -> float:
    if not vals:
        return float("nan")
    for v in vals:
        if v <= 0:
            return float("nan")
    log_sum = math.fsum(math.log(v) for v in vals)
    return math.exp(log_sum / len(vals))


# ---------------------------------------------------------------------------
# Table formatting
# ---------------------------------------------------------------------------

# Columns: TASK | CORRECT | TOK_RATIO | TIME_RATIO | TOKENS | TIME
_COL_HEADERS = ["CORRECT", "TOK_RATIO", "TIME_RATIO", "TOKENS", "TIME"]
_COL_KEYS = ["correctness", "token_ratio", "time_ratio", "avg_tokens", "avg_time"]
_COL_WIDTHS = [7, 9, 10, 7, 7]


def format_pillar_table(
    data: CompareData,
    title: str | None = None,
) -> str:
    """Single pillar table with per-model columns.

    Layout:
      [title line]
      [model name spanning all columns per model]
      [column headers]
      [task rows]
      [MEAN row]
    """
    if not data.tasks or not data.models:
        return "No scored eval logs found."

    model_names = [_short_model(m) for m in data.models]

    # Column widths
    task_col_w = max(len(t) for t in data.tasks) + 2
    body_w_per_model = sum(_COL_WIDTHS) + len(_COL_WIDTHS) + 1  # +spaces

    lines: list[str] = []

    if title:
        lines.append(f"{'━' * 3} {title} {'━' * 3}")
        lines.append("")

    # Row 1: model names
    row1 = " " * task_col_w
    for model in model_names:
        row1 += model.center(body_w_per_model) + "  "
    lines.append(row1)

    # Separator
    sep_w = task_col_w + (body_w_per_model + 2) * len(model_names)
    lines.append("─" * sep_w)

    # Row 2: column headers
    header = " " * task_col_w
    for _ in model_names:
        for col_name, col_w in zip(_COL_HEADERS, _COL_WIDTHS):
            header += " " + col_name.rjust(col_w)
        header += " "
    lines.append(header)

    # Task rows
    lines.append("─" * sep_w)

    for task in data.tasks:
        row = task.ljust(task_col_w)
        for model in data.models:
            ps = data.matrix.get(task, {}).get(model)
            if ps:
                cells = [
                    _fmt(ps.correctness),
                    _fmt_ratio(ps.token_ratio),
                    _fmt_ratio(ps.time_ratio),
                    _fmt_tokens(ps.avg_tokens),
                    _fmt_time(ps.avg_time),
                ]
                for cell, col_w in zip(cells, _COL_WIDTHS):
                    row += " " + cell.rjust(col_w)
                row += " "
            else:
                for col_w in _COL_WIDTHS:
                    row += " " + "—".rjust(col_w) + " "
        lines.append(row)

    # MEAN row
    lines.append("─" * sep_w)
    mean_row = "MEAN".ljust(task_col_w)
    for model in data.models:
        # Collect per-task values
        c_vals, tr_vals, lr_vals = [], [], []
        tok_vals, time_vals = [], []
        for task in data.tasks:
            ps = data.matrix.get(task, {}).get(model)
            if ps:
                c_vals.append(ps.correctness)
                if ps.token_ratio > 0:
                    tr_vals.append(ps.token_ratio)
                if ps.time_ratio > 0:
                    lr_vals.append(ps.time_ratio)
                tok_vals.append(ps.avg_tokens)
                time_vals.append(ps.avg_time)

        cells = [
            _fmt(sum(c_vals) / len(c_vals)) if c_vals else "  --",
            _fmt_ratio(_geometric_mean(tr_vals)) if tr_vals else "  --",
            _fmt_ratio(_geometric_mean(lr_vals)) if lr_vals else "  --",
            _fmt_tokens(sum(tok_vals) / len(tok_vals)) if tok_vals else "  --",
            _fmt_time(sum(time_vals) / len(time_vals)) if time_vals else "  --",
        ]
        for cell, col_w in zip(cells, _COL_WIDTHS):
            mean_row += " " + cell.rjust(col_w)
        mean_row += " "
    lines.append(mean_row)

    return "\n".join(lines)


def format_json(data: CompareData) -> str:
    """Machine-readable JSON output."""
    import json

    rows = []
    for task in data.tasks:
        for model in data.models:
            ps = data.matrix.get(task, {}).get(model)
            if ps:
                rows.append({
                    "task": task,
                    "model": model,
                    "correctness": round(ps.correctness, 4),
                    "token_ratio": round(ps.token_ratio, 4),
                    "time_ratio": round(ps.time_ratio, 4),
                    "avg_tokens": round(ps.avg_tokens, 1),
                    "avg_time": round(ps.avg_time, 2),
                    "samples": ps.samples,
                    "token_suppressed": ps.token_suppressed,
                    "time_suppressed": ps.time_suppressed,
                })
    return json.dumps(rows, indent=2)


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

import click


@click.command()
@click.option(
    "--log-dir",
    default="logs",
    show_default=True,
    type=click.Path(),
    help="Directory containing EvalLog files.",
)
@click.option(
    "--latest",
    type=int,
    default=None,
    help="Limit to the last N runs (default: all).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def compare(log_dir: str, latest: int | None, as_json: bool) -> None:
    """Compare evaluation results across models with pillar breakdowns."""
    data = load_compare_data(log_dir, latest)

    if as_json:
        click.echo(format_json(data))
    else:
        click.echo(format_pillar_table(data, "BENCHMARK RESULTS"))
