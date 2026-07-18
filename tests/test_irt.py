"""Tests for the IRT engine (SC4, SC5, SC10, SC13)."""

from __future__ import annotations

import pytest


def test_check_pymc_raises_when_missing(monkeypatch):
    """SC13 partial: _check_pymc() raises ImportError with install hint."""
    import builtins
    real_import = builtins.__import__

    def _block_pymc(name, *args, **kwargs):
        if name == "pymc" or name.startswith("pymc."):
            raise ImportError("no pymc")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_pymc)
    # Force reimport
    import importlib
    import bench_cli.irt
    importlib.reload(bench_cli.irt)
    with pytest.raises(ImportError, match="PyMC is required"):
        bench_cli.irt._check_pymc()


def test_outcome_matrix_dataclass():
    """OutcomeMatrix holds the expected fields."""
    from bench_cli.irt.types import OutcomeMatrix

    om = OutcomeMatrix(
        matrix=[[1.0, 0.0], [0.5, 0.5]],
        models=["model-a", "model-b"],
        tasks=["task-1", "task-2"],
        pillars={"task-1": "analysis", "task-2": "execution"},
    )
    assert len(om.models) == 2
    assert len(om.tasks) == 2
    assert om.matrix[0][1] == 0.0


def test_irt_fit_dataclass():
    """IRTFit holds posterior estimates."""
    from bench_cli.irt.types import IRTFit

    fit = IRTFit(
        theta=[0.5, -0.3],
        theta_ci=[(0.1, 0.9), (-0.7, 0.1)],
        a=[1.2, 0.8],
        a_ci=[(0.8, 1.6), (0.4, 1.2)],
        b=[-0.5, 0.3],
        b_ci=[(-1.0, 0.0), (-0.2, 0.8)],
        models=["m1", "m2"],
        tasks=["t1", "t2"],
        pillar=None,
        converged=True,
        n_divergences=0,
    )
    assert fit.converged
    assert len(fit.theta) == 2
