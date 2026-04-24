"""Click CLI for bench recommend and bench compare-profiles."""

from __future__ import annotations

from pathlib import Path

import click

from bench_cli.discriminative.correlation import compute_task_correlation, format_correlation_table
from bench_cli.discriminative.harness import format_harness_report, harness_change_report
from bench_cli.discriminative.matrix import compare_matrix, format_matrix
from bench_cli.discriminative.pipeline import run_multi_pipeline, run_pipeline
from bench_cli.discriminative.profiles import compare_subjects, format_profile
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
) -> None:
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
    model_alias = model or "openai/default"
    if agent_name:
        subject_id = SubjectID(model=model_alias, agent=agent_name, agent_mode=agent_mode)
    else:
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
        raise SystemExit(1) from e


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
@click.option(
    "--custom-clusters",
    default=None,
    type=click.Path(exists=True),
    help="Path to custom cluster YAML to merge with base clusters.",
)
def compare_profiles(
    subject_a: str,
    subject_b: str,
    log_dir: str,
    ci_level: float,
    custom_clusters: Path | None,
) -> None:
    """Compare two subjects side-by-side.

    Subjects are specified as:

        MODEL:     openai/qwen-local

        AGENT:     claude/openai/qwen-local/local

    Auto-detects harness change when subject_a and subject_b resolve
    to the same SubjectID (same model, same agent, same agent_mode).
    Triggers HarnessChangeReport instead of CompareResult.
    """
    log_path = Path(log_dir)
    config = PipelineConfig(ci_level=ci_level)
    custom_yaml = Path(custom_clusters) if custom_clusters else None

    sid_a = _parse_subject(subject_a)
    sid_b = _parse_subject(subject_b)

    # Check for harness change: same SubjectID different eval runs
    if _is_harness_change(sid_a, sid_b):
        try:
            profile_a, _ = run_pipeline(log_path, sid_a, config)
            profile_b, _ = run_pipeline(log_path, sid_b, config)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1) from e

        report = harness_change_report(profile_a, profile_b)
        click.echo(format_harness_report(report))
        return

    # Normal comparison
    try:
        if custom_yaml:
            multi_report = run_multi_pipeline(
                log_path,
                [sid_a, sid_b],
                config,
                custom_clusters_yaml=custom_yaml,
            )
            profile_a = multi_report.profiles[0]
            profile_b = multi_report.profiles[1]
        else:
            profile_a, _ = run_pipeline(log_path, sid_a, config)
            profile_b, _ = run_pipeline(log_path, sid_b, config)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from e

    result = compare_subjects(profile_a, profile_b)
    _print_compare_result(result)


@click.command("compare-matrix")
@click.argument("subjects", nargs=-1, required=True)
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
@click.option(
    "--custom-clusters",
    default=None,
    type=click.Path(exists=True),
    help="Path to custom cluster YAML to merge with base clusters.",
)
def compare_matrix_cmd(
    subjects: tuple[str, ...],
    log_dir: str,
    ci_level: float,
    custom_clusters: Path | None,
) -> None:
    """Compare 2+ subjects in a matrix view (per-cluster scores across all subjects).

    Subjects are specified the same way as for compare-profiles:

        bench compare-matrix openai/qwen-local openai/nemotron-3-nano-30b

    Or with agents:

        bench compare-matrix claude/local claude/bare
    """
    log_path = Path(log_dir)
    config = PipelineConfig(ci_level=ci_level)
    custom_yaml = Path(custom_clusters) if custom_clusters else None

    subject_ids: list[SubjectID] = []
    for spec in subjects:
        subject_ids.append(_parse_subject(spec))

    try:
        multi_report = run_multi_pipeline(
            log_path,
            subject_ids,
            config,
            custom_clusters_yaml=custom_yaml,
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from e

    matrix = compare_matrix(multi_report.profiles)
    click.echo(format_matrix(matrix))


@click.command("task-correlations")
@click.option(
    "--log-dir",
    default="logs",
    type=click.Path(),
    help="Directory containing eval logs.",
)
@click.argument("subjects", nargs=-1, required=False)
def task_correlations(
    log_dir: str,
    subjects: tuple[str, ...],
) -> None:
    """Compute pairwise task correlations across subjects.

    Shows task pairs where performance is correlated (Pearson r >= 0.5),
    revealing tasks that likely tap the same underlying capability.

    With no subjects specified, uses all models in the log directory.
    With subjects specified, uses only those subjects.
    """
    log_path = Path(log_dir)
    from bench_cli.discriminative.subject import get_all_log_paths, resolve_subject_from_log

    if subjects:
        subject_ids = [_parse_subject(spec) for spec in subjects]
    else:
        # Discover all subjects in log directory
        all_paths = get_all_log_paths(log_path, None)
        subject_ids = []
        seen: set[str] = set()
        for path in all_paths:
            sid = resolve_subject_from_log(path)
            if sid.display_name not in seen:
                subject_ids.append(sid)
                seen.add(sid.display_name)

    if len(subject_ids) < 2:
        click.echo("Need at least 2 subjects for correlation analysis.", err=True)
        raise SystemExit(1)

    try:
        multi_report = run_multi_pipeline(log_path, subject_ids)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from e

    # Build all_scores dict for correlation
    from inspect_ai.log import read_eval_log

    all_scores: dict[str, dict[str, float]] = {}
    for profile in multi_report.profiles:
        key = profile.subject_id.display_name
        all_scores[key] = {}
        # Re-extract from eval logs
        paths = get_all_log_paths(log_path, profile.subject_id)
        for path in paths:
            try:
                el = read_eval_log(str(path))
            except Exception:
                continue
            if el.status != "success" or not el.results:
                continue
            task_id = el.eval.task
            scores_list = []
            for sample in el.samples:
                c = _get_correctness_for_sample(sample)
                if c is not None:
                    scores_list.append(c)
            if scores_list:
                all_scores[key][task_id] = sum(scores_list) / len(scores_list)

    correlations = compute_task_correlation(all_scores)
    click.echo(format_correlation_table(correlations))


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


def _is_harness_change(a: SubjectID, b: SubjectID) -> bool:
    """Detect harness change: same SubjectID (model + agent + agent_mode)."""
    return a.model == b.model and a.agent == b.agent and a.agent_mode == b.agent_mode


def _get_correctness_for_sample(sample) -> float | None:
    """Extract correctness from sample scores."""
    import math

    if not sample.scores:
        return None
    for key in ("hybrid_scorer", "llm_judge", "verify_sh", "exact", "includes"):
        score = sample.scores.get(key)
        if score is None:
            continue
        val = getattr(score, "value", None)
        if val is None:
            if isinstance(score, (int, float)):
                val = score
        if val is not None:
            try:
                fv = float(val)
            except (ValueError, TypeError):
                continue
            if not math.isnan(fv) and not math.isinf(fv):
                return fv
    return None


def _print_compare_result(result) -> None:
    """Print a CompareResult as formatted text."""
    click.echo(f"COMPARE: {result.subject_a.display_name} vs {result.subject_b.display_name}")
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
