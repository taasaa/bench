"""bench baseline — record and list baseline eval results.

Usage:
  bench baseline record --model sonnet-3-5
  bench baseline list
  bench baseline record --model sonnet-3-5 --force
  bench baseline record --model sonnet-3-5 --correctness-threshold 0.6
"""

from __future__ import annotations

import time

import click

from scorers.baseline_store import (
    BASELINES_DIR,
    CORRECTNESS_GATE_DEFAULT,
    BaselineStore,
)


@click.group()
def baseline() -> None:
    """Record and manage baseline eval results for ratio scoring."""
    pass


@baseline.command()
@click.option(
    "--model",
    required=True,
    help="Model ID to use for baseline run.",
)
@click.option(
    "--tier",
    type=click.Choice(["quick", "full"]),
    default="full",
    help="Task tier to run for baseline.",
)
@click.option(
    "--correctness-threshold",
    type=float,
    default=CORRECTNESS_GATE_DEFAULT,
    show_default=True,
    help="Minimum correctness score required for baseline to be eligible as reference.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force record even if correctness is below threshold.",
)
def record(
    model: str,
    tier: str,
    correctness_threshold: float,
    force: bool,
) -> None:
    """Run eval and record baseline results for the specified model."""
    from inspect_ai import eval as inspect_eval

    click.echo(f"Recording baseline for model: {model} (tier: {tier})")

    # Discover tasks
    from bench_cli.run import _discover_tasks, _resolve_task

    specs = _discover_tasks(tier, max_tasks=None, task_filter=None)
    if not specs:
        click.echo("No tasks found.", err=True)
        raise SystemExit(1)

    click.echo(f"Running {len(specs)} tasks for baseline...")

    # Resolve tasks with metadata
    tasks_with_metadata = [_resolve_task(spec) for spec in specs]

    # Run eval and measure wall time
    start = time.monotonic()
    results = inspect_eval(
        tasks=tasks_with_metadata,
        model=model,
        log_dir=BASELINES_DIR,
    )
    wall_time = time.monotonic() - start

    store = BaselineStore(BASELINES_DIR)
    recorded = 0

    for result in results:
        task_id = result.eval.task
        eval_correctness: float | None = None

        if result.results and result.results.scores:
            for score in result.results.scores:
                # Look for correctness scorer
                m = score.metrics.get("mean")
                if m is not None:
                    eval_correctness = float(m.value)
                    break

        if eval_correctness is None:
            click.echo(f"  ⚠ {task_id}: no correctness score, skipping")
            continue

        # Compute average tokens from samples
        total_tokens = 0
        output_tokens = 0
        input_tokens = 0
        tool_call_count = 0
        latency_sum = 0.0
        sample_count = 0

        if result.samples:
            for sample in result.samples:
                if sample.model_usage:
                    total_tokens += sample.model_usage.total_tokens or 0
                    output_tokens += sample.model_usage.output_tokens or 0
                    input_tokens += sample.model_usage.input_tokens or 0
                tool_call_count += len(
                    [m for m in sample.messages if getattr(m, "type", None) == "tool"]
                )
                if sample.working_time:
                    latency_sum += sample.working_time
                sample_count += 1

        avg_tokens = total_tokens // max(sample_count, 1)
        avg_output = output_tokens // max(sample_count, 1)
        avg_input = input_tokens // max(sample_count, 1)
        avg_latency = latency_sum / max(sample_count, 1) if sample_count else None

        baseline = store.record(
            task_id=task_id,
            model_id=model,
            correctness=eval_correctness,
            total_tokens=avg_tokens,
            input_tokens=avg_input,
            output_tokens=avg_output,
            latency_seconds=avg_latency,
            tool_call_count=tool_call_count // max(sample_count, 1),
            correctness_gate=1.0 if force else correctness_threshold,
        )

        status = "✓" if baseline.valid_for_reference else "✗"
        click.echo(
            f"  {status} {task_id}: correctness={eval_correctness:.3f}, "
            f"tokens={avg_output} out / {avg_tokens} total, "
            f"latency={avg_latency:.1f}s" if avg_latency else ""
        )
        recorded += 1

    click.echo(f"\nRecorded {recorded} baselines in {wall_time:.1f}s")
    click.echo(f"Baseline store: {BASELINES_DIR}/")


@baseline.command("list")
def list_baselines() -> None:
    """List all stored baselines with validity status."""
    store = BaselineStore(BASELINES_DIR)
    baselines = store.list_all()

    if not baselines:
        click.echo("No baselines recorded yet.")
        click.echo("Run: bench baseline record --model <model>")
        return

    # Group by task
    by_task: dict[str, list] = {}
    for b in baselines:
        by_task.setdefault(b.task_id, []).append(b)

    click.echo(f"Baseline store: {BASELINES_DIR}/\n")
    for task_id in sorted(by_task):
        click.echo(f"{task_id}:")
        for b in sorted(by_task[task_id], key=lambda x: x.model_id):
            status = "✓ valid" if b.valid_for_reference else "✗ invalid (correctness < gate)"
            click.echo(
                f"  {b.model_id}: {status}\n"
                f"    correctness={b.correctness:.3f}, "
                f"tokens={b.output_tokens or '?'} out / {b.total_tokens} total, "
                f"latency={b.latency_seconds:.1f}s, "
                f"run_at={b.run_at[:10]}"
            )
