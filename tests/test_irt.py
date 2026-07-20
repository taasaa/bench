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


import random

def _generate_synthetic_2pl(
    n_models: int = 20,
    n_tasks: int = 30,
    seed: int = 42,
) -> tuple[list[list[float]], list[float], list[float], list[float]]:
    rng = random.Random(seed)
    true_theta = [rng.gauss(0, 1) for _ in range(n_models)]
    true_a = [abs(rng.gauss(1.0, 0.3)) for _ in range(n_tasks)]
    true_b = [rng.gauss(0, 1.5) for _ in range(n_tasks)]

    def sigmoid(x: float) -> float:
        import math
        return 1.0 / (1.0 + math.exp(-x))

    matrix: list[list[float]] = []
    for i in range(n_models):
        row: list[float] = []
        for j in range(n_tasks):
            p = sigmoid(true_a[j] * (true_theta[i] - true_b[j]))
            row.append(1.0 if rng.random() < p else 0.0)
        matrix.append(row)
    return matrix, true_theta, true_a, true_b


@pytest.mark.slow
def test_2pl_recovers_credible_intervals():
    """SC4: 2PL calculates credible intervals for theta, a, and b."""
    pytest.importorskip("pymc")
    from bench_cli.irt.fit import fit_2pl
    from bench_cli.irt.types import OutcomeMatrix

    matrix, _, _, _ = _generate_synthetic_2pl(n_models=10, n_tasks=10, seed=42)
    tasks = [f"t{i}" for i in range(10)]
    models = [f"m{i}" for i in range(10)]
    outcome = OutcomeMatrix(matrix=matrix, models=models, tasks=tasks, pillars={t: "analysis" for t in tasks})

    fit = fit_2pl(outcome, n_samples=200, n_chains=2, seed=42)

    assert len(fit.theta_ci) == 10
    assert len(fit.a_ci) == 10
    assert len(fit.b_ci) == 10
    assert all(ci[0] < ci[1] for ci in fit.theta_ci)
    assert all(ci[0] < ci[1] for ci in fit.a_ci)
    assert all(ci[0] < ci[1] for ci in fit.b_ci)


@pytest.mark.slow
def test_fit_all_pillars_convergence_fallback():
    """Pillar fit non-convergence falls back to general fit."""
    # pytest.importorskip("pymc")
    from bench_cli.irt.fit import fit_all_pillars
    from bench_cli.irt.types import OutcomeMatrix

    from unittest.mock import patch

    tasks = [f"e{i}" for i in range(10)]
    matrix, _, _, _ = _generate_synthetic_2pl(n_models=5, n_tasks=10, seed=99)
    models = [f"m{i}" for i in range(5)]
    outcome = OutcomeMatrix(matrix=matrix, models=models, tasks=tasks, pillars={t: "execution" for t in tasks})

    with patch("bench_cli.irt.fit.fit_2pl") as mock_fit:
        from bench_cli.irt.types import IRTFit
        bad_fit = IRTFit(
            theta=[0.0]*5, theta_ci=[(0,0)]*5, a=[1.0]*10, a_ci=[(0,0)]*10,
            b=[0.0]*10, b_ci=[(0,0)]*10, models=models, tasks=tasks,
            pillar="execution", converged=False, n_divergences=0
        )
        good_general = IRTFit(
            theta=[0.1]*5, theta_ci=[(0,0)]*5, a=[1.1]*10, a_ci=[(0,0)]*10,
            b=[0.1]*10, b_ci=[(0,0)]*10, models=models, tasks=tasks,
            pillar="general_fallback", converged=True, n_divergences=0
        )
        mock_fit.side_effect = [bad_fit, good_general]

        fits = fit_all_pillars(outcome, n_samples=1000, n_chains=2, seed=99)

        assert fits["execution"] is None
        assert fits["general_fallback"] is not None
        assert fits["general_fallback"].pillar == "general_fallback"


def test_fit_all_pillars_skips_small_pillars():
    """fit_all_pillars skips pillars with < 8 tasks (setting their entry in the returned dict to None)."""
    from bench_cli.irt.fit import fit_all_pillars
    from bench_cli.irt.types import OutcomeMatrix, IRTFit
    from unittest.mock import patch

    # 9 tasks for "large", 5 tasks for "small"
    tasks = [f"t{i}" for i in range(14)]
    pillars = {}
    for i in range(9):
        pillars[f"t{i}"] = "large"
    for i in range(9, 14):
        pillars[f"t{i}"] = "small"

    matrix = [[1.0] * 14]
    models = ["m1"]
    outcome = OutcomeMatrix(matrix=matrix, models=models, tasks=tasks, pillars=pillars)

    with patch("bench_cli.irt.fit.fit_2pl") as mock_fit:
        mock_fit.return_value = IRTFit(
            theta=[0.0], theta_ci=[(0, 0)], a=[1.0] * 9, a_ci=[(0, 0)] * 9,
            b=[0.0] * 9, b_ci=[(0, 0)] * 9, models=models, tasks=tasks[:9],
            pillar="large", converged=True, n_divergences=0
        )

        fits = fit_all_pillars(outcome)

        assert fits["large"] is not None
        assert fits["large"].pillar == "large"
        assert "small" in fits
        assert fits["small"] is None
        assert mock_fit.call_count == 1
        mock_fit.assert_called_once_with(outcome, pillar="large")


@pytest.mark.slow
def test_2pl_recovers_synthetic_params():
    """SC4 recovery: 2PL recovers true parameters (theta and b) with high correlation."""
    pytest.importorskip("pymc")
    import numpy as np
    from bench_cli.irt.fit import fit_2pl
    from bench_cli.irt.types import OutcomeMatrix

    n_models = 15
    n_tasks = 20
    matrix, true_theta, _, true_b = _generate_synthetic_2pl(
        n_models=n_models, n_tasks=n_tasks, seed=42
    )
    tasks = [f"t{i}" for i in range(n_tasks)]
    models = [f"m{i}" for i in range(n_models)]
    outcome = OutcomeMatrix(
        matrix=matrix,
        models=models,
        tasks=tasks,
        pillars={t: "analysis" for t in tasks},
    )

    fit = fit_2pl(outcome, n_samples=400, n_chains=2, seed=42)

    corr_theta = float(np.corrcoef(true_theta, fit.theta)[0, 1])
    corr_b = float(np.corrcoef(true_b, fit.b)[0, 1])

    assert corr_theta > 0.6, f"Theta correlation too low: {corr_theta:.4f}"
    assert corr_b > 0.8, f"b correlation too low: {corr_b:.4f}"


def test_item_analysis_extracts_ci():
    """Item analysis maps estimated a_ci and b_ci from IRTFit."""
    from bench_cli.irt.items import item_analysis
    from bench_cli.irt.types import IRTFit

    fit = IRTFit(
        theta=[0.0], theta_ci=[(-0.1, 0.1)],
        a=[1.5], a_ci=[(1.2, 1.8)],
        b=[0.5], b_ci=[(0.2, 0.8)],
        models=["m1"], tasks=["t1"],
        pillar=None, converged=True, n_divergences=0
    )
    items = item_analysis(fit)
    assert items[0].a_ci == (1.2, 1.8)
    assert items[0].b_ci == (0.2, 0.8)


def test_irt_fit_cli_requires_pymc(monkeypatch):
    """bench irt fit fails with clean message when PyMC is missing."""
    import builtins
    real_import = builtins.__import__

    def _block_pymc(name, *args, **kwargs):
        if name == "pymc" or name.startswith("pymc."):
            raise ImportError("no pymc")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_pymc)

    from click.testing import CliRunner
    from bench_cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["irt", "fit"])
    assert result.exit_code != 0
    assert "PyMC is required" in result.output


def test_irt_item_analysis_cli_requires_pymc(monkeypatch):
    """bench irt item-analysis fails with clean message when PyMC is missing."""
    import builtins
    real_import = builtins.__import__

    def _block_pymc(name, *args, **kwargs):
        if name == "pymc" or name.startswith("pymc."):
            raise ImportError("no pymc")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_pymc)

    from click.testing import CliRunner
    from bench_cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["irt", "item-analysis"])
    assert result.exit_code != 0
    assert "PyMC is required" in result.output


def test_fmt_val_helper():
    """_fmt_val and _fmt_json_val format float or return n/a for nan/inf."""
    from bench_cli.irt.cli import _fmt_val, _fmt_json_val
    import math

    assert _fmt_val(1.2346) == "1.235"
    assert _fmt_val(math.nan) == "n/a"
    assert _fmt_val(math.inf) == "n/a"
    assert _fmt_val(-math.inf) == "n/a"

    assert _fmt_json_val(1.2346) == 1.2346
    assert _fmt_json_val(math.nan) == "n/a"
    assert _fmt_json_val(math.inf) == "n/a"
    assert _fmt_json_val(-math.inf) == "n/a"


def test_irt_cli_renders_nan_inf_as_na(monkeypatch):
    """Ensure that nan/inf theta/a/b are rendered as n/a in terminal output."""
    from unittest.mock import patch, MagicMock
    from click.testing import CliRunner
    from bench_cli.main import cli
    from bench_cli.irt.types import IRTFit
    import math

    # Mock pymc check so we don't need pymc installed
    monkeypatch.setattr("bench_cli.irt._check_pymc", lambda: None)

    # 1. Test irt fit
    mock_outcome = MagicMock()
    mock_outcome.models = ["m1"]

    mock_fit = IRTFit(
        theta=[math.nan],
        theta_ci=[(math.nan, math.inf)],
        a=[1.0],
        a_ci=[(1.0, 1.0)],
        b=[1.0],
        b_ci=[(1.0, 1.0)],
        models=["m1"],
        tasks=["t1"],
        pillar="general",
        converged=True,
        n_divergences=0,
    )

    with (
        patch("bench_cli.irt.utils.build_outcome_matrix", return_value=mock_outcome),
        patch("bench_cli.irt.fit.fit_2pl", return_value=mock_fit),
        patch("bench_cli.irt.fit.fit_all_pillars", return_value={"general": mock_fit}),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["irt", "fit"])
        assert result.exit_code == 0
        assert "m1" in result.output
        assert "n/a" in result.output

    # 2. Test irt item-analysis
    from bench_cli.irt.items import ItemAnalysis
    mock_item = ItemAnalysis(
        task="t1",
        pillar="analysis",
        a=math.nan,
        a_ci=(math.nan, math.nan),
        b=math.inf,
        b_ci=(math.inf, math.inf),
        band="low"
    )

    with (
        patch("bench_cli.irt.utils.build_outcome_matrix", return_value=mock_outcome),
        patch("bench_cli.irt.fit.fit_2pl", return_value=mock_fit),
        patch("bench_cli.irt.items.item_analysis", return_value=[mock_item]),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["irt", "item-analysis"])
        assert result.exit_code == 0
        assert "t1" in result.output
        assert "n/a" in result.output


def test_irt_cli_renders_nan_inf_as_na_json(monkeypatch):
    """Ensure that nan/inf theta/a/b are serialized as 'n/a' in JSON output."""
    import json
    from unittest.mock import patch, MagicMock
    from click.testing import CliRunner
    from bench_cli.main import cli
    from bench_cli.irt.types import IRTFit
    import math

    # Mock pymc check so we don't need pymc installed
    monkeypatch.setattr("bench_cli.irt._check_pymc", lambda: None)

    # 1. Test irt fit --json
    mock_outcome = MagicMock()
    mock_outcome.models = ["m1"]

    mock_fit = IRTFit(
        theta=[math.nan],
        theta_ci=[(math.nan, math.inf)],
        a=[1.0],
        a_ci=[(1.0, 1.0)],
        b=[1.0],
        b_ci=[(1.0, 1.0)],
        models=["m1"],
        tasks=["t1"],
        pillar="general",
        converged=True,
        n_divergences=0,
    )

    with (
        patch("bench_cli.irt.utils.build_outcome_matrix", return_value=mock_outcome),
        patch("bench_cli.irt.fit.fit_2pl", return_value=mock_fit),
        patch("bench_cli.irt.fit.fit_all_pillars", return_value={"general": mock_fit}),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["irt", "fit", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["general"]["models"][0]["theta"] == "n/a"
        assert data["general"]["models"][0]["ci_low"] == "n/a"
        assert data["general"]["models"][0]["ci_high"] == "n/a"

    # 2. Test irt item-analysis --json
    from bench_cli.irt.items import ItemAnalysis
    mock_item = ItemAnalysis(
        task="t1",
        pillar="analysis",
        a=math.nan,
        a_ci=(math.nan, math.nan),
        b=math.inf,
        b_ci=(math.inf, math.inf),
        band="low"
    )

    with (
        patch("bench_cli.irt.utils.build_outcome_matrix", return_value=mock_outcome),
        patch("bench_cli.irt.fit.fit_2pl", return_value=mock_fit),
        patch("bench_cli.irt.items.item_analysis", return_value=[mock_item]),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["irt", "item-analysis", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["a"] == "n/a"
        assert data[0]["a_ci_low"] == "n/a"
        assert data[0]["a_ci_high"] == "n/a"
        assert data[0]["b"] == "n/a"
        assert data[0]["b_ci_low"] == "n/a"
        assert data[0]["b_ci_high"] == "n/a"




