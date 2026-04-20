"""bench run — discover tasks and execute them via Inspect AI."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import click
from inspect_ai import Task, task

# ---------------------------------------------------------------------------
# Task discovery
# ---------------------------------------------------------------------------

# Map tier names to the subdirectories under tasks/ that they include.
# "quick" runs verification/smoke tests only; "full" runs all eval tasks.
TIER_DIRS: dict[str, list[str]] = {
    "quick": ["verification"],
    "full": ["competence", "execution", "analysis", "universal"],
}


def _docker_available() -> bool:
    """Check if Docker is running and available."""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@lru_cache(maxsize=128)
def _requires_docker(task_py: Path) -> bool:
    """Heuristic: does task.py declare sandbox='docker'?"""
    try:
        content = task_py.read_text()
    except OSError:
        return False
    return bool(re.search(r'sandbox\s*=\s*["\']docker["\']', content))


def _discover_tasks(
    tier: str,
    max_tasks: int | None = None,
    task_filter: str | None = None,
) -> list[str]:
    """Return Inspect-compatible task spec strings for the given tier.

    Scans the configured subdirectories under ``tasks/`` for ``task.py``
    files and returns them as relative paths that Inspect's ``eval()``
    can resolve (e.g. ``tasks/verification/smoke/task.py``).

    Tasks that require Docker (``sandbox="docker"``) are automatically
    skipped with a warning when Docker is not available.

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

    docker_ok = _docker_available()

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
            if not task_py.is_file():
                continue
            if _requires_docker(task_py) and not docker_ok:
                click.echo(
                    f"  Skipping {task_py} (requires Docker, not available)",
                    err=True,
                )
                continue
            specs.append(str(task_py))

    if max_tasks is not None and max_tasks >= 0:
        specs = specs[:max_tasks]

    return specs


def parse_model_arg(model: str) -> tuple[str, str | None]:
    """Split --model value into (alias, openrouter_override).

    Supports optional [override] suffix:
        openai/nvidia-devstral[mistralai/devstral-2-123b-instruct-2512]
      → ("openai/nvidia-devstral", "mistralai/devstral-2-123b-instruct-2512")

    Without [override]:
        openai/nvidia-nemotron-30b
      → ("openai/nvidia-nemotron-30b", None)
    """
    if "[" in model:
        alias, rest = model.split("[", 1)
        if "]" not in rest:
            raise click.BadParameter(
                f"Invalid --model format: missing closing ']' in {model!r}",
                param_hint="--model",
            )
        or_override = rest.rstrip("]")
        return alias, or_override
    return model, None


# ---------------------------------------------------------------------------
# Pre-flight price gate
# ---------------------------------------------------------------------------

def _check_price_gate(model_alias: str) -> None:
    """Block eval if model has no known price — before any API calls.

    Managed/local models (qwen-local, gemma-*-local, etc.) are exempt always.
    """
    from bench_cli.pricing import OpenRouterCache
    from bench_cli.pricing.litellm_config import is_managed_model, resolve_openrouter_id

    if is_managed_model(model_alias):
        return  # exempt

    or_id = resolve_openrouter_id(model_alias)
    if or_id is None:
        return  # unknown alias, let it fail downstream

    cache = OpenRouterCache()

    # Try to refresh cache — this pulls fresh prices from OpenRouter.
    # If OPENROUTER_API_KEY is not set, this raises RuntimeError and we
    # fall back to the existing cache. If cache is stale and refresh fails,
    # we also fall back (stale cache still has useful data if the model was
    # cached before).
    try:
        cache.fetch_and_cache_prices()
    except RuntimeError:
        pass  # no key or refresh failed — rely on existing cache

    # Check cache for this specific model's price.
    all_prices = cache.get_all_prices()
    if or_id not in all_prices:
        from bench_cli.pricing.price_suggestions import suggest_alternatives

        alternatives = suggest_alternatives(or_id)

        click.echo(f"ERROR: No price found for {model_alias}", err=True)
        click.echo(f"  Resolved OpenRouter ID: {or_id}", err=True)
        click.echo("  This model was not found in the OpenRouter price cache.", err=True)
        click.echo(
            "  The OpenRouter catalog does not have this model — it may be a private/NIM endpoint.",
            err=True,
        )

        if alternatives:
            provider = alternatives[0].split("/")[0] if alternatives else ""
            click.echo(f"\n  Other {provider} models that ARE available:", err=True)
            for alt_id in alternatives:
                alt_price = all_prices.get(alt_id)
                if alt_price:
                    in_ppm = alt_price.input_price * 1e6
                    out_ppm = alt_price.output_price * 1e6
                    click.echo(
                        f"    {alt_id}  (${in_ppm:.4f} / ${out_ppm:.4f} per 1M tokens)",
                        err=True,
                    )
            click.echo(
                f"\n  To use one of these alternatives instead:\n"
                f"    bench run --model {model_alias}[{alternatives[0]}] --tier quick",
                err=True,
            )
            click.echo(
                f"\n  To provide a manual price for {model_alias}:\n"
                f"    bench prices add {model_alias} <input_per_million> <output_per_million>",
                err=True,
            )
        else:
            click.echo(
                f"\n  To provide a manual price for {model_alias}:\n"
                f"    bench prices add {model_alias} <input_per_million> <output_per_million>",
                err=True,
            )

        raise SystemExit(1)


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
    "--agent-mode",
    type=click.Choice(["local", "bare", "docker", "harness"]),
    default="local",
    show_default=True,
    help=(
        "How to run the agent: "
        "local (full harness), bare (no hooks/CLAUDE.md), "
        "docker (pristine in container), harness (Docker + injected instructions)."
    ),
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
@click.option(
    "--concurrency",
    "-j",
    type=int,
    default=None,
    help=(
        "Maximum number of tasks to run concurrently. "
        "Defaults to Inspect's default (unbounded). "
        "Use 1 for fully sequential execution."
    ),
)
@click.option(
    "--sequential",
    is_flag=True,
    default=False,
    help="Run tasks one at a time (shorthand for --concurrency 1).",
)
def run(
    model: str,
    tier: str,
    agent: str | None,
    agent_mode: str,
    task_filter: str | None,
    list_tasks: bool,
    max_tasks: int | None,
    log_dir: str,
    no_compare: bool,
    one_by_one: bool,
    concurrency: int | None,
    sequential: bool,
) -> None:
    """Discover and run evaluation tasks via Inspect AI."""
    # Lazy import so CLI --help stays fast when Inspect is not configured.
    from inspect_ai import eval as inspect_eval

    if concurrency is not None and concurrency <= 0:
        raise click.BadParameter(
            "--concurrency must be a positive integer (use --sequential for one-at-a-time)",
            param_hint="--concurrency",
        )

    if sequential:
        max_tasks_val: int | None = 1
    elif concurrency is not None:
        max_tasks_val = concurrency
    else:
        max_tasks_val = None

    # Parse [override] suffix: alias[openrouter_id] lets you supply the OpenRouter
    # price-lookup ID separately from the LiteLLM eval model name.
    bench_alias, or_override = parse_model_arg(model)

    # Persist the override so resolve_openrouter_id() finds it for all callers
    # (price gate, scorer, compare) — not just the gate.
    if or_override is not None:
        from bench_cli.pricing.litellm_config import save_override

        try:
            save_override(bench_alias, or_override)
            click.echo(f"Override saved: {bench_alias} → {or_override}")
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            raise SystemExit(1)

    # 1. Discover task specs.
    if list_tasks:
        specs = _discover_tasks(tier, max_tasks=None, task_filter=None)
        click.echo(f"Tasks available for tier '{tier}':")
        click.echo("  (use --tier to filter; default is 'quick')")
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

    click.echo(f"Running {len(specs)} task(s) from tier '{tier}' with model '{bench_alias}'.")

    # Pre-flight price gate — block if model has no known price.
    _check_price_gate(bench_alias)
    for s in specs:
        click.echo(f"  • {s}")

    # 2. Resolve solver.
    solver = None
    if agent is not None:
        solver = _resolve_agent_solver(agent, agent_mode)

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
    if one_by_one:
        click.echo("Running tasks one-by-one (--one-by-one mode)")
        click.echo()
        all_results = []
        for i, spec in enumerate(specs, 1):
            click.echo(f"[{i}/{len(specs)}] Running {spec}")
            result = inspect_eval(
                tasks=[tasks_with_metadata[i - 1]],
                model=bench_alias,
                solver=solver,
                log_dir=log_dir,
                fail_on_error=0.5,
                retry_on_error=2,
                max_tasks=max_tasks_val,
            )
            all_results.extend(result)
            click.echo(f"  → {result[0].eval.task}: {result[0].status}")
            if result[0].results and result[0].results.scores:
                s = result[0].results.scores[0]
                mv = s.metrics.get("mean")
                if mv is not None:
                    click.echo(f"    score={mv.value:.3f}")
            if not no_compare:
                from bench_cli.compare import format_pillar_table, load_compare_data

                data = load_compare_data(log_dir, latest=1)
                if data.tasks:
                    click.echo(format_pillar_table(data))
            click.echo()
        results = all_results
    else:
        results = inspect_eval(
            tasks=tasks_with_metadata,
            model=bench_alias,
            solver=solver,
            log_dir=log_dir,
            fail_on_error=0.5,
            retry_on_error=2,
            max_tasks=max_tasks_val,
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
        from bench_cli.compare import format_pillar_table, load_compare_data

        click.echo("\n── Comparing results ──")
        data = load_compare_data(log_dir, latest=1)
        if data.tasks:
            click.echo(format_pillar_table(data))
        else:
            click.echo("  (no scored logs found — run bench compare after eval completes)")

    # 6. Auto-generate model card.
    try:
        from bench_cli.results import generate_card_for_model

        card_path = generate_card_for_model(bench_alias, Path(log_dir))
        if card_path:
            click.echo(f"\n── Model card updated: {card_path} ──")
    except Exception as exc:
        click.echo(f"Warning: model card generation failed: {exc}", err=True)


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

    # Inject bench_task_dir into each sample's metadata (not Task metadata).
    # Inspect propagates sample.metadata → state.metadata during scoring,
    # but Task.metadata does NOT reach state.metadata.
    for sample in task_obj.dataset:
        if sample.metadata is None:
            sample.metadata = {}
        sample.metadata["bench_task_dir"] = task_dir

        # Inject fixture path from dataset.json "fixture" field.
        # The fixture field specifies a scenario_id under fixtures/.
        fixture_id = sample.metadata.get("fixture") if isinstance(sample.metadata, dict) else None
        if fixture_id:
            from bench_cli.fixtures import fixture_dir_for

            fdir = fixture_dir_for(task_dir, str(fixture_id))
            if fdir:
                sample.metadata["fixture_path"] = str(fdir)

    # Merge generous timeout into task config.  Local models behind LiteLLM
    # can be slow — a single generate() on a complex prompt may take 2-3
    # minutes.  Default OpenAI SDK timeout is 600s which is fine, but some
    # proxy configs or model servers impose shorter limits.  Setting
    # attempt_timeout=300 gives the model 5 minutes per attempt before retry.
    from inspect_ai._eval.task.run import GenerateConfig

    orig_config = task_obj.config
    config_overrides: dict = {}
    if orig_config is None or getattr(orig_config, "timeout", None) is None:
        config_overrides["timeout"] = 600
    if orig_config is None or getattr(orig_config, "attempt_timeout", None) is None:
        config_overrides["attempt_timeout"] = 300
    config = GenerateConfig(**config_overrides)

    return Task(
        dataset=task_obj.dataset,
        setup=task_obj.setup,
        solver=task_obj.solver,
        cleanup=task_obj.cleanup,
        scorer=task_obj.scorer,
        metrics=task_obj.metrics,
        model=task_obj.model,
        config=config,
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
        metadata=dict(task_obj.metadata or {}),
        tags=task_obj.tags,
    )


def _resolve_agent_solver(agent: str, agent_mode: str) -> object:
    """Route (agent, mode) to the correct Inspect solver.

    Modes:
      local / bare → local_agent solver (subprocess on host)
      docker / harness → docker_agent solver (inspect-swe in Docker)
    """
    if agent_mode in ("local", "bare"):
        from bench_cli.solvers.local_agent import local_agent

        return local_agent(agent, bare=(agent_mode == "bare"))

    # docker / harness
    from bench_cli.solvers.docker_agent import docker_agent

    return docker_agent(agent, harness=(agent_mode == "harness"))
