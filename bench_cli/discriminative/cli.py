"""Click CLI for bench recommend and bench compare-profiles."""
from __future__ import annotations

from pathlib import Path

import click

from bench_cli.discriminative.pipeline import run_pipeline
from bench_cli.discriminative.profiles import format_profile, compare_subjects
from bench_cli.discriminative.types import PipelineConfig, SubjectID


@click.command("recommend")
@click.option(
    "--model",
    default=None,
    help="Model alias in openai/<alias> format (e.g. qwen-local).",
)
@click.option(
    "--agent",
    "agent_name",
    default=None,
    type=click.Choice(["claude", "codex", "gemini"]),
    help="Agent name for agent eval profile.",
)
@click.option(
    "--agent-mode",
    default="local",
    type=click.Choice(["local", "bare", "docker", "harness"]),
    help="Agent execution mode.",
)
@click.option(
    "--log-dir",
    default="logs",
    type=click.Path(),
    help="Directory containing eval logs.",
)
@click.option(
    "--ci-level",
    default=0.90,
    type=float,
    help="Confidence level for CIs.",
)
def recommend(
    model: str | None,
    agent_name: str | None,
    agent_mode: str,
    log_dir: str,
    ci_level: float,
):
    """Generate a discriminative profile for a model or agent subject.

    Examples:

        bench recommend --model openai/qwen-local

        bench recommend --agent claude --agent-mode docker --model openai/qwen-local
    """
    from bench_cli.discriminative.diagnostics import format_diagnostic_summary

    if model is None and agent_name is None:
        click.echo("Error: must provide --model or --agent", err=True)
        raise SystemExit(1)

    log_path = Path(log_dir)

    if agent_name:
        model_alias = model or "openai/default"
        subject_id = SubjectID(model=model_alias, agent=agent_name, agent_mode=agent_mode)
    else:
        model_alias = model or "openai/default"
        subject_id = SubjectID(model=model_alias)

    try:
        config = PipelineConfig(ci_level=ci_level)
        profile, report = run_pipeline(log_path, subject_id, config)
        click.echo(format_profile(profile))

        if report.non_discriminative_tasks:
            click.echo("")
            click.echo(format_diagnostic_summary(report))

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@click.command("compare-profiles")
@click.argument("subject_a")
@click.argument("subject_b")
@click.option(
    "--log-dir",
    default="logs",
    type=click.Path(),
    help="Directory containing eval logs.",
)
@click.option(
    "--ci-level",
    default=0.90,
    type=float,
    help="Confidence level for CIs.",
)
def compare_profiles(
    subject_a: str,
    subject_b: str,
    log_dir: str,
    ci_level: float,
):
    """Compare two subjects side-by-side.

    Subjects are specified as:

        MODEL:     openai/qwen-local

        AGENT:     claude/openai/qwen-local/local
    """
    log_path = Path(log_dir)
    config = PipelineConfig(ci_level=ci_level)

    sid_a = _parse_subject(subject_a)
    sid_b = _parse_subject(subject_b)

    try:
        profile_a, _ = run_pipeline(log_path, sid_a, config)
        profile_b, _ = run_pipeline(log_path, sid_b, config)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    result = compare_subjects(profile_a, profile_b)
    _print_compare_result(result)


_KNOWN_AGENTS = {"claude", "codex", "gemini"}
_KNOWN_MODES = {"local", "bare", "docker", "harness"}


def _parse_subject(spec: str) -> SubjectID:
    """Parse subject specification.

    Formats:
        openai/qwen-local                    -> model subject
        claude/openai/qwen-local              -> agent subject (no mode)
        claude/openai/qwen-local/local        -> agent subject with mode

    Disambiguation: if the first segment is a known agent name, treat as
    agent.  If the last segment is a known mode, extract it.  Otherwise
    treat the entire spec as a model alias.
    """
    parts = spec.split("/")
    if len(parts) == 1:
        return SubjectID(model=parts[0])
    if parts[0] in _KNOWN_AGENTS:
        if len(parts) >= 3 and parts[-1] in _KNOWN_MODES:
            # agent/model-alias/mode
            model_alias = "/".join(parts[1:-1])
            return SubjectID(model=model_alias, agent=parts[0], agent_mode=parts[-1])
        else:
            # agent/model-alias (no mode)
            model_alias = "/".join(parts[1:])
            return SubjectID(model=model_alias, agent=parts[0])
    # Not a known agent -- entire string is a model alias
    return SubjectID(model=spec)


def _print_compare_result(result) -> None:
    """Print a CompareResult as formatted text."""
    click.echo(
        f"COMPARE: {result.subject_a.display_name} vs {result.subject_b.display_name}"
    )
    click.echo("=" * 60)
    click.echo("")
    click.echo("CLUSTER DELTAS:")
    for delta in result.deltas:
        sig = "[significant]" if delta.significant else "[not significant]"
        sign = "+" if delta.delta >= 0 else ""
        click.echo(f"  {delta.cluster_name:<15} {sign}{delta.delta:.2f}  {sig}")

    if result.cost_delta is not None:
        sign = "+" if result.cost_delta >= 0 else ""
        click.echo(f"\nCOST DELTA: {sign}${abs(result.cost_delta):.4f}/sample")

    if result.latency_delta is not None:
        sign = "+" if result.latency_delta >= 0 else ""
        click.echo(f"LATENCY DELTA: {sign}{abs(result.latency_delta):.1f}s")
