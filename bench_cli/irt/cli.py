"""CLI commands for IRT discrimination analysis."""

from __future__ import annotations

import json
import math
import click


def _fmt_val(val: float, fmt: str = ".3f") -> str:
    """Format val as float representation, or return 'n/a' if nan or inf."""
    if math.isnan(val) or math.isinf(val):
        return "n/a"
    return f"{val:{fmt}}"


def _fmt_json_val(val: float) -> float | str:
    """Format val as float for JSON, or return 'n/a' if nan or inf."""
    if math.isnan(val) or math.isinf(val):
        return "n/a"
    return float(val)


@click.group("irt")
def irt_group():
    """IRT discrimination analysis (requires PyMC)."""
    pass


@irt_group.command("fit")
@click.option("--log-dir", default="logs", help="Directory containing .eval logs.")
@click.option("--pillar", default=None, help="Fit single pillar (default: all).")
@click.option("--n-samples", default=2000, type=int, help="MCMC draw count.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def irt_fit(log_dir: str, pillar: str | None, n_samples: int, as_json: bool) -> None:
    """Fit Bayesian 2PL IRT model on eval logs."""
    from bench_cli.irt import _check_pymc
    try:
        _check_pymc()
    except ImportError as e:
        raise click.ClickException(str(e))

    from bench_cli.irt.fit import fit_2pl, fit_all_pillars
    from bench_cli.irt.utils import build_outcome_matrix

    outcome = build_outcome_matrix(log_dir)
    if not outcome.models:
        click.echo("No model data found in logs.")
        return

    if pillar is not None:
        fits = {pillar: fit_2pl(outcome, pillar=pillar, n_samples=n_samples)}
    else:
        fits = fit_all_pillars(outcome, n_samples=n_samples)
        if "general_fallback" in fits:
            click.echo("WARNING: Convergence failure detected in pillar fitting (Rhat > 1.1).")
            click.echo("Falling back to fitting a single general θ model across all tasks.")
        else:
            fits["general"] = fit_2pl(outcome, n_samples=n_samples)

    if as_json:
        out: dict = {}
        for p, fit in fits.items():
            if fit is None:
                continue
            out[p] = {
                "converged": fit.converged,
                "n_divergences": fit.n_divergences,
                "models": [
                    {"name": m, "theta": _fmt_json_val(fit.theta[i]),
                     "ci_low": _fmt_json_val(fit.theta_ci[i][0]), "ci_high": _fmt_json_val(fit.theta_ci[i][1])}
                    for i, m in enumerate(fit.models)
                ],
            }
        click.echo(json.dumps(out, indent=2))
    else:
        for p, fit in fits.items():
            if fit is None:
                continue
            click.echo(f"\n{'=' * 60}")
            click.echo(f"Pillar: {p}")
            click.echo(f"{'=' * 60}")
            click.echo(f"  Converged: {fit.converged}  Divergences: {fit.n_divergences}")
            click.echo(f"  {'Model':<35} {'θ':>8} {'95% CI':>18}")
            click.echo(f"  {'-' * 35} {'-' * 8} {'-' * 18}")
            ranked = sorted(range(len(fit.models)), key=lambda i: fit.theta[i], reverse=True)
            for i in ranked:
                m = fit.models[i]
                t_str = _fmt_val(fit.theta[i], ".3f")
                lo_str = _fmt_val(fit.theta_ci[i][0], ".3f")
                hi_str = _fmt_val(fit.theta_ci[i][1], ".3f")
                click.echo(f"  {m:<35} {t_str:>8} [{lo_str:>7}, {hi_str:>7}]")


@irt_group.command("item-analysis")
@click.option("--log-dir", default="logs", help="Directory containing .eval logs.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def irt_item_analysis(log_dir: str, as_json: bool) -> None:
    """Report per-task difficulty and discrimination parameters."""
    from bench_cli.irt import _check_pymc
    try:
        _check_pymc()
    except ImportError as e:
        raise click.ClickException(str(e))

    from bench_cli.irt.fit import fit_2pl
    from bench_cli.irt.items import item_analysis
    from bench_cli.irt.utils import build_outcome_matrix

    outcome = build_outcome_matrix(log_dir)
    if not outcome.models:
        click.echo("No model data found in logs.")
        return

    fit = fit_2pl(outcome)
    items = item_analysis(fit)

    if as_json:
        out = [
            {"task": ia.task, "pillar": ia.pillar,
             "a": _fmt_json_val(ia.a),
             "a_ci_low": _fmt_json_val(ia.a_ci[0]),
             "a_ci_high": _fmt_json_val(ia.a_ci[1]),
             "b": _fmt_json_val(ia.b),
             "b_ci_low": _fmt_json_val(ia.b_ci[0]),
             "b_ci_high": _fmt_json_val(ia.b_ci[1]),
             "band": ia.band}
            for ia in items
        ]
        click.echo(json.dumps(out, indent=2))
    else:
        click.echo(f"\n{'Task':<35} {'Pillar':<12} {'a (disc)':>10} {'b (diff)':>10} {'Band':<8}")
        click.echo(f"{'-' * 35} {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 8}")
        for ia in sorted(items, key=lambda x: x.a, reverse=True):
            a_str = _fmt_val(ia.a, ".3f")
            b_str = _fmt_val(ia.b, ".3f")
            click.echo(
                f"{ia.task:<35} {ia.pillar:<12} {a_str:>10} {b_str:>10} {ia.band:<8}"
            )

        high = sum(1 for ia in items if ia.band == "high")
        med = sum(1 for ia in items if ia.band == "medium")
        low = sum(1 for ia in items if ia.band == "low")
        cull = sum(1 for ia in items if ia.band == "cull")
        click.echo(f"\nSummary: {high} high, {med} medium, {low} low, {cull} cull")
