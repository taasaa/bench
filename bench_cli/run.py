"""bench run — discover tasks and execute them via Inspect AI."""

from __future__ import annotations

from inspect_ai import Task, task
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


def _discover_tasks(
    tier: str,
    max_tasks: int | None = None,
    task_filter: str | None = None,
) -> list[str]:
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
    task_filter:
        If set, select only the task whose directory name matches.
        Matches as a suffix (e.g. ``"smoke"`` matches ``"smoke"`` and
        ``"agent_smoke"``).  Use ``--list-tasks`` first to see all names.
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
            if task_filter and task_dir.name != task_filter:
                continue
            task_py = task_dir / "task.py"
            if task_py.is_file():
                specs.append(str(task_py))

    if max_tasks is not None and max_tasks >= 0:
        specs = specs[:max_tasks]

    return specs


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "openai/default"


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
    "--task",
    "task_filter",
    default=None,
    help=(
        "Run only the task whose directory name exactly matches this string. "
        "E.g. --task smoke. "
        "Use --list-tasks to see all available names."
    ),
)
@click.option(
    "--list-tasks",
    "list_tasks",
    is_flag=True,
    default=False,
    help="List all available tasks for the given --tier and exit.",
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
@click.option(
    "--no-compare",
    is_flag=True,
    default=False,
    help="Skip automatic bench compare after eval completes.",
)
@click.option(
    "--one-by-one",
    is_flag=True,
    default=False,
    help=(
        "Run tasks one at a time instead of batching. "
        "Useful for monitoring individual results and logs. "
        "Results are compared after each task finishes."
    ),
)
def run(
    model: str,
    tier: str,
    agent: str | None,
    task_filter: str | None,
    list_tasks: bool,
    max_tasks: int | None,
    log_dir: str,
    no_compare: bool,
    one_by_one: bool,
) -> None:
    """Discover and run evaluation tasks via Inspect AI."""
    # Lazy import so CLI --help stays fast when Inspect is not configured.
    from inspect_ai import eval as inspect_eval

    # 1. Discover task specs.
    if list_tasks:
        specs = _discover_tasks(tier, max_tasks=None, task_filter=None)
        click.echo(f"Tasks available for tier '{tier}':")
        click.echo(f"  (use --tier to filter; default is 'quick')")
        click.echo()
        for spec in specs:
            click.echo(f"  {spec}")
        click.echo()
        click.echo(f"{len(specs)} task(s) found. Run one with --task <name>.")
        return

    specs = _discover_tasks(tier, max_tasks, task_filter)
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

    # 0. Convert spec strings to Task objects with bench_task_dir injected.
    # inspect_eval runs scorers inside an async event loop where stack introspection
    # fails (no task.py frame visible). Passing via Task metadata lets the scorer
    # find verify.sh without any filesystem gymnastics.
    tasks_with_metadata = [_resolve_task(spec) for spec in specs]

    # 3. Execute via Inspect AI's programmatic eval() API.
    #
    # one-by-one mode: eval one task at a time so each result + log can be
    # inspected before moving on.  compare runs after each task.
    # batch mode (default): eval all tasks in one call, compare once at end.
    from bench_cli.compare import format_all_tables, load_compare_data

    if one_by_one:
        click.echo("Running tasks one-by-one (--one-by-one mode)")
        click.echo()
        all_results = []
        for i, spec in enumerate(specs, 1):
            click.echo(f"[{i}/{len(specs)}] Running {spec}")
            result = inspect_eval(tasks=[tasks_with_metadata[i - 1]], model=model, solver=solver, log_dir=log_dir)
            all_results.extend(result)
            click.echo(f"  → {result[0].eval.task}: {result[0].status}")
            if result[0].results and result[0].results.scores:
                s = result[0].results.scores[0]
                mv = s.metrics.get("mean")
                if mv is not None:
                    click.echo(f"    score={mv.value:.3f}")
            if not no_compare:
                data = load_compare_data(log_dir, latest=1)
                if data.tasks:
                    click.echo(format_all_tables(data))
            click.echo()
        results = all_results
    else:
        results = inspect_eval(
            tasks=tasks_with_metadata,
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

    # 5. Auto-compare results (unless suppressed).
    if not no_compare:
        from bench_cli.compare import format_all_tables, load_compare_data

        click.echo("\n── Comparing results ──")
        data = load_compare_data(log_dir, latest=1)
        if data.tasks:
            click.echo(format_all_tables(data))
        else:
            click.echo("  (no scored logs found — run bench compare after eval completes)")


def _resolve_task(spec: str) -> task:
    """Load a task spec (path or name) and inject bench_task_dir into its metadata.

    The verify_sh scorer runs inside Inspect AI's async event loop where stack
    introspection cannot locate task.py — no such frame exists in the async call
    stack. By injecting bench_task_dir into the Task's metadata dict we bypass the
    need for any runtime detection.
    """
    import importlib.util
    import os
    import sys

    spec_path = os.path.abspath(spec)
    task_dir = os.path.dirname(spec_path)

    # Load the module so we can extract the Task object.
    spec_obj = importlib.util.spec_from_file_location(spec_path, spec_path)
    if spec_obj is None or spec_obj.loader is None:
        raise click.ClickException(f"Cannot load task spec: {spec}")
    module = importlib.util.module_from_spec(spec_obj)
    sys.modules[spec_path] = module  # prevent duplicate-load warnings
    spec_obj.loader.exec_module(module)

    # task.py typically defines one @task-decorated function.
    # Use registry_info to identify it (more reliable than introspection).
    task_factory = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if not callable(attr) or attr_name.startswith("_"):
            continue
        try:
            from inspect_ai._util.registry import registry_info
            info = registry_info(attr)
            if info.type == "task":
                task_factory = attr
                break
        except ValueError:
            continue

    if task_factory is None:
        raise click.ClickException(f"No @task-decorated function found in {spec}")

    # Call the factory with CWD set to the task directory so relative dataset
    # paths (e.g. "dataset.json") resolve correctly.
    orig_cwd = os.getcwd()
    try:
        os.chdir(task_dir)
        task_obj = task_factory()
    finally:
        os.chdir(orig_cwd)

    # Clone with bench_task_dir injected.
    metadata = dict(task_obj.metadata or {})
    metadata["bench_task_dir"] = task_dir
    return Task(
        dataset=task_obj.dataset,
        setup=task_obj.setup,
        solver=task_obj.solver,
        cleanup=task_obj.cleanup,
        scorer=task_obj.scorer,
        metrics=task_obj.metrics,
        model=task_obj.model,
        config=task_obj.config,
        model_roles=task_obj.model_roles,
        sandbox=task_obj.sandbox,
        approval=task_obj.approval,
        epochs=task_obj.epochs,
        fail_on_error=task_obj.fail_on_error,
        continue_on_fail=task_obj.continue_on_fail,
        message_limit=task_obj.message_limit,
        token_limit=task_obj.token_limit,
        time_limit=task_obj.time_limit,
        working_limit=task_obj.working_limit,
        cost_limit=task_obj.cost_limit,
        early_stopping=task_obj.early_stopping,
        display_name=task_obj.display_name,
        name=task_obj.name or task_obj.display_name,
        version=task_obj.version,
        metadata=metadata,
        tags=task_obj.tags,
    )


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
