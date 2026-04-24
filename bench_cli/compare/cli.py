"""CLI adapter for bench compare."""

from __future__ import annotations

import click

from bench_cli.compare.core import (
    format_compact_table,
    format_json,
    format_pillar_table,
    format_summary,
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
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
@click.option("-v", "verbosity", count=True, help="Verbosity: -v per-task, -vv full table.")
def compare(log_dir: str, latest: int | None, as_json: bool, verbosity: int) -> None:
    """Compare evaluation results across models with pillar breakdowns."""
    data = load_compare_data(log_dir, latest)

    if as_json:
        click.echo(format_json(data))
    elif verbosity >= 2:
        click.echo(format_pillar_table(data, "BENCHMARK RESULTS"))
    elif verbosity >= 1:
        click.echo(format_compact_table(data))
    else:
        click.echo(format_summary(data))
