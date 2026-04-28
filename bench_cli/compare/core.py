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

from scorers.task_budgets import get_task_budget

# ---------------------------------------------------------------------------
# Model pricing (hardcoded / user-provided — not from KiloCode cache)
# Used to recalculate actual_cost_usd for models whose prices weren't
# captured correctly in eval log scorer metadata.
# ---------------------------------------------------------------------------
_MANUAL_PRICES: dict[str, tuple[float, float]] = {
    # model_alias → (input_price_per_M, output_price_per_M)
    # Covers all models evaluated before the per-token→per-M cache fix.
    "openai/default": (0.30, 1.20),
    "openai/nvidia-mistral-small4": (0.15, 0.60),
    "openai/nvidia-nemotron-30b": (0.05, 0.20),
    "openai/nvidia-devstral": (0.40, 2.00),
    "openai/nvidia-qwen-next": (0.455, 1.82),
    "openai/gemma-4-26-local": (0.08, 0.35),
    "openai/qwen-local": (0.1625, 1.30),
}


def _recalc_cost(model_alias: str, input_tokens: int, output_tokens: int) -> float | None:
    """Recalculate actual cost using manual price table.

    Returns None if model is not in _MANUAL_PRICES.
    """
    prices = _MANUAL_PRICES.get(model_alias)
    if prices is None:
        return None
    inp_price, out_price = prices
    return input_tokens * inp_price / 1_000_000 + output_tokens * out_price / 1_000_000


@dataclass
class PillarScores:
    """Score breakdown for one (task, model) pair — averaged over samples."""

    correctness: float
    token_ratio: float
    time_ratio: float
    avg_tokens: float  # mean total tokens per sample
    avg_time: float  # mean working_time per sample in seconds
    samples: int
    price_ratio: float = float("nan")  # geometric mean of cost ratios, NaN if unavailable
    avg_cost_usd: float = float("nan")  # mean cost per sample in USD, NaN if unavailable
    tier_breakdown: dict[str, dict] | None = None  # per-tier info for smart-router models

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


_RE_EFF_RATIO = re.compile(r"efficiency_ratio=([\d.]+)")
_RE_LAT_RATIO = re.compile(r"latency_ratio=([\d.]+)")
_RE_LOOP = re.compile(r"potential_loop=(true|false)")


def _numeric_val(score: object) -> float | None:
    """Extract a non-NaN numeric value from a score object, or None.

    Handles:
      - float/int: returned as-is (1.0, 0.0, inf, NaN)
      - string 'C'/'I': convert to 1.0/0.0 (includes/exact scorers)
      - string numeric: attempt float() conversion
      - None: return None
    """
    if score is None:
        return None
    val = getattr(score, "value", None)
    if isinstance(val, (int, float)) and val == val:  # not NaN
        return float(val)
    if isinstance(val, str):
        # Handle CORRECT/INCORRECT from includes/exact scorers (returns 'C'/'I')
        upper = val.upper()
        if upper in ("C", "CORRECT"):
            return 1.0
        if upper in ("I", "INCORRECT"):
            return 0.0
        # Try numeric string
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    return None


def _extract_from_scorers(
    sample_scores: dict,
    sample_model_usage: dict | None = None,
    model_alias: str | None = None,
) -> tuple[float | None, float | None, float | None, float | None, dict[str, dict] | None]:
    """Extract (correctness, token_ratio, time_ratio, actual_cost_usd, tier_breakdown) from a sample's score dict.

    Correctness: llm_judge > verify_sh > exact > includes (strings 'C'/'I'
    are converted to 1.0/0.0 by _numeric_val).

    Returns actual_cost_usd from price_ratio_scorer metadata, or recalculated
    from _MANUAL_PRICES if sample_model_usage and model_alias are provided.
    """
    # Correctness: hybrid_scorer > llm_judge > verify_sh > exact > includes
    # (exact/includes return 'C'/'I' strings, mean() converts to 1.0/0.0 inside Inspect,
    # but compare reads raw scorer keys for pillar extraction)
    correctness = _numeric_val(sample_scores.get("hybrid_scorer"))
    if correctness is None:
        correctness = _numeric_val(sample_scores.get("llm_judge"))
    if correctness is None:
        correctness = _numeric_val(sample_scores.get("verify_sh"))
    if correctness is None:
        correctness = _numeric_val(sample_scores.get("exact"))
    if correctness is None:
        correctness = _numeric_val(sample_scores.get("includes"))

    token_ratio = _numeric_val(sample_scores.get("token_ratio_scorer"))
    time_ratio = _numeric_val(sample_scores.get("time_ratio_scorer"))

    # Extract actual_cost_usd from price_ratio_scorer metadata
    actual_cost_usd: float | None = None
    pr_score = sample_scores.get("price_ratio_scorer")
    if (
        pr_score is not None
        and hasattr(pr_score, "metadata")
        and isinstance(pr_score.metadata, dict)
    ):
        cost_val = pr_score.metadata.get("actual_cost_usd")
        if isinstance(cost_val, (int, float)):
            actual_cost_usd = float(cost_val)

    # Fall back to manual price recalculation if scorer didn't capture cost
    # or if the cached cost is from the old per-token cache (pre-fix values are ~1e-10).
    if actual_cost_usd is None or (actual_cost_usd is not None and actual_cost_usd < 1e-6):
        if sample_model_usage and model_alias:
            # Find the primary model usage (exclude 'openai/judge')
            primary = None
            if model_alias in sample_model_usage:
                primary = sample_model_usage[model_alias]
            elif len(sample_model_usage) == 1:
                primary = next(iter(sample_model_usage.values()))
            if primary is not None:
                inp = getattr(primary, "input_tokens", 0) or 0
                out = getattr(primary, "output_tokens", 0) or 0
                recalc = _recalc_cost(model_alias, int(inp), int(out))
                if recalc is not None:
                    actual_cost_usd = recalc

    # Extract tier_breakdown from price_ratio_scorer metadata
    tier_breakdown: dict[str, dict] | None = None
    if (
        pr_score is not None
        and hasattr(pr_score, "metadata")
        and isinstance(pr_score.metadata, dict)
    ):
        tb = pr_score.metadata.get("tier_breakdown")
        if isinstance(tb, dict) and tb:
            tier_breakdown = tb

    return correctness, token_ratio, time_ratio, actual_cost_usd, tier_breakdown


def _is_suppressed(score: object) -> bool:
    """Check if a scorer marked its result as suppressed (noise floor)."""
    if hasattr(score, "metadata") and isinstance(score.metadata, dict):
        return score.metadata.get("suppressed", False)
    return False


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
    # Each entry: list of (correctness, token_ratio, time_ratio, total_tokens,
    # working_time, token_suppressed, time_suppressed, actual_cost_usd, tier_breakdown)
    run_samples: dict[
        tuple[str, str, str],
        list[
            tuple[
                float | None,
                float | None,
                float | None,
                int,
                float,
                bool,
                bool,
                float | None,
                dict[str, dict] | None,
            ]
        ],
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
            tuple[
                float | None,
                float | None,
                float | None,
                int,
                float,
                bool,
                bool,
                float | None,
                dict[str, dict] | None,
            ]
        ] = []

        for sample in el.samples:
            if not isinstance(sample.scores, dict):
                continue

            correctness, token_ratio, time_ratio, actual_cost_usd, tier_breakdown = _extract_from_scorers(
                sample.scores, sample.model_usage, model
            )

            total_tokens = (
                sum(u.total_tokens for u in sample.model_usage.values())
                if sample.model_usage
                else 0
            )
            working_time = sample.working_time or 0.0

            tok_supp = _is_suppressed(sample.scores.get("token_ratio_scorer"))
            time_supp = _is_suppressed(sample.scores.get("time_ratio_scorer"))

            samples_list.append(
                (
                    correctness,
                    token_ratio,
                    time_ratio,
                    total_tokens,
                    working_time,
                    tok_supp,
                    time_supp,
                    actual_cost_usd,
                    tier_breakdown,
                )
            )

        if samples_list:
            run_samples[run_key] = samples_list

    # For each (task, model), keep the latest run (logs are loaded newest-first)
    best: dict[tuple[str, str], PillarScores] = {}

    for (task, model, _log_name), samples_list in run_samples.items():
        key = (task, model)
        if key in best:
            continue

        n = len(samples_list)

        # Correctness average
        valid_c = [s[0] for s in samples_list if s[0] is not None]
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

        # Average cost USD (arithmetic mean of actual costs)
        valid_cost = [s[7] for s in samples_list if s[7] is not None]
        avg_cost_usd = sum(valid_cost) / len(valid_cost) if valid_cost else float("nan")

        # Price ratio: recompute using current reference costs from task_budgets.py
        # (the ratio stored in eval logs uses stale references from the time of the run)
        budget = get_task_budget(task)
        if budget and budget.reference_cost_usd is not None and valid_cost:
            ratios = [budget.reference_cost_usd / c for c in valid_cost if c > 0]
            avg_price_ratio = _geometric_mean(ratios) if ratios else float("nan")
        else:
            avg_price_ratio = float("nan")

        # Tier breakdown: use first non-None from samples
        tier_bd = next((s[8] for s in samples_list if s[8] is not None), None)

        best[key] = PillarScores(
            correctness=avg_correctness,
            token_ratio=avg_token_ratio,
            time_ratio=avg_time_ratio,
            avg_tokens=avg_tokens,
            avg_time=avg_time,
            samples=n,
            price_ratio=avg_price_ratio,
            avg_cost_usd=avg_cost_usd,
            token_suppressed=token_suppressed,
            time_suppressed=time_suppressed,
            tier_breakdown=tier_bd,
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
        return f"{tokens / 1000:.1f}k"
    return f"{tokens:.0f}"


def _fmt_cost_ratio(val: float) -> str:
    """Format a cost ratio value (higher = cheaper)."""
    if math.isinf(val):
        return "FREE"
    return _fmt_ratio(val) + "x"


def _fmt_avg_cost(cost: float) -> str:
    """Format average cost per sample in USD. Shows raw values — no rounding."""
    if math.isnan(cost):
        return "  --"
    if math.isinf(cost):
        return "FREE"
    return f"${cost:.9f}"


def _geometric_mean(vals: list[float]) -> float:
    if not vals:
        return float("nan")
    for v in vals:
        if v <= 0:
            return float("nan")
    log_sum = math.fsum(math.log(v) for v in vals)
    return math.exp(log_sum / len(vals))


# Columns: TASK | CORRECT | TOK_RATIO | TIME_RATIO | TOKENS | TIME | COST_RATIO | AVG COST
_COL_HEADERS = ["CORRECT", "TOK_RATIO", "TIME_RATIO", "TOKENS", "TIME", "COST_RATIO", "AVG COST"]
_COL_KEYS = [
    "correctness",
    "token_ratio",
    "time_ratio",
    "avg_tokens",
    "avg_time",
    "price_ratio",
    "avg_cost_usd",
]
_COL_WIDTHS = [7, 9, 10, 7, 7, 9, 9]


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

    # Cache freshness header — use OpenRouterCache.get_freshness()
    try:
        import datetime

        from bench_cli.pricing.price_cache import OpenRouterCache

        cache = OpenRouterCache()
        freshness = cache.get_freshness()
        if freshness:
            # freshness is ISO string, compute age from cache file mtime
            cp = cache.cache_path
            if cp.exists():
                mtime = datetime.datetime.fromtimestamp(cp.stat().st_mtime)
                age_days = (datetime.datetime.now() - mtime).days
                age_str = f"{age_days}d ago" if age_days > 0 else "today"
                date_str = mtime.strftime("%Y-%m-%d")
                lines.append(f"COST: cached {date_str} ({age_str})")
            else:
                lines.append("COST: no cache")
        else:
            lines.append("COST: no cache")
    except Exception:
        pass
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
        for col_name, col_w in zip(_COL_HEADERS, _COL_WIDTHS, strict=True):
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
                    _fmt_cost_ratio(ps.price_ratio),
                    _fmt_avg_cost(ps.avg_cost_usd),
                ]
                for cell, col_w in zip(cells, _COL_WIDTHS, strict=True):
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
        cr_vals, cost_vals = [], []
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
                if not math.isnan(ps.price_ratio) and ps.price_ratio > 0:
                    cr_vals.append(ps.price_ratio)
                if not math.isnan(ps.avg_cost_usd):
                    cost_vals.append(ps.avg_cost_usd)

        cells = [
            _fmt(sum(c_vals) / len(c_vals)) if c_vals else "  --",
            _fmt_ratio(_geometric_mean(tr_vals)) if tr_vals else "  --",
            _fmt_ratio(_geometric_mean(lr_vals)) if lr_vals else "  --",
            _fmt_tokens(sum(tok_vals) / len(tok_vals)) if tok_vals else "  --",
            _fmt_time(sum(time_vals) / len(time_vals)) if time_vals else "  --",
            _fmt_cost_ratio(_geometric_mean(cr_vals)) if cr_vals else "  --",
            _fmt_avg_cost(sum(cost_vals) / len(cost_vals)) if cost_vals else "  --",
        ]
        for cell, col_w in zip(cells, _COL_WIDTHS, strict=True):
            mean_row += " " + cell.rjust(col_w)
        mean_row += " "
    lines.append(mean_row)

    return "\n".join(lines)


def format_summary(data: CompareData) -> str:
    """3-5 line ranked model summary for default compare output."""
    if not data.tasks or not data.models:
        return "No scored eval logs found."

    from bench_cli.resolver import bare_name

    model_scores: list[tuple[str, float]] = []
    for model in data.models:
        vals = []
        for task in data.tasks:
            ps = data.matrix.get(task, {}).get(model)
            if ps and not math.isnan(ps.correctness):
                vals.append(ps.correctness)
        if vals:
            model_scores.append((model, sum(vals) / len(vals)))

    model_scores.sort(key=lambda x: x[1], reverse=True)

    lines: list[str] = []
    n_tasks = len(data.tasks)
    n_models = len(data.models)
    lines.append(f"{'━' * 3} BENCHMARK SUMMARY ({n_tasks} tasks, {n_models} models) {'━' * 3}")
    lines.append("")
    for i, (model, score) in enumerate(model_scores, 1):
        filled = round(score * 10)
        bar = "●" * filled + "○" * (10 - filled)
        lines.append(f"  #{i}  {bare_name(model):<20s} {score:.0%}  {bar}")
    lines.append("")
    lines.append("  Use -v for per-task breakdown, -vv for full table.")
    return "\n".join(lines)


def format_compact_table(data: CompareData) -> str:
    """Per-task correctness grid for -v output."""
    if not data.tasks or not data.models:
        return "No scored eval logs found."

    from bench_cli.resolver import bare_name

    model_names = [bare_name(m) for m in data.models]
    task_col_w = max(len(t) for t in data.tasks) + 2
    model_col_w = max(max(len(n) for n in model_names), 7)

    lines: list[str] = []
    lines.append(f"{'━' * 3} PER-TASK CORRECTNESS ({len(data.tasks)} tasks) {'━' * 3}")
    lines.append("")

    # Header
    header = " " * task_col_w
    for name in model_names:
        header += name.rjust(model_col_w + 2)
    lines.append(header)

    lines.append("─" * (task_col_w + (model_col_w + 2) * len(model_names)))

    # Rows
    for task in data.tasks:
        row = task.ljust(task_col_w)
        for model in data.models:
            ps = data.matrix.get(task, {}).get(model)
            if ps:
                row += f"  {ps.correctness:.0%}".rjust(model_col_w + 2)
            else:
                row += "  —".rjust(model_col_w + 2)
        lines.append(row)

    # Mean row
    lines.append("─" * (task_col_w + (model_col_w + 2) * len(model_names)))
    mean_row = "MEAN".ljust(task_col_w)
    for model in data.models:
        vals = []
        for task in data.tasks:
            ps = data.matrix.get(task, {}).get(model)
            if ps and not math.isnan(ps.correctness):
                vals.append(ps.correctness)
        avg = sum(vals) / len(vals) if vals else 0.0
        mean_row += f"  {avg:.0%}".rjust(model_col_w + 2)
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
                rows.append(
                    {
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
                        "price_ratio": (
                            round(ps.price_ratio, 4) if not math.isnan(ps.price_ratio) else None
                        ),
                        "avg_cost_usd": (
                            round(ps.avg_cost_usd, 6) if not math.isnan(ps.avg_cost_usd) else None
                        ),
                        "tier_breakdown": ps.tier_breakdown,
                    }
                )
    return json.dumps(rows, indent=2)


def format_tier_breakdown(data: CompareData) -> str | None:
    """Render smart-router tier usage breakdown. Returns None if no tier data."""
    # Collect models that have tier data
    router_models: dict[str, dict[str, dict]] = {}  # model -> task -> tier_breakdown
    for model in data.models:
        for task in data.tasks:
            ps = data.matrix.get(task, {}).get(model)
            if ps and ps.tier_breakdown:
                if model not in router_models:
                    router_models[model] = {}
                router_models[model][task] = ps.tier_breakdown

    if not router_models:
        return None

    lines: list[str] = []
    for model, tasks_tiers in router_models.items():
        model_name = _short_model(model)
        lines.append(f"{'━' * 3} TIER USAGE ({model_name}) {'━' * 3}")
        lines.append("")

        # Aggregate: tier -> count, cost
        tier_counts: dict[str, int] = {}
        tier_costs: dict[str, float] = {}
        tier_models: dict[str, str] = {}
        for task, tb in tasks_tiers.items():
            for tier_name, tier_info in tb.items():
                tier_counts[tier_name] = tier_counts.get(tier_name, 0) + 1
                tier_costs[tier_name] = tier_costs.get(tier_name, 0.0) + tier_info.get("cost_usd", 0.0)
                or_id = tier_info.get("model", "")
                if or_id:
                    tier_models[tier_name] = or_id

        total_tasks = len(tasks_tiers)

        # Summary: tier distribution
        for tier_name in sorted(tier_counts):
            count = tier_counts[tier_name]
            pct = count / total_tasks * 100 if total_tasks else 0
            cost = tier_costs[tier_name]
            or_id = tier_models.get(tier_name, "?")
            # Strip provider prefix for readability
            short_model = or_id.split("/", 1)[-1] if "/" in or_id else or_id
            lines.append(f"  {tier_name:<12} {short_model:<30} {count:>3} tasks ({pct:>5.1f}%)  ${cost:.6f}")
        lines.append("")

        # Per-task mapping
        lines.append("  Per-task:")
        for task in sorted(tasks_tiers):
            tb = tasks_tiers[task]
            # Show the primary tier (first one, or the one with most tokens)
            primary_tier = next(iter(tb))
            primary_info = tb[primary_tier]
            short_model = primary_info.get("model", "?")
            if "/" in short_model:
                short_model = short_model.split("/", 1)[-1]
            lines.append(f"    {task:<30} {primary_tier:<12} {short_model}")
        lines.append("")

    return "\n".join(lines)
