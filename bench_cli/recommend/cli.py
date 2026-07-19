"""CLI command for preset-based model recommendations."""

from __future__ import annotations

import json
import math
import click


def _fmt_cost(cost: float) -> str:
    if math.isnan(cost) or math.isinf(cost):
        return "n/a"
    return f"${cost:.4f}"


def _fmt_time(t: float) -> str:
    if math.isnan(t) or math.isinf(t):
        return "n/a"
    if t < 60:
        return f"{t:.1f}s"
    return f"{int(t // 60)}m{t % 60:.0f}s"


@click.command("recommend-preset")
@click.option(
    "--preset",
    type=click.Choice(["best", "cheap-fast", "balanced"]),
    required=True,
    help="Recommendation preset.",
)
@click.option("--log-dir", default="logs", help="Directory containing .eval logs.")
@click.option(
    "--use-irt/--no-use-irt",
    default=True,
    help="Use θ from IRT fit as capability measure if PyMC is available; else pass@1.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option(
    "--fully-evaluated/--no-fully-evaluated",
    default=False,
    help="Only include models that have successfully completed all tasks in the cohort.",
)
def recommend_preset_cmd(
    preset: str, log_dir: str, use_irt: bool, as_json: bool, fully_evaluated: bool
) -> None:
    """Rank models by use-case preset."""
    from bench_cli.compare.core import load_compare_data
    from bench_cli.recommend.presets import recommend_preset

    data = load_compare_data(log_dir)
    if not data.models:
        click.echo("No model data found in logs.")
        return

    result = recommend_preset(
        data, preset, use_irt=use_irt, fully_evaluated_only=fully_evaluated
    )

    if not result.models:
        click.echo(f"No models match the '{preset}' preset criteria.")
        return

    if as_json:
        out = {
            "preset": result.preset,
            "used_irt": result.used_irt,
            "models": [
                {
                    "rank": m.rank,
                    "model": m.model,
                    "capability": m.capability,
                    "cost_per_task": m.cost_per_task,
                    "time_per_task": m.time_per_task,
                    "on_pareto": m.on_pareto,
                    "dominated_by": m.dominated_by,
                }
                for m in result.models
            ],
        }
        click.echo(json.dumps(out, indent=2))
    else:
        cap_header = "θ" if result.used_irt else "Cap"

        click.echo(f"\nPreset: {preset}")
        click.echo(f"{'#':>3}  {'Model':<35} {cap_header:>6} {'Cost/task':>10} {'Time/task':>10} {'Pareto':>7}")
        click.echo(f"{'---':>3}  {'-' * 35} {'-' * 6} {'-' * 10} {'-' * 10} {'-' * 7}")
        for m in result.models:
            pareto_mark = "  ★" if m.on_pareto else ""
            if math.isnan(m.capability) or math.isinf(m.capability):
                cap_val = "n/a"
            else:
                cap_val = f"{m.capability:.3f}" if result.used_irt else f"{m.capability:.1%}"
            click.echo(
                f"{m.rank:>3}  {m.model:<35} {cap_val:>6} "
                f"{_fmt_cost(m.cost_per_task):>10} {_fmt_time(m.time_per_task):>10}"
                f"{pareto_mark:>7}"
            )
