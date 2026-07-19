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


def test_reconcile_identities_basic():
    """Reconcile identities maps aliases to canonical names."""
    from bench_cli.identity import reconcile_identities
    from unittest.mock import patch

    def _mock_resolve(routed, as_name):
        if routed == "openai/thinking":
            return "openai/claude-3-5-sonnet"
        return routed

    with patch("bench_cli.identity.resolve_recorded_name", side_effect=_mock_resolve):
        # When model list is passed, it should reconcile instantly without file scan
        res = reconcile_identities("dummy_dir", models=["openai/thinking", "openai/default"])
        assert res["openai/thinking"] == "openai/claude-3-5-sonnet"
        assert res["openai/default"] == "openai/default"


def _make_compare_data(
    models: list[str],
    tasks: list[str],
    scores: dict[tuple[str, str], float],
) -> CompareData:
    """Helper: build CompareData from a sparse (task, model) -> correctness map."""
    from bench_cli.compare.core import CompareData, PillarScores

    matrix: dict[str, dict[str, PillarScores]] = {}
    for task in tasks:
        matrix[task] = {}
        for model in models:
            if (task, model) in scores:
                matrix[task][model] = PillarScores(
                    correctness=scores[(task, model)],
                    token_ratio=1.0,
                    time_ratio=1.0,
                    avg_tokens=100,
                    avg_time=1.0,
                    samples=1,
                )
    return CompareData(matrix=matrix, tasks=tasks, models=models)


def test_build_outcome_matrix_basic():
    """OutcomeMatrix has correct shape and values from CompareData."""
    from bench_cli.irt.utils import build_outcome_matrix
    from unittest.mock import patch

    data = _make_compare_data(
        models=["m1", "m2"],
        tasks=["t1", "t2"],
        scores={("t1", "m1"): 1.0, ("t1", "m2"): 0.0,
                ("t2", "m1"): 0.5, ("t2", "m2"): 0.75},
    )
    with (
        patch("bench_cli.irt.utils.load_compare_data", return_value=data),
        patch("bench_cli.irt.utils.reconcile_identities", return_value={"m1": "m1", "m2": "m2"}),
        patch("bench_cli.irt.utils._get_pillar_map", return_value={"t1": "analysis", "t2": "execution"}),
    ):
        om = build_outcome_matrix("logs")

    assert om.models == ["m1", "m2"]
    assert om.tasks == ["t1", "t2"]
    assert om.matrix[0] == [1.0, 0.5]
    assert om.matrix[1] == [0.0, 0.75]
    assert om.pillars["t1"] == "analysis"


def test_build_outcome_matrix_reconciles_identities():
    """Different recorded names mapping to the same canonical backing name are merged."""
    from bench_cli.irt.utils import build_outcome_matrix
    from unittest.mock import patch

    data = _make_compare_data(
        models=["m1_alias", "m1_canonical"],
        tasks=["t1"],
        scores={("t1", "m1_alias"): 1.0, ("t1", "m1_canonical"): 0.8},
    )
    identity_map = {"m1_alias": "m1_canonical", "m1_canonical": "m1_canonical"}

    with (
        patch("bench_cli.irt.utils.load_compare_data", return_value=data),
        patch("bench_cli.irt.utils.reconcile_identities", return_value=identity_map),
        patch("bench_cli.irt.utils._get_pillar_map", return_value={"t1": "analysis"}),
    ):
        om = build_outcome_matrix("logs")

    assert om.models == ["m1_canonical"]
    assert om.matrix[0] == [0.9]


def test_build_outcome_matrix_filters_monikers():
    """Moniker aliases (default, thinking, heavy) are excluded."""
    from bench_cli.irt.utils import build_outcome_matrix
    from unittest.mock import patch

    data = _make_compare_data(
        models=["m1", "default", "thinking"],
        tasks=["t1"],
        scores={("t1", "m1"): 0.8, ("t1", "default"): 0.7, ("t1", "thinking"): 0.6},
    )
    with (
        patch("bench_cli.irt.utils.load_compare_data", return_value=data),
        patch("bench_cli.irt.utils.reconcile_identities", return_value={"m1": "m1", "default": "default", "thinking": "thinking"}),
        patch("bench_cli.irt.utils._get_pillar_map", return_value={"t1": "analysis"}),
    ):
        om = build_outcome_matrix("logs", filter_monikers=True)

    assert om.models == ["m1"]
    assert len(om.matrix) == 1




