"""CLI adapter for bench compare."""

from __future__ import annotations

import click

from bench_cli.compare.core import (
    format_compact_table,
    format_json,
    format_pillar_table,
    format_summary,
    format_tier_breakdown,
    load_compare_data,
)


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
    "--min-tasks",
    type=int,
    default=34,
    show_default=True,
    help="Models with fewer than N scored tasks are excluded from the ranked "
         "leaderboard (partial evals never rank against full evals).",
)
@click.option(
    "--show-partial/--no-show-partial",
    default=False,
    show_default=True,
    help="When set, list excluded partial-eval models in a separate footer block.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
@click.option(
    "--legacy-weighted/--no-legacy-weighted",
    default=False,
    show_default=True,
    help="Use deprecated 0.5/0.2/0.15/0.15 weighted blend. "
         "Default is capability-only ranking (pass@1 mean).",
)
@click.option(
    "--no-ci",
    is_flag=True,
    default=False,
    help="Suppress bootstrap CI computation and rendering (faster).",
)
@click.option("-v", "verbosity", count=True, help="Verbosity: -v per-task, -vv full table.")
def compare(
    log_dir: str,
    latest: int | None,
    min_tasks: int,
    show_partial: bool,
    as_json: bool,
    verbosity: int,
    legacy_weighted: bool,
    no_ci: bool,
) -> None:
    """Compare evaluation results across models with pillar breakdowns."""
    data = load_compare_data(log_dir, latest)
    include_ci = not no_ci

    if as_json:
        click.echo(
            format_json(
                data, legacy_weighted=legacy_weighted, include_ci=include_ci
            )
        )
    elif verbosity >= 2:
        click.echo(
            format_pillar_table(
                data,
                "BENCHMARK RESULTS",
                legacy_weighted=legacy_weighted,
                include_ci=include_ci,
            )
        )
    elif verbosity >= 1:
        click.echo(
            format_compact_table(
                data,
                min_tasks=min_tasks,
                legacy_weighted=legacy_weighted,
                include_ci=include_ci,
            )
        )
    else:
        click.echo(
            format_summary(
                data,
                min_tasks=min_tasks,
                show_partial=show_partial,
                legacy_weighted=legacy_weighted,
                include_ci=include_ci,
            )
        )

    # Show tier breakdown for smart-router models (all verbosity levels)
    tier_output = format_tier_breakdown(data)
    if tier_output:
        click.echo()
        click.echo(tier_output)
