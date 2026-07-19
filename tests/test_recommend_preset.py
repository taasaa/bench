"""Tests for the preset router (SC9)."""

from __future__ import annotations

import math
import pytest
from bench_cli.compare.core import CompareData, PillarScores


def _make_cohort() -> CompareData:
    """Synthetic cohort: 5 models, 2 tasks, varying capability and cost."""
    models = ["fast-cheap", "slow-expensive", "balanced-a", "balanced-b", "dominated-worst"]
    tasks = ["t1", "t2"]
    matrix: dict[str, dict[str, PillarScores]] = {}
    for task in tasks:
        matrix[task] = {}

    for t in tasks:
        matrix[t]["fast-cheap"] = PillarScores(
            correctness=0.5, token_ratio=1.0, time_ratio=1.0,
            avg_tokens=50, avg_time=1.0, samples=1,
            avg_cost_usd=0.001,
        )
        matrix[t]["slow-expensive"] = PillarScores(
            correctness=0.9, token_ratio=1.0, time_ratio=1.0,
            avg_tokens=500, avg_time=10.0, samples=1,
            avg_cost_usd=0.05,
        )
        matrix[t]["balanced-a"] = PillarScores(
            correctness=0.75, token_ratio=1.0, time_ratio=1.0,
            avg_tokens=200, avg_time=4.0, samples=1,
            avg_cost_usd=0.01,
        )
        matrix[t]["balanced-b"] = PillarScores(
            correctness=0.7, token_ratio=1.0, time_ratio=1.0,
            avg_tokens=150, avg_time=6.0, samples=1,
            avg_cost_usd=0.005,
        )
        matrix[t]["dominated-worst"] = PillarScores(
            correctness=0.4, token_ratio=1.0, time_ratio=1.0,
            avg_tokens=600, avg_time=12.0, samples=1,
            avg_cost_usd=0.06,
        )

    return CompareData(matrix=matrix, tasks=tasks, models=models)


def test_best_preset_ranks_by_capability():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    result = recommend_preset(data, "best", use_irt=False)
    assert result.preset == "best"
    assert result.models[0].model == "slow-expensive"


def test_cheap_fast_filters_below_median_cost():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    result = recommend_preset(data, "cheap-fast", use_irt=False)
    model_names = [m.model for m in result.models]
    assert "slow-expensive" not in model_names
    assert result.models[0].model == "fast-cheap"


def test_preset_rankings_deterministic():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    r1 = recommend_preset(data, "best", use_irt=False)
    r2 = recommend_preset(data, "best", use_irt=False)
    assert [m.model for m in r1.models] == [m.model for m in r2.models]


def test_different_presets_different_top3():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    best = recommend_preset(data, "best", use_irt=False)
    cheap = recommend_preset(data, "cheap-fast", use_irt=False)
    assert best.models[0].model != cheap.models[0].model


def test_preset_router_uses_theta_when_pymc_available():
    """Preset router uses IRT θ as capability measure when use_irt=True and PyMC is available."""
    from bench_cli.recommend.presets import recommend_preset
    from unittest.mock import patch
    from bench_cli.irt.types import IRTFit

    data = _make_cohort()
    mock_fit = IRTFit(
        theta=[1.5, 0.0, 0.5, 0.1, -1.0],
        theta_ci=[(0,0)]*5, a=[1.0], a_ci=[(0,0)], b=[0.0], b_ci=[(0,0)],
        models=["fast-cheap", "slow-expensive", "balanced-a", "balanced-b", "dominated-worst"],
        tasks=["t1"], pillar=None, converged=True, n_divergences=0
    )

    with patch("bench_cli.irt.fit.fit_2pl", return_value=mock_fit), \
         patch("bench_cli.recommend.presets._has_pymc", return_value=True):
        result = recommend_preset(data, "best", use_irt=True)
        assert result.models[0].model == "fast-cheap"
        assert result.used_irt is True


def test_balanced_preset_populates_dominated_by():
    """balanced preset populates dominated_by list with model names."""
    from bench_cli.recommend.presets import recommend_preset

    data = _make_cohort()
    result = recommend_preset(data, "balanced", use_irt=False)
    dominated = [m for m in result.models if m.model == "dominated-worst"]
    if dominated:
        # dominated-worst is dominated by slow-expensive, balanced-a, balanced-b
        assert len(dominated[0].dominated_by) >= 1
        assert "slow-expensive" in dominated[0].dominated_by


def test_pareto_front_basic():
    from bench_cli.recommend.pareto import compute_pareto_front

    pareto_idx, dominated_by = compute_pareto_front(
        models=["a", "b", "c"],
        capability=[0.9, 0.5, 0.4],
        cost=[0.05, 0.001, 0.06],
        time=[10.0, 1.0, 12.0],
    )
    assert 0 in pareto_idx  # a is Pareto-optimal
    assert 1 in pareto_idx  # b is Pareto-optimal
    assert 2 not in pareto_idx  # c is dominated by a (better cap, lower cost, lower time)


def test_recommend_preset_cli():
    from click.testing import CliRunner
    from unittest.mock import patch
    from bench_cli.main import cli

    runner = CliRunner()

    # We mock load_compare_data and recommend_preset
    with patch("bench_cli.compare.core.load_compare_data") as mock_load, \
         patch("bench_cli.recommend.presets.recommend_preset") as mock_rec:
        
        # Setup mocks
        mock_load.return_value = _make_cohort()
        # Let's import RecommendResult and RankedModel from bench_cli.recommend.presets
        from bench_cli.recommend.presets import RecommendResult, RankedModel
        mock_rec.return_value = RecommendResult(
            preset="balanced",
            used_irt=False,
            models=[
                RankedModel(
                    model="balanced-a", rank=1, capability=0.75, ci=None,
                    cost_per_task=0.01, time_per_task=4.0, on_pareto=True,
                    dominated_by=[]
                )
            ]
        )

        # 1. Run recommend-preset with --preset balanced
        result = runner.invoke(cli, ["recommend-preset", "--preset", "balanced"])
        assert result.exit_code == 0
        assert "balanced-a" in result.output

        # 2. Run with rp alias
        result_alias = runner.invoke(cli, ["rp", "--preset", "balanced"])
        assert result_alias.exit_code == 0
        assert "balanced-a" in result_alias.output

        # 3. Run with --json flag
        result_json = runner.invoke(cli, ["recommend-preset", "--preset", "balanced", "--json"])
        assert result_json.exit_code == 0
        import json
        data = json.loads(result_json.output)
        assert data["preset"] == "balanced"
        assert data["models"][0]["model"] == "balanced-a"

        # Verify arguments passed to recommend_preset
        mock_rec.assert_any_call(mock_load.return_value, "balanced", use_irt=True, fully_evaluated_only=False)

        # 4. Run with --no-use-irt flag
        result_no_irt = runner.invoke(cli, ["recommend-preset", "--preset", "balanced", "--no-use-irt"])
        assert result_no_irt.exit_code == 0
        mock_rec.assert_any_call(mock_load.return_value, "balanced", use_irt=False, fully_evaluated_only=False)


def test_recommend_preset_nan_inf():
    from click.testing import CliRunner
    from unittest.mock import patch
    from bench_cli.main import cli
    from bench_cli.recommend.presets import RecommendResult, RankedModel

    runner = CliRunner()

    with patch("bench_cli.compare.core.load_compare_data") as mock_load, \
         patch("bench_cli.recommend.presets.recommend_preset") as mock_rec:
        
        mock_load.return_value = _make_cohort()
        mock_rec.return_value = RecommendResult(
            preset="best",
            used_irt=True,
            models=[
                RankedModel(
                    model="model-alpha", rank=1, capability=float("nan"), ci=None,
                    cost_per_task=float("nan"), time_per_task=float("nan"), on_pareto=True,
                    dominated_by=[]
                ),
                RankedModel(
                    model="model-beta", rank=2, capability=float("inf"), ci=None,
                    cost_per_task=float("inf"), time_per_task=float("inf"), on_pareto=False,
                    dominated_by=[]
                )
            ]
        )

        # 1. Run recommend-preset and verify tabular stdout outputs "n/a" for nan and inf values
        result = runner.invoke(cli, ["recommend-preset", "--preset", "best"])
        assert result.exit_code == 0
        output = result.output
        
        assert "model-alpha" in output
        assert "model-beta" in output
        assert output.count("n/a") >= 6
        assert "nan" not in output.lower()
        assert "inf" not in output.lower()

        # 2. Check non-IRT rendering (capability as percentages)
        mock_rec.return_value = RecommendResult(
            preset="balanced",
            used_irt=False,
            models=[
                RankedModel(
                    model="model-alpha", rank=1, capability=float("nan"), ci=None,
                    cost_per_task=float("nan"), time_per_task=float("nan"), on_pareto=True,
                    dominated_by=[]
                ),
                RankedModel(
                    model="model-beta", rank=2, capability=float("inf"), ci=None,
                    cost_per_task=float("inf"), time_per_task=float("inf"), on_pareto=False,
                    dominated_by=[]
                )
            ]
        )
        result_no_irt = runner.invoke(cli, ["recommend-preset", "--preset", "balanced", "--no-use-irt"])
        assert result_no_irt.exit_code == 0
        output_no_irt = result_no_irt.output
        assert "model-alpha" in output_no_irt
        assert "model-beta" in output_no_irt
        assert output_no_irt.count("n/a") >= 6
        assert "nan" not in output_no_irt.lower()
        assert "inf" not in output_no_irt.lower()


def test_recommend_preset_fully_evaluated():
    """Test that fully_evaluated_only parameter excludes models with missing task scores."""
    from bench_cli.recommend.presets import recommend_preset
    from click.testing import CliRunner
    from unittest.mock import patch
    from bench_cli.main import cli

    # Create cohort where 'partially-tested' model has a NaN score for task t2
    models = ["fully-tested", "partially-tested"]
    tasks = ["t1", "t2"]
    matrix: dict[str, dict[str, PillarScores]] = {"t1": {}, "t2": {}}

    matrix["t1"]["fully-tested"] = PillarScores(
        correctness=0.8, token_ratio=1.0, time_ratio=1.0,
        avg_tokens=100, avg_time=2.0, samples=1, avg_cost_usd=0.002,
    )
    matrix["t2"]["fully-tested"] = PillarScores(
        correctness=0.8, token_ratio=1.0, time_ratio=1.0,
        avg_tokens=100, avg_time=2.0, samples=1, avg_cost_usd=0.002,
    )

    matrix["t1"]["partially-tested"] = PillarScores(
        correctness=0.9, token_ratio=1.0, time_ratio=1.0,
        avg_tokens=100, avg_time=2.0, samples=1, avg_cost_usd=0.002,
    )
    matrix["t2"]["partially-tested"] = PillarScores(
        correctness=float("nan"), token_ratio=1.0, time_ratio=1.0,
        avg_tokens=100, avg_time=2.0, samples=1, avg_cost_usd=0.002,
    )

    data = CompareData(matrix=matrix, tasks=tasks, models=models)

    # 1. Without fully_evaluated_only, both models should be present
    res_all = recommend_preset(data, "best", use_irt=False, fully_evaluated_only=False)
    assert len(res_all.models) == 2
    assert res_all.models[0].model == "partially-tested"

    # 2. With fully_evaluated_only, 'partially-tested' should be filtered out
    res_filtered = recommend_preset(data, "best", use_irt=False, fully_evaluated_only=True)
    assert len(res_filtered.models) == 1
    assert res_filtered.models[0].model == "fully-tested"

    # 3. Test CLI flag --fully-evaluated
    runner = CliRunner()
    with patch("bench_cli.compare.core.load_compare_data", return_value=data):
        result = runner.invoke(cli, ["recommend-preset", "--preset", "best", "--fully-evaluated"])
        assert result.exit_code == 0
        assert "fully-tested" in result.output
        assert "partially-tested" not in result.output






