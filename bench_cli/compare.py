"""EvalLog reading, pillar extraction, and pivot-table comparison."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from scorers.composite import CORRECTNESS_WEIGHT, EFFICIENCY_WEIGHT


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PillarScores:
    """Score breakdown for one (task, model) pair — averaged over samples."""
    correctness: float
    composite: float
    avg_time: float  # mean working_time per sample in seconds
    avg_tokens: float  # mean total tokens per sample
    avg_tokens_per_sec: float  # output tokens / working_time
    samples: int
    scorer: str
    safety: float = 1.0  # only surfaced on failure


@dataclass
class CompareData:
    """All comparison data extracted from logs."""
    # task_name -> model_name -> PillarScores (best run per pair)
    matrix: dict[str, dict[str, PillarScores]] = field(default_factory=dict)
    tasks: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pillar parsing
# ---------------------------------------------------------------------------

_RE_CORRECTNESS = re.compile(r"correctness=([\d.]+)")
_RE_EFFICIENCY = re.compile(r"efficiency=([\d.]+)")
_RE_SAFETY = re.compile(r"safety(?:_gate)?=([\d.]+)")


def _parse_pillars(explanation: str) -> tuple[float, float, float] | None:
    """Extract correctness, efficiency, safety from a score explanation."""
    m_c = _RE_CORRECTNESS.search(explanation)
    m_e = _RE_EFFICIENCY.search(explanation)
    m_s = _RE_SAFETY.search(explanation)
    if m_c and m_e and m_s:
        return float(m_c.group(1)), float(m_e.group(1)), float(m_s.group(1))
    return None


# ---------------------------------------------------------------------------
# Log loading
# ---------------------------------------------------------------------------

def load_compare_data(log_dir: str, latest: int | None = None) -> CompareData:
    """Read eval logs and extract pillar-scored data.

    For each (task, model) pair, keeps the run with the highest composite
    score. Requires reading full logs (not header-only) to get per-sample
    score explanations and timing.
    """
    from inspect_ai.log import list_eval_logs, read_eval_log

    log_path = Path(log_dir)
    if not log_path.is_dir():
        return CompareData()

    infos = list_eval_logs(log_dir=str(log_path), descending=True)
    if latest is not None:
        infos = infos[:latest]

    # Accumulate all per-sample data per (task, model, run)
    # Each entry: (samples, eval_log, scorer_name)
    run_samples: dict[
        tuple[str, str, str],
        tuple[list[tuple[float, float, float, int, int]], object, str],
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
        scorer_name = el.results.scores[0].scorer
        run_key = (task, model, info.name)

        samples_list: list[tuple[float, float, float, int, int]] = []

        for sample in el.samples:
            sc = None
            if isinstance(sample.scores, dict):
                sc = sample.scores.get(scorer_name)
            elif isinstance(sample.scores, list):
                for s in sample.scores:
                    if hasattr(s, "value"):
                        sc = s
                        break

            if sc is None:
                continue

            working_time = sample.working_time or 0.0
            total_tokens = sum(u.total_tokens for u in sample.model_usage.values()) if sample.model_usage else 0
            output_tokens = sum(u.output_tokens for u in sample.model_usage.values()) if sample.model_usage else 0

            pillars = _parse_pillars(sc.explanation or "")
            if pillars:
                c, _e, s = pillars
                composite = c * CORRECTNESS_WEIGHT + _e * EFFICIENCY_WEIGHT
                samples_list.append((c, composite, working_time, total_tokens, output_tokens))
            else:
                val = sc.value if isinstance(sc.value, (int, float)) else 0.0
                samples_list.append((float("nan"), float(val), working_time, total_tokens, output_tokens))

        if samples_list:
            run_samples[run_key] = (samples_list, el, scorer_name)

    # For each (task, model), pick the best run by mean composite
    best: dict[tuple[str, str], PillarScores] = {}

    for (task, model, _log_name), (samples, eval_log, scorer_name) in run_samples.items():
        mean_composite = sum(s[1] for s in samples) / len(samples)
        key = (task, model)

        if key not in best or mean_composite > best[key].composite:
            n = len(samples)
            avg_c = sum(s[0] for s in samples) / n
            avg_t = sum(s[2] for s in samples) / n
            avg_tok = sum(s[3] for s in samples) / n
            avg_out_tok = sum(s[4] for s in samples) / n
            avg_tps = avg_out_tok / avg_t if avg_t > 0 else 0.0

            safety = 1.0
            for sample in eval_log.samples:
                sc = None
                if isinstance(sample.scores, dict):
                    sc = sample.scores.get(scorer_name)
                if sc and sc.explanation:
                    m_s = _RE_SAFETY.search(sc.explanation)
                    if m_s:
                        safety = float(m_s.group(1))
                        break

            best[key] = PillarScores(
                correctness=avg_c,
                composite=mean_composite,
                avg_time=avg_t,
                avg_tokens=avg_tok,
                avg_tokens_per_sec=avg_tps,
                samples=n,
                scorer="composite",
                safety=safety,
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
# Formatting
# ---------------------------------------------------------------------------

def _short_model(name: str) -> str:
    """Strip 'openai/' prefix for display."""
    return name.removeprefix("openai/")


def _fmt(val: float) -> str:
    if val != val:  # NaN check
        return "  —"
    return f"{val:.2f}"


def _fmt_time(seconds: float) -> str:
    """Format time as human-readable."""
    if seconds != seconds:  # NaN
        return "  —"
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}m{secs:.0f}s"


def _fmt_tokens(tokens: float) -> str:
    if tokens != tokens:  # NaN
        return "  —"
    if tokens >= 1000:
        return f"{tokens/1000:.1f}k"
    return f"{tokens:.0f}"


def format_pivot_table(
    data: CompareData,
    pillar: str = "composite",
    title: str | None = None,
) -> str:
    """Format a pivot table: tasks as rows, models as columns."""
    if not data.tasks or not data.models:
        return "No scored eval logs found."

    model_names = [_short_model(m) for m in data.models]
    task_col_w = max(len(t) for t in data.tasks) + 2
    model_col_w = max(max(len(m) for m in model_names), 6)

    lines: list[str] = []

    if title:
        lines.append(f"{'━' * 3} {title} {'━' * 3}")
        lines.append("")

    # Header
    header = " " * task_col_w + "  ".join(m.center(model_col_w) for m in model_names)
    lines.append(header)

    # Separator
    sep = "─" * task_col_w + "─" * (model_col_w + 2) * len(data.models)
    lines.append(sep)

    def _get_pillar(ps: PillarScores, p: str) -> str:
        val = {
            "composite": ps.composite,
            "correctness": ps.correctness,
            "time": ps.avg_time,
            "tokens": ps.avg_tokens,
            "speed": ps.avg_tokens_per_sec,
        }.get(p)
        if val is None:
            return "  —"
        if p == "time":
            return _fmt_time(val)
        if p == "tokens":
            return _fmt_tokens(val)
        if p == "speed":
            return f"{val:.1f}" if val == val else "  —"
        return _fmt(val)

    # Task rows
    for task in data.tasks:
        cells = []
        for model in data.models:
            ps = data.matrix.get(task, {}).get(model)
            if ps:
                cells.append(_get_pillar(ps, pillar).center(model_col_w))
            else:
                cells.append("  —".center(model_col_w))
        lines.append(task.ljust(task_col_w) + "  ".join(cells))

    # Mean row
    lines.append(sep)
    mean_cells = []
    for model in data.models:
        vals = []
        for task in data.tasks:
            ps = data.matrix.get(task, {}).get(model)
            if ps:
                val = {
                    "composite": ps.composite,
                    "correctness": ps.correctness,
                    "time": ps.avg_time,
                    "tokens": ps.avg_tokens,
                    "speed": ps.avg_tokens_per_sec,
                }.get(pillar)
                if val is not None and val == val:  # skip NaN
                    vals.append(val)
        if vals:
            if pillar == "time":
                mean_cells.append(_fmt_time(sum(vals) / len(vals)).center(model_col_w))
            elif pillar == "tokens":
                mean_cells.append(_fmt_tokens(sum(vals) / len(vals)).center(model_col_w))
            elif pillar == "speed":
                mean_cells.append(f"{sum(vals)/len(vals):.1f}".center(model_col_w))
            else:
                mean_cells.append(_fmt(sum(vals) / len(vals)).center(model_col_w))
        else:
            mean_cells.append("  —".center(model_col_w))
    lines.append("MEAN".ljust(task_col_w) + "  ".join(mean_cells))

    return "\n".join(lines)


def _safety_warnings(data: CompareData) -> str | None:
    """Return safety warnings if any model/task has safety < 1.0."""
    warnings = []
    for task in data.tasks:
        for model in data.models:
            ps = data.matrix.get(task, {}).get(model)
            if ps and ps.safety == ps.safety and ps.safety < 1.0:  # not NaN
                short_model = _short_model(model)
                warnings.append(f"  ⚠ {short_model} / {task}: safety_gate={ps.safety:.2f}")
    if not warnings:
        return None
    return "⚠ SAFETY FAILURES:\n" + "\n".join(warnings)


def format_all_tables(data: CompareData) -> str:
    """Format all pillar tables."""
    parts = []

    # Composite (the main score)
    parts.append(format_pivot_table(
        data, "composite",
        f"COMPOSITE  (correctness×{CORRECTNESS_WEIGHT} + efficiency×{EFFICIENCY_WEIGHT}) × safety",
    ))
    parts.append("")

    # Correctness
    parts.append(format_pivot_table(
        data, "correctness",
        "CORRECTNESS  (did the model produce the right output?)",
    ))
    parts.append("")

    # Tokens
    parts.append(format_pivot_table(
        data, "tokens",
        "AVG TOKENS PER SAMPLE  (total tokens — lower is better)",
    ))
    parts.append("")

    # Time
    parts.append(format_pivot_table(
        data, "time",
        "AVG TIME PER SAMPLE  (model API latency)",
    ))
    parts.append("")

    # Speed (tokens/s)
    parts.append(format_pivot_table(
        data, "speed",
        "OUTPUT TOKENS/SEC  (throughput — higher is better)",
    ))
    parts.append("")

    # Safety warnings only if failures exist
    safety = _safety_warnings(data)
    if safety:
        parts.append(safety)
        parts.append("")

    return "\n".join(parts)


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
                    "scorer": ps.scorer,
                    "composite": round(ps.composite, 4),
                    "correctness": round(ps.correctness, 4),
                    "avg_tokens": round(ps.avg_tokens, 1),
                    "avg_time": round(ps.avg_time, 2),
                    "tokens_per_sec": round(ps.avg_tokens_per_sec, 1),
                    "samples": ps.samples,
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
        click.echo(format_all_tables(data))
