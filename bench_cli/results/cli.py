"""CLI adapter for bench results -- model card generation."""

from __future__ import annotations

from pathlib import Path

import click

from bench_cli.results.core import generate_all_cards


@click.group("results")
def results() -> None:
    """Generate and manage model result cards."""


@results.command("generate")
@click.option("--log-dir", default="logs", show_default=True, type=click.Path(), help="Eval log directory.")
def generate_cmd(log_dir: str) -> None:
    """Generate model cards from all eval logs."""
    log_path = Path(log_dir)
    if not log_path.is_dir():
        click.echo(f"Error: {log_dir} is not a directory.", err=True)
        raise SystemExit(1)

    click.echo("Generating model cards from eval logs...")
    generated = generate_all_cards(log_path)

    if generated:
        click.echo(f"\nGenerated {len(generated)} model card(s):")
        for p in generated:
            click.echo(f"  {p}")
    else:
        click.echo("No eval logs found. Run some evaluations first.")
