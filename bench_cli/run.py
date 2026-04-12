"""bench run — discover tasks and execute them via Inspect AI."""

from __future__ import annotations

from pathlib import Path

import click

# ---------------------------------------------------------------------------
# Task discovery
# ---------------------------------------------------------------------------

# Map tier names to the subdirectories under tasks/ that they include.
# "quick" runs verification/smoke tests only; "full" runs all eval tasks.
TIER_DIRS: dict[str, list[str]] = {
    "quick": ["verification"],
    "full": ["competence", "execution", "analysis"],
}


def _discover_tasks(tier: str, max_tasks: int | None = None) -> list[str]:
    """Return Inspect-compatible task spec strings for the given tier.

    Scans the configured subdirectories under ``tasks/`` for ``task.py``
    files and returns them as relative paths that Inspect's ``eval()``
    can resolve (e.g. ``tasks/verification/smoke/task.py``).

    Parameters
    ----------
    tier:
        ``"quick"`` or ``"full"`` — selects which task directories to scan.
    max_tasks:
        If set, cap the returned list to this many entries.
    """
    tasks_root = Path("tasks")
    dirs = TIER_DIRS.get(tier)
    if dirs is None:
        raise click.BadParameter(f"Unknown tier {tier!r}", param_hint="--tier")

    specs: list[str] = []
    for subdir in sorted(dirs):
        # Each subdir contains task directories (e.g. tasks/verification/smoke/).
        task_parent = tasks_root / subdir
        if not task_parent.is_dir():
            continue
        for task_dir in sorted(task_parent.iterdir()):
            task_py = task_dir / "task.py"
            if task_py.is_file():
                specs.append(str(task_py))

    if max_tasks is not None and max_tasks >= 0:
        specs = specs[:max_tasks]

    return specs


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "openai/rut-small"


@click.command()
@click.option(
    "--model",
    default=DEFAULT_MODEL,
    show_default=True,
    help="Model in Inspect format (provider/alias).",
)
@click.option(
    "--tier",
    type=click.Choice(["quick", "full"]),
    default="quick",
    show_default=True,
    help="Task tier: quick (verification) or full (all eval tasks).",
)
@click.option(
    "--agent",
    type=click.Choice(["claude", "codex", "gemini"]),
    default=None,
    help="Agent solver. Omit for model-only eval (generate()).",
)
@click.option(
    "--max-tasks",
    type=int,
    default=None,
    help="Cap on number of tasks to run.",
)
@click.option(
    "--log-dir",
    default="logs",
    show_default=True,
    type=click.Path(),
    help="Directory for EvalLog output.",
)
def run(
    model: str,
    tier: str,
    agent: str | None,
    max_tasks: int | None,
    log_dir: str,
) -> None:
    """Discover and run evaluation tasks via Inspect AI."""
    # Lazy import so CLI --help stays fast when Inspect is not configured.
    from inspect_ai import eval as inspect_eval

    # 1. Discover task specs.
    specs = _discover_tasks(tier, max_tasks)
    if not specs:
        click.echo(f"No tasks found for tier {tier!r}.", err=True)
        raise SystemExit(1)

    click.echo(f"Running {len(specs)} task(s) from tier '{tier}' with model '{model}'.")
    for s in specs:
        click.echo(f"  • {s}")

    # 2. Resolve solver.
    solver = None
    if agent is not None:
        solver = _resolve_agent_solver(agent)

    # 3. Execute via Inspect AI's programmatic eval() API.
    results = inspect_eval(
        tasks=specs,
        model=model,
        solver=solver,
        log_dir=log_dir,
    )

    # 4. Print summary.
    click.echo("\n── Results ──")
    for log in results:
        status = log.status
        name = log.eval.task
        score = ""
        if log.results and log.results.scores:
            # Show the first (primary) score's mean.
            s = log.results.scores[0]
            mean_val = s.metrics.get("mean", None)
            if mean_val is not None:
                score = f"  score={mean_val.value:.3f}"
        click.echo(f"  {name}: {status}{score}")

    # Exit with non-zero if any task errored.
    if any(log.status == "error" for log in results):
        raise SystemExit(1)


def _resolve_agent_solver(agent: str) -> None:
    """Map agent name to an inspect-swe solver instance."""
    try:
        from inspect_swe import claude_code, codex_cli, gemini_cli  # type: ignore[import-untyped]
    except ImportError as exc:
        raise click.ClickException(
            "Agent eval requires the 'inspect-swe' package. "
            "Install with: pip install 'bench[agent]'"
        ) from exc

    solvers = {
        "claude": claude_code,
        "codex": codex_cli,
        "gemini": gemini_cli,
    }
    factory = solvers.get(agent)
    if factory is None:
        raise click.BadParameter(f"Unknown agent {agent!r}", param_hint="--agent")
    return factory()
