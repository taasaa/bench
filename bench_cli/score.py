"""bench score — one-number model ranking."""

from __future__ import annotations

import math

import click

from bench_cli.compare.core import CompareData, load_compare_data
from bench_cli.resolver import bare_name, resolve_model


def _bar(score: float, width: int = 10) -> str:
    filled = max(0, min(width, round(score * width)))
    return "●" * filled + "○" * (width - filled)


def _composite_score(ps_list: list) -> float:
    """Compute composite score from PillarScores list."""
    c_vals = [
        p.correctness for p in ps_list
        if not math.isnan(p.correctness)
    ]
    tr_vals = [
        p.token_ratio for p in ps_list
        if not math.isnan(p.token_ratio) and p.token_ratio > 0
    ]
    lr_vals = [
        p.time_ratio for p in ps_list
        if not math.isnan(p.time_ratio) and p.time_ratio > 0
    ]
    pr_vals = [
        p.price_ratio for p in ps_list
        if not math.isnan(p.price_ratio) and p.price_ratio > 0
    ]

    parts = []
    if c_vals:
        parts.append(sum(c_vals) / len(c_vals))
    if tr_vals:
        parts.append(min(1.0, sum(tr_vals) / len(tr_vals)))
    if lr_vals:
        parts.append(min(1.0, sum(lr_vals) / len(lr_vals)))
    if pr_vals:
        parts.append(min(1.0, sum(pr_vals) / len(pr_vals)))

    if not parts:
        return 0.0
    return sum(parts) / len(parts)


def _pillar_avg(data: CompareData, model: str, key: str) -> float:
    """Average a pillar across all tasks for a model."""
    vals = []
    for task in data.tasks:
        ps = data.matrix.get(task, {}).get(model)
        if ps:
            v = getattr(ps, key, None)
            if v is not None and not math.isnan(v) and v > 0:
                vals.append(v)
    if not vals:
        return 0.0
    if key in ("token_ratio", "time_ratio", "price_ratio"):
        return min(1.0, sum(vals) / len(vals))
    return sum(vals) / len(vals)


@click.command("score")
@click.argument("model", required=False)
@click.option("--breakdown", is_flag=True, help="Show per-pillar breakdown for all models.")
@click.option("--log-dir", default="logs", hidden=True)
def score_cmd(model: str | None, breakdown: bool, log_dir: str) -> None:
    """Model ranking by composite score."""
    try:
        data = load_compare_data(log_dir)
    except Exception:
        click.echo("No eval data found.")
        return

    if not data.models:
        click.echo("No models found in eval logs.")
        return

    if model:
        resolved = resolve_model(model)
        _score_single(data, resolved)
    elif breakdown:
        _score_breakdown(data)
    else:
        _score_ranking(data)


def _score_ranking(data: CompareData) -> None:
    """Ranked model list with composite scores."""
    model_scores: list[tuple[str, float]] = []
    for model in data.models:
        ps_list = [
            data.matrix[t][model]
            for t in data.tasks
            if model in data.matrix.get(t, {})
        ]
        if ps_list:
            model_scores.append((model, _composite_score(ps_list)))

    model_scores.sort(key=lambda x: x[1], reverse=True)

    for model, score in model_scores:
        pct = score * 100
        click.echo(f"  {bare_name(model):<25s} {pct:3.0f}  {_bar(score)}")


def _score_single(data: CompareData, model: str) -> None:
    """Per-pillar breakdown for one model."""
    if model not in data.models:
        click.echo(f"No eval results for {bare_name(model)}.")
        return

    ps_list = [
        data.matrix[t][model]
        for t in data.tasks
        if model in data.matrix.get(t, {})
    ]
    if not ps_list:
        click.echo(f"No scored tasks for {bare_name(model)}.")
        return

    composite = _composite_score(ps_list)
    click.echo(f"{bare_name(model)}: {composite * 100:.0f}/100  {_bar(composite)}")
    click.echo("")

    corr = _pillar_avg(data, model, "correctness")
    eff = _pillar_avg(data, model, "token_ratio")
    spd = _pillar_avg(data, model, "time_ratio")
    cost = _pillar_avg(data, model, "price_ratio")

    click.echo(f"  {'correctness':<14s} {corr * 100:3.0f}  {_bar(corr)}")
    click.echo(f"  {'efficiency':<14s} {eff * 100:3.0f}  {_bar(eff)}")
    click.echo(f"  {'speed':<14s} {spd * 100:3.0f}  {_bar(spd)}")
    click.echo(f"  {'cost':<14s} {cost * 100:3.0f}  {_bar(cost)}")


def _score_breakdown(data: CompareData) -> None:
    """Table with composite + per-pillar for all models."""
    model_scores: list[tuple[str, float, float, float, float, float]] = []
    for model in data.models:
        ps_list = [
            data.matrix[t][model]
            for t in data.tasks
            if model in data.matrix.get(t, {})
        ]
        if not ps_list:
            continue
        comp = _composite_score(ps_list)
        corr = _pillar_avg(data, model, "correctness") * 100
        eff = _pillar_avg(data, model, "token_ratio") * 100
        spd = _pillar_avg(data, model, "time_ratio") * 100
        cost = _pillar_avg(data, model, "price_ratio") * 100
        model_scores.append((model, comp * 100, corr, eff, spd, cost))

    model_scores.sort(key=lambda x: x[1], reverse=True)

    click.echo(
        f"  {'model':<25s} {'overall':>7s} "
        f"{'corr':>6s} {'eff':>6s} {'spd':>6s} {'cost':>6s}"
    )
    click.echo("  " + "─" * 58)
    for model, comp, corr, eff, spd, cost in model_scores:
        click.echo(
            f"  {bare_name(model):<25s} {comp:6.0f} "
            f"{corr:6.0f} {eff:6.0f} {spd:6.0f} {cost:6.0f}"
        )
