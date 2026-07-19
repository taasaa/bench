"""Bayesian 2PL IRT model fitting via PyMC."""

from __future__ import annotations

from bench_cli.irt import _check_pymc
from bench_cli.irt.types import IRTFit, OutcomeMatrix


def fit_2pl(
    outcome: OutcomeMatrix,
    *,
    pillar: str | None = None,
    n_samples: int = 2000,
    n_chains: int = 2,
    seed: int = 42,
) -> IRTFit:
    """Fit a Bayesian 2PL IRT model.

    Extracts true posterior credible intervals for parameters theta, a, and b.
    """
    _check_pymc()
    import numpy as np
    import pymc as pm

    if pillar is not None and pillar != "general_fallback":
        task_indices = [
            j for j, t in enumerate(outcome.tasks)
            if outcome.pillars.get(t) == pillar
        ]
        tasks = [outcome.tasks[j] for j in task_indices]
        data = np.array([[outcome.matrix[i][j] for j in task_indices]
                         for i in range(len(outcome.models))])
    else:
        tasks = outcome.tasks
        data = np.array(outcome.matrix)

    n_models, n_tasks = data.shape

    # Flatten to 1D observed indices to support missing data in PyMC 5.x naturally
    model_indices = []
    task_indices_1d = []
    observed_y = []
    for i in range(n_models):
        for j in range(n_tasks):
            val = data[i, j]
            if not np.isnan(val):
                model_indices.append(i)
                task_indices_1d.append(j)
                observed_y.append(val)

    with pm.Model() as model:
        theta = pm.Normal("theta", mu=0, sigma=1, shape=n_models)
        a = pm.LogNormal("a", mu=0, sigma=0.5, shape=n_tasks)
        b = pm.Normal("b", mu=0, sigma=2, shape=n_tasks)

        # Logit: a_j * (theta_i - b_j) using 1D indexing arrays
        logit_p = a[task_indices_1d] * (theta[model_indices] - b[task_indices_1d])
        pm.Bernoulli(
            "y_obs",
            logit_p=logit_p,
            observed=observed_y,
        )

        trace = pm.sample(
            draws=n_samples,
            chains=n_chains,
            random_seed=seed,
            progressbar=False,
            return_inferencedata=True,
        )

    theta_post = trace.posterior["theta"].values.reshape(-1, n_models)
    a_post = trace.posterior["a"].values.reshape(-1, n_tasks)
    b_post = trace.posterior["b"].values.reshape(-1, n_tasks)

    theta_mean = theta_post.mean(axis=0).tolist()
    a_mean = a_post.mean(axis=0).tolist()
    b_mean = b_post.mean(axis=0).tolist()

    theta_ci = [
        (float(np.percentile(theta_post[:, i], 2.5)),
         float(np.percentile(theta_post[:, i], 97.5)))
        for i in range(n_models)
    ]
    a_ci = [
        (float(np.percentile(a_post[:, j], 2.5)),
         float(np.percentile(a_post[:, j], 97.5)))
        for j in range(n_tasks)
    ]
    b_ci = [
        (float(np.percentile(b_post[:, j], 2.5)),
         float(np.percentile(b_post[:, j], 97.5)))
        for j in range(n_tasks)
    ]

    import arviz as az
    rhat = az.rhat(trace)
    max_rhat = max(
        float(rhat["theta"].max()),
        float(rhat["a"].max()),
        float(rhat["b"].max()),
    )
    converged = max_rhat <= 1.1
    n_divergences = int(trace.sample_stats["diverging"].sum())

    return IRTFit(
        theta=theta_mean,
        theta_ci=theta_ci,
        a=a_mean,
        a_ci=a_ci,
        b=b_mean,
        b_ci=b_ci,
        models=outcome.models,
        tasks=tasks,
        pillar=pillar,
        converged=converged,
        n_divergences=n_divergences,
    )


_MIN_PILLAR_TASKS = 8


def fit_all_pillars(
    outcome: OutcomeMatrix,
    **kwargs,
) -> dict[str, IRTFit | None]:
    """Fit 2PL per pillar. Skip pillars with < 8 tasks.

    If any pillar fit fails to converge (converged=False), fall back to
    fitting a single general θ on all tasks.
    """
    all_pillars = sorted({p for p in outcome.pillars.values() if p is not None})
    fits: dict[str, IRTFit | None] = {}
    any_convergence_failed = False

    for pillar in all_pillars:
        pillar_task_count = sum(
            1 for t in outcome.tasks if outcome.pillars.get(t) == pillar
        )
        if pillar_task_count < _MIN_PILLAR_TASKS:
            fits[pillar] = None
            continue
        fit = fit_2pl(outcome, pillar=pillar, **kwargs)
        if not fit.converged:
            any_convergence_failed = True
            fits[pillar] = None
        else:
            fits[pillar] = fit

    if any_convergence_failed:
        fits["general_fallback"] = fit_2pl(outcome, pillar="general_fallback", **kwargs)

    return fits
