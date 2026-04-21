"""CLI adapter for bench compare."""

from __future__ import annotations

from pathlib import Path

import click

from bench_cli.compare.core import CompareData, load_compare_data, format_pillar_table, format_json


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
