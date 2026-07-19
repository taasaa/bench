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
    result = recommend_preset(data, "best")
    assert result.preset == "best"
    assert result.models[0].model == "slow-expensive"


def test_cheap_fast_filters_below_median_cost():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    result = recommend_preset(data, "cheap-fast")
    model_names = [m.model for m in result.models]
    assert "slow-expensive" not in model_names
    assert result.models[0].model == "fast-cheap"


def test_preset_rankings_deterministic():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    r1 = recommend_preset(data, "best")
    r2 = recommend_preset(data, "best")
    assert [m.model for m in r1.models] == [m.model for m in r2.models]


def test_different_presets_different_top3():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    best = recommend_preset(data, "best")
    cheap = recommend_preset(data, "cheap-fast")
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
