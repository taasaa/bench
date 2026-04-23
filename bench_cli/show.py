"""bench show — universal viewer that dispatches by argument."""

from __future__ import annotations

import math

import click

from bench_cli.resolver import resolve_model


def _bar(score: float, width: int = 10) -> str:
    filled = max(0, min(width, round(score * width)))
    return "●" * filled + "○" * (width - filled)


@click.command("show")
@click.argument("what", nargs=-1)
@click.option("--log-dir", default="logs", hidden=True)
@click.option("-v", "verbosity", count=True, help="Verbosity: -v detail, -vv raw.")
@click.pass_context
def show_cmd(
    ctx: click.Context,
    what: tuple[str, ...],
    log_dir: str,
    verbosity: int,
) -> None:
    """Show information about models, tasks, or eval results."""
    args = list(what)

    if not args:
        from bench_cli.dashboard import render_dashboard

        click.echo(render_dashboard(log_dir))
        return

    subject = " ".join(args)

    # "vs" → redirect to compare
    if " vs " in subject:
        parts = [p.strip() for p in subject.split(" vs ", 1)]
        if len(parts) == 2:
            from bench_cli.compare.cli import compare

            ctx.invoke(
                compare,
                log_dir=log_dir,
                latest=None,
                as_json=False,
                verbosity=max(verbosity, 1),
            )
            return

    # Named keywords
    lower = subject.lower()
    if lower == "models":
        _show_models(log_dir)
        return
    if lower == "tasks":
        from bench_cli.tasks_browser import tasks_cmd

        ctx.invoke(tasks_cmd, pillar=None, show_scores=True, log_dir=log_dir)
        return
    if lower.startswith("tasks "):
        from bench_cli.tasks_browser import tasks_cmd

        ctx.invoke(
            tasks_cmd,
            pillar=subject[6:].strip(),
            show_scores=True,
            log_dir=log_dir,
        )
        return
    if lower == "prices":
        from bench_cli.prices import prices

        ctx.invoke(prices, log_dir=log_dir)
        return
    if lower == "latest":
        _show_latest(log_dir)
        return

    # Try resolving as a model name
    try:
        resolved = resolve_model(subject)
        _show_model(resolved, log_dir, verbosity)
        return
    except click.BadParameter:
        pass

    click.echo(
        f"Unknown subject '{subject}'. "
        "Try: models, tasks, prices, latest, or a model name."
    )


def _show_models(log_dir: str) -> None:
    """Show all evaluated models with scores."""
    from bench_cli.compare.core import load_compare_data
    from bench_cli.resolver import bare_name

    try:
        data = load_compare_data(log_dir)
    except Exception:
        click.echo("No eval data found.")
        return

    if not data.models:
        click.echo("No models found in eval logs.")
        return

    model_scores: list[tuple[str, float]] = []
    for model in data.models:
        vals = []
        for task in data.tasks:
            ps = data.matrix.get(task, {}).get(model)
            if ps and not math.isnan(ps.correctness):
                vals.append(ps.correctness)
        avg = sum(vals) / len(vals) if vals else 0.0
        model_scores.append((model, avg))

    model_scores.sort(key=lambda x: x[1], reverse=True)

    click.echo(f"Evaluated models ({len(data.models)}):\n")
    for i, (model, score) in enumerate(model_scores, 1):
        bar = _bar(score)
        click.echo(f"  #{i}  {bare_name(model):<25s} {score:.0%}  {bar}")


def _show_latest(log_dir: str) -> None:
    """Show the most recent eval run."""
    from bench_cli.dashboard import _extract_recent_runs

    recent = _extract_recent_runs(log_dir, limit=1)
    if not recent:
        click.echo("No eval runs found.")
        return

    r = recent[0]
    click.echo(f"Latest run: {r['date']}  {r['task']}  ({r['id']})")


def _show_model(model: str, log_dir: str, verbosity: int) -> None:
    """Show model card summary."""
    from bench_cli.compare.core import load_compare_data
    from bench_cli.resolver import bare_name

    try:
        data = load_compare_data(log_dir)
    except Exception:
        click.echo(f"No eval data found for {bare_name(model)}.")
        return

    if model not in data.models:
        click.echo(f"No eval results for {bare_name(model)}.")
        return

    # Default: 5-line summary
    vals: list[float] = []
    task_details: list[tuple[str, float]] = []
    for task in data.tasks:
        ps = data.matrix.get(task, {}).get(model)
        if ps and not math.isnan(ps.correctness):
            vals.append(ps.correctness)
            task_details.append((task, ps.correctness))

    if not vals:
        click.echo(f"No scored tasks for {bare_name(model)}.")
        return

    avg = sum(vals) / len(vals)
    click.echo(f"{bare_name(model)} — {avg:.0%} across {len(vals)} tasks  {_bar(avg)}")
    click.echo("")

    # Strengths (top 5) and weaknesses (bottom 5)
    task_details.sort(key=lambda x: x[1], reverse=True)
    strengths = task_details[:5]
    weaknesses = list(reversed(task_details[-5:]))

    click.echo("Strengths:")
    for name, score in strengths:
        click.echo(f"  {name:<28s} {score:.0%}")

    click.echo("")
    click.echo("Weaknesses:")
    for name, score in weaknesses:
        click.echo(f"  {name:<28s} {score:.0%}")

    if verbosity >= 1:
        click.echo("")
        click.echo("Per-task breakdown:")
        for name, score in task_details:
            click.echo(f"  {name:<28s} {score:.0%}  {_bar(score)}")
