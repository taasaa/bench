"""Top-level Click group for the bench CLI."""

from pathlib import Path

import click
from dotenv import load_dotenv

# Load .env from project root (where pyproject.toml lives) before anything else.
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env", override=True)


class _BenchGroup(click.Group):
    """Override main() so Click handles its own errors gracefully (no tracebacks)."""

    def main(self, *args: object, **kwargs: object) -> object:
        kwargs["standalone_mode"] = True
        return super().main(*args, **kwargs)


@click.group(
    cls=_BenchGroup,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(version="0.1.0", prog_name="bench")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Bench — local LLM and AI agent evaluation system."""
    if ctx.invoked_subcommand is None:
        from bench_cli.dashboard import render_dashboard

        click.echo(render_dashboard())


@cli.command("help", hidden=True)
@click.pass_context
def _show_help(ctx: click.Context) -> None:
    """Full command reference."""
    click.echo(cli.get_help(ctx.parent or ctx))


# ── Primary surface ───────────────────────────────────────────────────
from bench_cli.compare import compare
from bench_cli.run import run
from bench_cli.score import score_cmd
from bench_cli.show import show_cmd
from bench_cli.tasks_browser import tasks_cmd

cli.add_command(run)
cli.add_command(show_cmd)
cli.add_command(compare)
cli.add_command(tasks_cmd)
cli.add_command(score_cmd)

# ── Legacy commands (hidden from help) ────────────────────────────────
from bench_cli.baseline import baseline
from bench_cli.config_group import config_group
from bench_cli.discriminative.cli import (
    compare_matrix_cmd,
    compare_profiles,
    recommend,
    task_correlations,
)
from bench_cli.inspect import inspect
from bench_cli.prices import prices
from bench_cli.results import results

for cmd in (
    baseline,
    inspect,
    prices,
    results,
    recommend,
    compare_profiles,
    compare_matrix_cmd,
    task_correlations,
):
    cmd.hidden = True
    cli.add_command(cmd)
cli.add_command(config_group)


if __name__ == "__main__":
    cli(standalone_mode=True)
