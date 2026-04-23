"""Business logic for bench run -- task discovery, resolution, and price gating."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import click
from inspect_ai import Task

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Map tier names to the subdirectories under tasks/ that they include.
# "quick" runs verification/smoke tests only; "full" runs all eval tasks.
TIER_DIRS: dict[str, list[str]] = {
    "quick": ["verification"],
    "full": ["competence", "execution", "analysis", "universal"],
}

DEFAULT_MODEL = "openai/default"


# ---------------------------------------------------------------------------
# Task discovery
# ---------------------------------------------------------------------------


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
        ``"quick"`` or ``"full"`` -- selects which task directories to scan.
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
      -> ("openai/nvidia-devstral", "mistralai/devstral-2-123b-instruct-2512")

    Without [override]:
        openai/nvidia-nemotron-30b
      -> ("openai/nvidia-nemotron-30b", None)
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
    """Block eval if model has no known price -- before any API calls.

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

    # Try to refresh cache -- this pulls fresh prices from OpenRouter.
    # If OPENROUTER_API_KEY is not set, this raises RuntimeError and we
    # fall back to the existing cache. If cache is stale and refresh fails,
    # we also fall back (stale cache still has useful data if the model was
    # cached before).
    try:
        cache.fetch_and_cache_prices()
    except RuntimeError:
        pass  # no key or refresh failed -- rely on existing cache

    # Check cache for this specific model's price.
    all_prices = cache.get_all_prices()
    if or_id not in all_prices:
        from bench_cli.pricing.price_suggestions import suggest_alternatives

        alternatives = suggest_alternatives(or_id)

        click.echo(f"ERROR: No price found for {model_alias}", err=True)
        click.echo(f"  Resolved OpenRouter ID: {or_id}", err=True)
        click.echo("  This model was not found in the OpenRouter price cache.", err=True)
        click.echo(
            "  The OpenRouter catalog does not have this model -- it may be a private/NIM endpoint.",
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
# Task and agent resolution
# ---------------------------------------------------------------------------


def _resolve_task(spec: str) -> Task:
    """Load a task spec (path or name) and inject bench_task_dir into its metadata.

    The verify_sh scorer runs inside Inspect AI's async event loop where stack
    introspection cannot locate task.py -- no such frame exists in the async call
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
    # Inspect propagates sample.metadata -> state.metadata during scoring,
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
                # Copy fixture files into sample.files so Inspect AI's sandbox
                # init writes them into the Docker container.  This makes fixture
                # files available to agent solvers (which bypass the multishot
                # solver and its read_file/list_directory tools).
                if sample.files is None:
                    sample.files = {}
                sample.files["workspace"] = str(fdir)
        else:
            # No fixture — ensure workspace dir exists so cwd="workspace"
            # in the docker agent solver doesn't fail.  Use a data: URI so
            # Inspect treats it as literal content, not a filesystem path.
            if sample.files is None:
                sample.files = {}
            if "workspace" not in sample.files:
                sample.files["workspace/.gitkeep"] = "data:text/plain,"

    # Merge generous timeout into task config.  Local models behind LiteLLM
    # can be slow -- a single generate() on a complex prompt may take 2-3
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
      local / bare -> local_agent solver (subprocess on host)
      docker / harness -> docker_agent solver (inspect-swe in Docker)
    """
    if agent_mode in ("local", "bare"):
        from bench_cli.solvers.local_agent import local_agent

        return local_agent(agent, bare=(agent_mode == "bare"))

    # docker / harness
    from bench_cli.solvers.docker_agent import docker_agent

    return docker_agent(agent, harness=(agent_mode == "harness"))
