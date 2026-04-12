"""Top-level Click group for the bench CLI."""

import click


@click.group()
@click.version_option(version="0.1.0", prog_name="bench")
def cli() -> None:
    """Bench — local LLM and AI agent evaluation system."""
    pass


# Import and register subcommands so they attach to the group.
# Placed at bottom to avoid circular imports.
from bench_cli.compare import compare
from bench_cli.run import run

cli.add_command(run)
cli.add_command(compare)
