"""CLI commands for IRT discrimination analysis."""

from __future__ import annotations

import json
import click


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
    _check_pymc()

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
                    {"name": m, "theta": fit.theta[i],
                     "ci_low": fit.theta_ci[i][0], "ci_high": fit.theta_ci[i][1]}
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
                t = fit.theta[i]
                lo, hi = fit.theta_ci[i]
                click.echo(f"  {m:<35} {t:>8.3f} [{lo:>7.3f}, {hi:>7.3f}]")


@irt_group.command("item-analysis")
@click.option("--log-dir", default="logs", help="Directory containing .eval logs.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def irt_item_analysis(log_dir: str, as_json: bool) -> None:
    """Report per-task difficulty and discrimination parameters."""
    from bench_cli.irt import _check_pymc
    _check_pymc()

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
             "a": ia.a, "a_ci_low": ia.a_ci[0], "a_ci_high": ia.a_ci[1],
             "b": ia.b, "b_ci_low": ia.b_ci[0], "b_ci_high": ia.b_ci[1],
             "band": ia.band}
            for ia in items
        ]
        click.echo(json.dumps(out, indent=2))
    else:
        click.echo(f"\n{'Task':<35} {'Pillar':<12} {'a (disc)':>10} {'b (diff)':>10} {'Band':<8}")
        click.echo(f"{'-' * 35} {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 8}")
        for ia in sorted(items, key=lambda x: x.a, reverse=True):
            click.echo(
                f"{ia.task:<35} {ia.pillar:<12} {ia.a:>10.3f} {ia.b:>10.3f} {ia.band:<8}"
            )

        high = sum(1 for ia in items if ia.band == "high")
        med = sum(1 for ia in items if ia.band == "medium")
        low = sum(1 for ia in items if ia.band == "low")
        cull = sum(1 for ia in items if ia.band == "cull")
        click.echo(f"\nSummary: {high} high, {med} medium, {low} low, {cull} cull")
