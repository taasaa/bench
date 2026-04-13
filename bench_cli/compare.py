"""EvalLog reading, pillar extraction, and pillar-table comparison."""

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

    # Required positional fields (legacy compatibility)
    correctness: float
    composite: float
    avg_time: float  # mean working_time per sample in seconds
    avg_tokens: float  # mean total tokens per sample
    avg_tokens_per_sec: float  # output tokens / working_time
    samples: int
    scorer: str
    safety: float = 1.0  # only surfaced on failure

    # New optional fields — come AFTER required fields
    efficiency_ratio: float | None = None
    latency_ratio: float | None = None
    exec_safety: float | None = None
    constraint_adherence: float | None = None
    output_safety: float | None = None
    avg_output_tokens: float = 0.0
    tool_call_count: int = 0
    potential_loop: bool = False


@dataclass


class CompareData:

    """All comparison data extracted from logs."""
    # task_name -> model_name -> PillarScores (best run per pair)
    matrix: dict[str, dict[str, PillarScores]] = field(default_factory=dict)
    tasks: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pillar parsing (handles both legacy and new explanation formats)
# ---------------------------------------------------------------------------

_RE_CORRECTNESS = re.compile(r"correctness=([\d.]+)")
_RE_EFFICIENCY = re.compile(r"(?:efficiency_ratio|efficiency)=([\d.]+)")
_RE_SAFETY = re.compile(r"safety(?:_gate)?=([\d.]+)")
_RE_EFF_RATIO = re.compile(r"efficiency_ratio=([\d.]+)")
_RE_LAT_RATIO = re.compile(r"latency_ratio=([\d.]+)")
_RE_EXEC_SAFE = re.compile(r"exec_safety=([\d.]+)")
_RE_CONSTR = re.compile(r"constraint_adherence=([\d.]+)")
_RE_OUT_SAFE = re.compile(r"output_safety=([\d.]+)")
_RE_LOOP = re.compile(r"potential_loop=(true|false)")
_RE_PASS = re.compile(r"PASS (\d+)/(\d+)")


def _parse_pillars(explanation: str) -> tuple[float, float, float] | None:
    """Extract correctness, efficiency, safety from a score explanation.

    Handles both new format (all three pillars present) and legacy format
    (correctness only, e.g. 'correctness=0.00\\nFAIL'). For legacy format,
    efficiency and safety default to 1.00.
    """
    m_c = _RE_CORRECTNESS.search(explanation)
    if not m_c:
        return None
    c = float(m_c.group(1))

    m_e = _RE_EFFICIENCY.search(explanation)
    e = float(m_e.group(1)) if m_e else 1.0

    m_s = _RE_SAFETY.search(explanation)
    s = float(m_s.group(1)) if m_s else 1.0

    return (c, e, s)


def parse_pillar_scores(explanation: str) -> dict:
    """Parse new two-tier explanation fields into a flat dict."""
    if not explanation:
        return {}
    result = {}
    m = _RE_CORRECTNESS.search(explanation)
    if m:
        result["correctness"] = float(m.group(1))
    m = _RE_EFF_RATIO.search(explanation)
    if m:
        result["efficiency_ratio"] = float(m.group(1))
    m = _RE_LAT_RATIO.search(explanation)
    if m:
        result["latency_ratio"] = float(m.group(1))
    m = _RE_EXEC_SAFE.search(explanation)
    if m:
        result["exec_safety"] = float(m.group(1))
    m = _RE_CONSTR.search(explanation)
    if m:
        result["constraint_adherence"] = float(m.group(1))
    m = _RE_OUT_SAFE.search(explanation)
    if m:
        result["output_safety"] = float(m.group(1))
    m = _RE_LOOP.search(explanation)
    if m:
        result["potential_loop"] = m.group(1) == "true"
    return result


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
            total_tokens = (
                sum(u.total_tokens for u in sample.model_usage.values())
                if sample.model_usage
                else 0
            )
            output_tokens = (
                sum(u.output_tokens for u in sample.model_usage.values())
                if sample.model_usage
                else 0
            )

            pillars = _parse_pillars(sc.explanation or "")
            if pillars:
                c, _e, s = pillars
                composite = c * CORRECTNESS_WEIGHT + _e * EFFICIENCY_WEIGHT
                samples_list.append((c, composite, working_time, total_tokens, output_tokens))
            else:
                val = sc.value if isinstance(sc.value, (int, float)) else 0.0
                samples_list.append(
                    (float("nan"), float(val), working_time, total_tokens, output_tokens)
                )

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
# Formatting helpers
# ---------------------------------------------------------------------------

def _short_model(name: str) -> str:
    """Strip 'openai/' prefix for display."""
    return name.removeprefix("openai/")


def _fmt(val: float) -> str:
    if val != val:  # NaN check
        return "  --"
    return f"{val:.2f}"


def _fmt_ratio(val: float | None) -> str:
    """Format a ratio value with < prefix when at floor."""
    if val is None:
        return "  --"
    if val <= 0.01:
        return "<0.01"
    return f"{val:.2f}"


def _fmt_safety(val: float | None) -> str:
    """Format a safety sub-score."""
    if val is None:
        return "  -"
    return f"{val:.2f}"


def _fmt_time(seconds: float) -> str:
    """Format time as human-readable."""
    if seconds != seconds:  # NaN
        return "  --"
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}m{secs:.0f}s"


def _fmt_tokens(tokens: float) -> str:
    if tokens != tokens:  # NaN
        return "  --"
    if tokens >= 1000:
        return f"{tokens/1000:.1f}k"
    return f"{tokens:.0f}"


def _geometric_mean(vals: list[float]) -> float:
    """Geometric mean, guarded against zero/negative."""
    import math
    product = 1.0
    for v in vals:
        if v <= 0:
            return float("nan")
        product *= v
    return math.exp(math.log(product) / len(vals))


def _harmonic_mean(vals: list[float]) -> float:
    """Harmonic mean, guarded against zero."""
    sum_recip = sum(1.0 / v for v in vals if v > 0)
    if sum_recip == 0:
        return float("nan")
    return len(vals) / sum_recip


# ---------------------------------------------------------------------------
# Column layout constants
# ---------------------------------------------------------------------------

# Two-tier column layout: each entry is (header_line1, header_line2, width)
# header_line1=None means this column is in the metric row (no spanning header)
_PILLAR_COLS = [
    ("CORRECT", "CORRECT", 6),
    ("EFF_RATIO", "EFF_RATIO", 8),
    ("LAT_RATIO", "LAT_RATIO", 8),
    ("EXEC_SAFE", "EXEC_SAFE", 8),
    ("CONSTR", "CONSTR", 6),
    ("OUT_SAFE", "OUT_SAFE", 7),
]
_ABSOLUTE_COLS = [
    ("TOK_OUT", "TOK_OUT", 7),
    ("LAT_S", "LAT_S", 6),
    ("TOOLS", "TOOLS", 5),
]


def _get_pillar_cell(ps: PillarScores, key: str) -> str:
    """Get formatted cell value for a given pillar key."""
    val = getattr(ps, key, None)
    if key in ("efficiency_ratio", "latency_ratio"):
        result = _fmt_ratio(val)
        # Add loop warning suffix
        if key == "efficiency_ratio" and getattr(ps, "potential_loop", False):
            result = result.strip() + " *"
        return result
    if key in ("exec_safety", "constraint_adherence", "output_safety"):
        return _fmt_safety(val)
    if key == "avg_output_tokens":
        return _fmt_tokens(val if val == val else float("nan"))
    if key == "avg_time":
        return _fmt_time(val if val == val else float("nan"))
    if key == "tool_call_count":
        if val is None or val != val:
            return "  --"
        return str(int(val))
    return _fmt(val if val == val else float("nan"))


def _mean_cell_for_key(data: CompareData, model: str, key: str) -> str:
    """Compute mean for a specific key across all tasks, format as cell."""
    vals = []
    for task in data.tasks:
        ps = data.matrix.get(task, {}).get(model)
        if ps:
            v = getattr(ps, key, None)
            vals.append(v)
    if key in ("efficiency_ratio", "latency_ratio"):
        valid = [v for v in vals if v is not None and v == v]
        if valid:
            if any(v <= 0.01 for v in valid):
                mean_val = _harmonic_mean(valid)
            else:
                mean_val = _geometric_mean(valid)
        else:
            mean_val = None
    else:
        valid = [v for v in vals if v is not None and v == v]
        mean_val = sum(valid) / len(valid) if valid else None

    # Format using a minimal PillarScores
    if mean_val is not None and mean_val == mean_val:
        fake_ps = PillarScores(
            correctness=1.0, composite=1.0, avg_time=1.0,
            avg_tokens=1.0, avg_tokens_per_sec=1.0,
            samples=1, scorer="mean",
        )
        setattr(fake_ps, key, mean_val)
        return _get_pillar_cell(fake_ps, key)
    return "  --"


# ---------------------------------------------------------------------------
# Table formatting
# ---------------------------------------------------------------------------

def format_pillar_table(
    data: CompareData,
    title: str | None = None,
    include_absolute: bool = True,
) -> str:
    """Two-tier pillar table with a model-name header row.

    Layout (3 header rows, then task rows + MEAN):
      [title line]
      [model name spanning across all columns per model]
      [column labels: CORRECT EFF_RATIO LAT_RATIO EXEC_SAFE CONSTR OUT_SAFE TOK_OUT LAT_S TOOLS]
      [task rows]
      [MEAN row]
    """
    if not data.tasks or not data.models:
        return "No scored eval logs found."

    model_names = [_short_model(m) for m in data.models]
    all_cols = _PILLAR_COLS + (_ABSOLUTE_COLS if include_absolute else [])
    # Key name for each column (matches PillarScores attribute)
    col_keys = [
        "correctness",
        "efficiency_ratio",
        "latency_ratio",
        "exec_safety",
        "constraint_adherence",
        "output_safety",
        "avg_output_tokens",
        "avg_time",
        "tool_call_count",
    ][: len(all_cols)]

    # Column widths: task label + each column
    task_col_w = max(len(t) for t in data.tasks) + 2
    col_widths = [max(w, len(h)) for _, h, w in all_cols]

    lines: list[str] = []

    if title:
        lines.append(f"{'━' * 3} {title} {'━' * 3}")
        lines.append("")

    # ── Row 1: model name spanning total table width ──────────────────────
    table_body_w = sum(col_widths) + len(col_widths) + 1
    row1 = " " * task_col_w
    for model in model_names:
        row1 += model.center(table_body_w) + "  "
    lines.append(row1)

    # Separator after model names
    sep_w = task_col_w + (table_body_w + 2) * len(model_names)
    lines.append("─" * sep_w)

    # ── Row 2: metric column headers ───────────────────────────────────────
    metric_header = " " * task_col_w
    for (abbrev, _full, col_w) in all_cols:
        metric_header += " " + abbrev.center(col_w)
    lines.append(metric_header)

    # ── Row 3: sub-metric names (second tier) ─────────────────────────────
    metric_names = [h for _, h, _ in all_cols]
    sub_header = " " * task_col_w
    for i, col_w in enumerate(col_widths):
        sub_header += " " + metric_names[i].center(col_w)
    lines.append(sub_header)

    # ── Task rows ──────────────────────────────────────────────────────────
    body_sep = "─" * sep_w
    lines.append(body_sep)

    for task in data.tasks:
        row = task.ljust(task_col_w)
        for model in data.models:
            ps = data.matrix.get(task, {}).get(model)
            if ps:
                for key, (_, _, col_w) in zip(col_keys, all_cols, strict=True):
                    cell = _get_pillar_cell(ps, key)
                    row += " " + cell.rjust(col_w)
                row += " "
            else:
                for _, _, col_w in all_cols:
                    row += " " + "—".rjust(col_w) + " "
        lines.append(row)

    # ── MEAN row ───────────────────────────────────────────────────────────
    lines.append(body_sep)
    mean_row = "MEAN".ljust(task_col_w)
    for model in data.models:
        for key, (_, _, col_w) in zip(col_keys, all_cols, strict=True):
            cell = _mean_cell_for_key(data, model, key)
            mean_row += " " + cell.rjust(col_w)
        mean_row += " "
    lines.append(mean_row)

    return "\n".join(lines)


# Keep format_pivot_table as alias for backward compat / simple view
def format_pivot_table(
    data: CompareData,
    pillar: str = "composite",
    title: str | None = None,
) -> str:
    """Format a simple pivot table (backward compatible view)."""
    return format_pillar_table(data, title, include_absolute=True)


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

    # Pillar scores table (two-tier)
    parts.append(format_pillar_table(
        data,
        "PILLAR SCORES",
        include_absolute=True,
    ))
    parts.append("")

    # Composite (legacy)
    parts.append(format_pivot_table(
        data,
        "composite",
        "COMPOSITE  "
        f"(correctness*{CORRECTNESS_WEIGHT} + efficiency*{EFFICIENCY_WEIGHT}) * safety",
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
                eff_ratio = round(ps.efficiency_ratio, 4) \
                    if ps.efficiency_ratio is not None else None
                lat_ratio = round(ps.latency_ratio, 4) \
                    if ps.latency_ratio is not None else None
                exec_s = round(ps.exec_safety, 4) \
                    if ps.exec_safety is not None else None
                constr = round(ps.constraint_adherence, 4) \
                    if ps.constraint_adherence is not None else None
                out_s = round(ps.output_safety, 4) if ps.output_safety is not None else None
                rows.append({
                    "task": task,
                    "model": model,
                    "scorer": ps.scorer,
                    "composite": round(ps.composite, 4),
                    "correctness": round(ps.correctness, 4),
                    "avg_tokens": round(ps.avg_tokens, 1),
                    "avg_output_tokens": round(ps.avg_output_tokens, 1),
                    "avg_time": round(ps.avg_time, 2),
                    "efficiency_ratio": eff_ratio,
                    "latency_ratio": lat_ratio,
                    "exec_safety": exec_s,
                    "constraint_adherence": constr,
                    "output_safety": out_s,
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
