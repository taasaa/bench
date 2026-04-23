"""CLI adapter for bench results -- model card generation."""

from __future__ import annotations

from pathlib import Path

import click

from bench_cli.results.core import generate_all_cards, generate_card_for_model


@click.group("results")
def results() -> None:
    """Generate and manage model result cards."""


@results.command("generate")
@click.option(
    "--log-dir",
    default="logs",
    show_default=True,
    type=click.Path(),
    help="Eval log directory.",
)
@click.option(
    "--model",
    default=None,
    help="Generate card for a specific model alias (e.g. openai/qwen-local).",
)
@click.option(
    "--agent",
    type=click.Choice(["claude", "codex", "gemini"]),
    default=None,
    help="Agent name for agent eval cards.",
)
@click.option(
    "--agent-mode",
    type=click.Choice(["local", "bare", "docker", "harness"]),
    default=None,
    help="Agent mode for agent eval cards.",
)
def generate_cmd(
    log_dir: str,
    model: str | None,
    agent: str | None,
    agent_mode: str | None,
) -> None:
    """Generate model cards from all eval logs."""
    log_path = Path(log_dir)
    if not log_path.is_dir():
        click.echo(f"Error: {log_dir} is not a directory.", err=True)
        raise SystemExit(1)

    if model:
        click.echo(f"Generating card for {model}...")
        path = generate_card_for_model(
            model, log_path, agent=agent, agent_mode=agent_mode,
        )
        if path:
            click.echo(f"  {path}")
        else:
            click.echo("No eval logs found for this model/agent combination.")
    else:
        click.echo("Generating model cards from eval logs...")
        generated = generate_all_cards(log_path)

        if generated:
            click.echo(f"\nGenerated {len(generated)} model card(s):")
            for p in generated:
                click.echo(f"  {p}")
        else:
            click.echo("No eval logs found. Run some evaluations first.")
