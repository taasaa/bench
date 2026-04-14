"""Top-level Click group for the bench CLI."""

from pathlib import Path

import click
from dotenv import load_dotenv

# Load .env from project root (where pyproject.toml lives) before anything else.
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env", override=True)


@click.group()
@click.version_option(version="0.1.0", prog_name="bench")
def cli() -> None:
    """Bench — local LLM and AI agent evaluation system."""
    pass


# Import and register subcommands so they attach to the group.
# Placed at bottom to avoid circular imports.
from bench_cli.baseline import baseline
from bench_cli.compare import compare
from bench_cli.run import run

cli.add_command(run)
cli.add_command(compare)
cli.add_command(baseline)


if __name__ == "__main__":
    cli()
