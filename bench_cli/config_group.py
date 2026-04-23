"""bench config — admin commands for baseline, prices, results."""

from __future__ import annotations

import click

from bench_cli.baseline import baseline
from bench_cli.prices import prices
from bench_cli.results import results


@click.group("config", hidden=True)
def config_group() -> None:
    """Admin commands: baseline, prices, results."""
    pass


config_group.add_command(baseline)
config_group.add_command(prices)
config_group.add_command(results)
