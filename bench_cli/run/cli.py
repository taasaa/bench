"""Click CLI command for bench run."""

from __future__ import annotations

import json as _json
import sys as _sys
import time as _time
from pathlib import Path

import click

from bench_cli.run.core import (
    DEFAULT_MODEL,
    _check_price_gate,
    _completed_tasks,
    _discover_tasks,
    _resolve_agent_solver,
    _resolve_task,
    parse_model_arg,
)


# ---------------------------------------------------------------------------
# Plain-text progress + heartbeat helpers (W1b)
# ---------------------------------------------------------------------------


def _choose_display(no_tui: bool) -> str | None:
    """W1b: return 'plain' when output isn't a TTY or --no-tui is set, else None (Inspect auto)."""
    if no_tui or not _sys.stdout.isatty():
        return "plain"
    return None


def _status_path(log_dir: str, bench_alias: str) -> Path:
    """W1b: path for the per-run status/heartbeat file under <log_dir>/_runs/."""
    d = Path(log_dir) / "_runs"
    d.mkdir(parents=True, exist_ok=True)
    safe = bench_alias.replace("/", "_")
    return d / f"{safe}.{_time.strftime('%H%M%S')}.status.jsonl"


def _append_heartbeat(
    path: Path, *, task: str, status: str, score: float | None, tokens: int
) -> None:
    """Append one JSON object per completed task (one-by-one mode only)."""
    entry = {
        "task": task,
        "status": status,
        "score": score,
        "tokens": tokens,
        "ts": _time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(_json.dumps(entry) + "\n")


def _extract_result_metrics(log) -> tuple[float | None, int]:
    """Extract (score, total_tokens) from an eval log result."""
    score = None
    tokens = 0
    if not (log.results and log.results.scores):
        return score, tokens
    s = log.results.scores[0]
    mv = s.metrics.get("mean")
    if mv is not None:
        score = mv.value
    try:
        for sm in log.samples or []:
            mu = getattr(getattr(sm, "output", None), "usage", None)
            if mu is not None:
                tokens += int(getattr(mu, "input_tokens", 0) or 0) + int(
                    getattr(mu, "output_tokens", 0) or 0
                )
    except Exception:
        tokens = 0
    return score, tokens


def _write_run_summary(path: Path, *, bench_alias: str, results: list) -> None:
    """W1b: write one post-run JSON summary after a batch inspect_eval() returns.

    Batch mode is a single blocking call with no per-task Python loop to hook, so a
    live heartbeat is impossible without Inspect internals. This summary (written
    once at the end) satisfies SC#2's 'batch mode writes a post-run summary'.
    """
    summary = {
        "model": bench_alias,
        "ts": _time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tasks": [
            {
                "task": getattr(getattr(log, "eval", None), "task", None),
                "status": str(log.status),
                "score": (
                    log.results.scores[0].metrics.get("mean").value
                    if log.results
                    and log.results.scores
                    and log.results.scores[0].metrics.get("mean") is not None
                    else None
                ),
            }
            for log in results
        ],
    }
    path.write_text(_json.dumps(summary, indent=2) + "\n", encoding="utf-8")


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
    "--cc-model",
    default=None,
    help=(
        "Override the model passed to Claude Code's --model flag. "
        "Use CCR-style names like 'litellm,thinking' or 'kilocode,opus'. "
        "Only applies to --agent-mode local/bare. "
        "Has no effect on scoring model (use --model for that)."
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
    "--no-resume",
    is_flag=True,
    default=False,
    help=(
        "Force a fully fresh run: re-run every task even if a status='success' "
        "log already exists. Required after a scoring fix, a scorer change, a "
        "verify.sh/judge.md edit, or a reference-cost update (otherwise resume "
        "would silently skip now-stale tasks)."
    ),
)
@click.option(
    "--no-tui",
    is_flag=True,
    default=False,
    help="Force plain-text progress (Inspect display='plain') even when stdout is a TTY.",
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
    help="Run tasks one at a time (shorthand for --concurrency 1). Implies --max-samples 1.",
)
@click.option(
    "--max-samples",
    type=int,
    default=None,
    help=(
        "Maximum samples to run in parallel per task (default 1). "
        "Default 1 is safe for rpm-capped providers (e.g. nvidia NIM): the "
        "programmatic eval() path ignores INSPECT_EVAL_MAX_SAMPLES, so without "
        "this bound every sample in a multi-sample task fires concurrently and "
        "can trigger an upstream 429 retry storm. Override with --max-samples N."
    ),
)
@click.option(
    "--max-retries",
    type=int,
    default=None,
    help=(
        "Maximum retries for an individual model generate() call (HTTP-level). "
        "None (default) passes through to Inspect's provider default. Set small "
        "(e.g. 4) to bound backoff on flaky 429 endpoints so a single sample "
        "fails fast instead of backing off for minutes."
    ),
)
def run(
    model: str,
    tier: str,
    agent: str | None,
    agent_mode: str,
    cc_model: str | None,
    task_filter: str | None,
    list_tasks: bool,
    max_tasks: int | None,
    log_dir: str,
    no_compare: bool,
    no_resume: bool,
    no_tui: bool,
    one_by_one: bool,
    concurrency: int | None,
    sequential: bool,
    max_samples: int | None,
    max_retries: int | None,
) -> None:
    """Discover and run evaluation tasks via Inspect AI."""
    # Lazy import so CLI --help stays fast when Inspect is not configured.
    from inspect_ai import eval as inspect_eval

    if concurrency is not None and concurrency <= 0:
        raise click.BadParameter(
            "--concurrency must be a positive integer (use --sequential for one-at-a-time)",
            param_hint="--concurrency",
        )
    if max_samples is not None and max_samples <= 0:
        raise click.BadParameter(
            "--max-samples must be a positive integer",
            param_hint="--max-samples",
        )

    # Task-level concurrency: --sequential or --concurrency bound how many tasks
    # run at once; otherwise leave it to Inspect's default.
    max_tasks_val: int | None = 1 if sequential else concurrency

    # Sample-level concurrency. --sequential => 1 (fully serial). Otherwise default
    # to 1 (safe for rpm-capped providers; the programmatic eval() path ignores
    # INSPECT_EVAL_MAX_SAMPLES, so this default is the only bound on sample
    # concurrency). Override with --max-samples N.
    max_samples_val: int = 1 if sequential else (max_samples if max_samples is not None else 1)

    # Parse [override] suffix: alias[openrouter_id] lets you supply the OpenRouter
    # price-lookup ID separately from the LiteLLM eval model name.
    bench_alias, or_override = parse_model_arg(model)

    # Persist the override so resolve_openrouter_id() finds it for all callers
    # (price gate, scorer, compare) -- not just the gate.
    if or_override is not None:
        from bench_cli.pricing.litellm_config import save_override

        try:
            save_override(bench_alias, or_override)
            click.echo(f"Override saved: {bench_alias} -> {or_override}")
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            raise SystemExit(1) from None

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

    # Pre-flight price gate -- block if model has no known price.
    _check_price_gate(bench_alias)
    for s in specs:
        click.echo(f"  • {s}")

    # 2. Resolve solver and sandbox.
    solver = None
    eval_sandbox = None
    if agent is not None:
        solver = _resolve_agent_solver(agent, agent_mode, cc_model=cc_model)
        # Docker agent modes require sandbox="docker" on eval() so inspect-swe
        # can inject tools and manage container lifecycle for every task.
        if agent_mode in ("docker", "harness"):
            eval_sandbox = "docker"

    # W1a: cross-run resume (default-on). Skip (model, task) pairs that
    # already have a status='success' log, unless --no-resume. Filtering
    # happens BEFORE task resolution so we don't even load completed tasks.
    run_specs = specs
    if not no_resume:
        spec_dirs = {Path(s).parent.name for s in specs}
        done = _completed_tasks(log_dir, bench_alias, spec_dirs)
        run_specs = [s for s in specs if Path(s).parent.name not in done]
        skipped = len(specs) - len(run_specs)
        if skipped:
            click.echo(
                f"Resume: skipping {skipped} task(s) with existing success log "
                f"(--no-resume to re-run)."
            )
        if not run_specs:
            click.echo(
                "All tasks already have a success log; nothing to do. "
                "Use --no-resume to re-run."
            )
            return

    # 0. Convert spec strings to Task objects with bench_task_dir injected.
    # inspect_eval runs scorers inside an async event loop where stack introspection
    # fails (no task.py frame visible). Passing via Task metadata lets the scorer
    # find verify.sh without any filesystem gymnastics.
    display_mode = _choose_display(no_tui)
    tasks_with_metadata = [
        _resolve_task(spec, agent=agent, agent_mode=agent_mode, cc_model=cc_model)
        for spec in run_specs
    ]

    # 3. Execute via Inspect AI's programmatic eval() API.
    #
    # one-by-one mode: eval one task at a time so each result + log can be
    # inspected before moving on.  compare runs after each task.
    # batch mode (default): eval all tasks in one call, compare once at end.
    if one_by_one:
        click.echo("Running tasks one-by-one (--one-by-one mode)")
        click.echo()
        all_results = []
        heartbeat = _status_path(log_dir, bench_alias)
        for i, spec in enumerate(run_specs, 1):
            click.echo(f"[{i}/{len(run_specs)}] Running {spec}")
            result = inspect_eval(
                tasks=[tasks_with_metadata[i - 1]],
                model=bench_alias,
                solver=solver,
                sandbox=eval_sandbox,
                log_dir=log_dir,
                fail_on_error=0.5,
                retry_on_error=2,
                max_tasks=max_tasks_val,
                max_samples=max_samples_val,
                max_retries=max_retries,
                display=display_mode,
            )
            all_results.extend(result)
            click.echo(f"  -> {result[0].eval.task}: {result[0].status}")
            score, tokens = _extract_result_metrics(result[0])
            if score is not None:
                click.echo(f"    score={score:.3f}")
            _append_heartbeat(
                heartbeat,
                task=Path(spec).parent.name,
                status=str(result[0].status),
                score=score,
                tokens=tokens,
            )
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
            sandbox=eval_sandbox,
            log_dir=log_dir,
            fail_on_error=0.5,
            retry_on_error=2,
            max_tasks=max_tasks_val,
            max_samples=max_samples_val,
            max_retries=max_retries,
            display=display_mode,
        )
        # W1b (SC#2): batch mode has no per-task Python loop to hook, so emit a
        # single post-run summary (not a live heartbeat).
        _write_run_summary(
            _status_path(log_dir, bench_alias).with_suffix(".summary.json"),
            bench_alias=bench_alias,
            results=results,
        )

    # 4. Print summary.
    click.echo("\n-- Results --")
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

        click.echo("\n-- Comparing results --")
        data = load_compare_data(log_dir, latest=1)
        if data.tasks:
            click.echo(format_pillar_table(data))
        else:
            click.echo("  (no scored logs found -- run bench compare after eval completes)")

    # 6. Auto-generate model card.
    try:
        from bench_cli.results import generate_card_for_model

        card_path = generate_card_for_model(
            bench_alias,
            Path(log_dir),
            agent=agent,
            agent_mode=agent_mode,
        )
        if card_path:
            click.echo(f"\n-- Model card updated: {card_path} --")
    except Exception as exc:
        click.echo(f"Warning: model card generation failed: {exc}", err=True)
