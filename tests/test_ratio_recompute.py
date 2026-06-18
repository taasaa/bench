"""Tests for scorers.ratio_recompute — the shared ratio math for compare + results.

These tests guard the single-source-of-truth invariant: both display paths
(bench_cli.compare and bench_cli.results) MUST resolve to the same functions
here, so the two paths cannot drift and silently disagree (which is what
stale-ified the m3 card after the m2.7 -> m3 cost re-baseline).
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest

from scorers import ratio_recompute as rr
from scorers.ratio_recompute import (
    geometric_mean,
    recompute_price_ratio,
    recompute_time_ratio,
    recompute_token_ratio,
)

FIXTURE = Path(__file__).parent / "fixtures" / "eval-logs" / "sample_success.eval"


# ---------------------------------------------------------------------------
# geometric_mean
# ---------------------------------------------------------------------------


class TestGeometricMean:
    def test_basic(self):
        assert geometric_mean([2.0, 8.0]) == pytest.approx(4.0)

    def test_single(self):
        assert geometric_mean([5.0]) == pytest.approx(5.0)

    def test_empty_is_nan(self):
        assert math.isnan(geometric_mean([]))

    def test_nonpositive_is_nan(self):
        assert math.isnan(geometric_mean([2.0, 0.0]))
        assert math.isnan(geometric_mean([2.0, -1.0]))

    def test_identical_to_log_formula(self):
        vals = [1.5, 3.0, 0.7, 12.0]
        expected = math.exp(sum(math.log(v) for v in vals) / len(vals))
        assert geometric_mean(vals) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# recompute_token_ratio / recompute_time_ratio (W3a, ratio-of-means)
# ---------------------------------------------------------------------------


class TestRecomputeTokenTimeRatio:
    def test_token_budget_tier(self, tmp_path, monkeypatch):
        """No reference model -> Tier-2 task_budget.output_tokens wins."""
        from scorers import reference_model as rm
        from scorers.task_budgets import get_task_budget

        monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")  # none registered
        budget = get_task_budget("add_tests")  # output_tokens=508
        # ref 508 / actual 1016 = 0.5
        assert recompute_token_ratio(None, "add_tests", 1016.0, budget) == 0.5

    def test_time_budget_tier(self, tmp_path, monkeypatch):
        from scorers import reference_model as rm
        from scorers.task_budgets import get_task_budget

        monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")
        budget = get_task_budget("add_tests")  # latency_seconds=17.0
        assert recompute_time_ratio(None, "add_tests", 34.0, budget) == pytest.approx(0.5)

    def test_budget_defaults_to_get_task_budget(self, tmp_path, monkeypatch):
        """Omitting budget resolves it internally (results' call style)."""
        from scorers import reference_model as rm

        monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")
        # add_tests output_tokens=508; 508/1016 = 0.5
        assert recompute_token_ratio(None, "add_tests", 1016.0) == 0.5

    def test_reference_baseline_wins_over_budget(self, tmp_path, monkeypatch):
        """A registered Tier-1 baseline overrides Tier-2 budget for ALL subjects."""
        from scorers import reference_model as rm
        from scorers.baseline_store import Baseline, BaselineStore
        from scorers.task_budgets import get_task_budget

        monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")
        rm.set_reference_model_id("openai/minimax-m3")
        store = BaselineStore(str(tmp_path / "baselines"))
        store.save(
            Baseline(
                task_id="add_tests",
                model_id="openai/minimax-m3",
                run_at="x",
                correctness=0.9,
                valid_for_reference=True,
                total_tokens=10,
                output_tokens=200,
            ),
            "add_tests",
            "openai/minimax-m3",
        )
        budget = get_task_budget("add_tests")  # output_tokens=508, must NOT win
        # 200 / 1016 (not 508 / 1016) — proves the reference baseline is used
        assert recompute_token_ratio(store, "add_tests", 1016.0, budget) == pytest.approx(200 / 1016)

    @pytest.mark.parametrize("zero", [0.0, -5.0])
    def test_nonpositive_actual_is_nan(self, zero):
        assert math.isnan(recompute_token_ratio(None, "add_tests", zero))
        assert math.isnan(recompute_time_ratio(None, "add_tests", zero))


# ---------------------------------------------------------------------------
# recompute_price_ratio (W3b, geometric mean of ref/cost)
# ---------------------------------------------------------------------------


class TestRecomputePriceRatio:
    def test_geomean_of_ref_over_cost(self, tmp_path, monkeypatch):
        from scorers import reference_model as rm
        from scorers.task_budgets import get_task_budget

        monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")
        # f18: reference_cost_usd = 0.000181
        budget = get_task_budget("f18_direct_answer_first")
        costs = [0.00011397, 6.96e-05, 8.439e-05, 0.00014877]
        ref = budget.reference_cost_usd
        expected = math.exp(sum(math.log(ref / c) for c in costs) / len(costs))
        assert recompute_price_ratio(None, "f18_direct_answer_first", costs, budget) == pytest.approx(expected)

    def test_free_model_is_nan(self, tmp_path, monkeypatch):
        """Free models have actual_cost_usd=0.0 -> filtered out -> nan.

        The 'FREE' display is driven by a separate flag, not this value, so nan
        keeps results <-> compare parity (compare also yields nan for free).
        """
        from scorers import reference_model as rm

        monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")
        assert math.isnan(recompute_price_ratio(None, "add_tests", [0.0, 0.0, 0.0]))
        # mixed with zeros still ignores them
        assert not math.isnan(recompute_price_ratio(None, "add_tests", [0.0, 0.001]))

    def test_empty_or_all_none_is_nan(self):
        assert math.isnan(recompute_price_ratio(None, "add_tests", []))
        assert math.isnan(recompute_price_ratio(None, "add_tests", [None, None]))

    def test_self_heals_on_reference_change(self, tmp_path, monkeypatch):
        """The property that motivated this whole effort: changing the live cost
        reference changes the ratio WITHOUT a re-eval (cards self-heal)."""
        from scorers import reference_model as rm
        from scorers import task_budgets as tb
        from scorers.protocol import TaskBudget

        monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")
        costs = [0.001, 0.002]
        with monkeypatch.context() as m:
            m.setitem(
                tb.TASK_BUDGETS,
                "selfheal",
                TaskBudget(reference_cost_usd=0.002),
            )
            high_ref = recompute_price_ratio(None, "selfheal", costs)
            m.setitem(
                tb.TASK_BUDGETS,
                "selfheal",
                TaskBudget(reference_cost_usd=0.001),
            )
            low_ref = recompute_price_ratio(None, "selfheal", costs)
        # Halving the reference halves every per-sample ratio -> halves the geomean
        assert high_ref == pytest.approx(low_ref * 2.0)
        assert low_ref != high_ref  # actually changed


# ---------------------------------------------------------------------------
# Structural parity: both consumers bind to the SAME function objects
# ---------------------------------------------------------------------------


class TestStructuralParity:
    """If either path re-implements these privately, this fails."""

    def test_compare_uses_shared(self):
        import bench_cli.compare.core as cmp

        for name in ("geometric_mean", "recompute_token_ratio", "recompute_time_ratio", "recompute_price_ratio"):
            assert getattr(cmp, name) is getattr(rr, name), f"compare.{name} is not the shared function"

    def test_results_uses_shared(self):
        import bench_cli.results.core as res

        for name in ("recompute_token_ratio", "recompute_time_ratio", "recompute_price_ratio"):
            assert getattr(res, name) is getattr(rr, name), f"results.{name} is not the shared function"


# ---------------------------------------------------------------------------
# Integration parity: identical per-task ratios from a real eval log
# ---------------------------------------------------------------------------


class TestIntegrationParity:
    def test_results_and_compare_agree_per_task(self, tmp_path):
        """results card-generation and the compare table must produce IDENTICAL
        per-task token/time/cost ratios for the same eval log. This is the
        end-to-end anti-drift guard: it would have caught the m3 staleness bug."""
        if not FIXTURE.exists():
            pytest.skip(f"fixture missing: {FIXTURE}")

        # results requires a dated filename (_FNAME_RE); compare reads eval.task.
        dst = tmp_path / "2026-06-18T00-00-00-00-00_f18-direct-answer-first_PARITY.eval"
        shutil.copy(FIXTURE, dst)

        from bench_cli.compare.core import load_compare_data
        from bench_cli.results.core import _load_model_data

        rdata = _load_model_data(log_dir=tmp_path)
        assert len(rdata) == 1, f"expected 1 card, got {list(rdata)}"
        rscores = next(iter(next(iter(rdata.values()))["tasks"].values()))["scores"]

        cdata = load_compare_data(str(tmp_path))
        assert len(cdata.tasks) == 1 and len(cdata.models) == 1
        cps = cdata.matrix[cdata.tasks[0]][cdata.models[0]]

        # results rounds to 4 dp; compare stores full precision.
        pairs = [
            ("token_ratio_scorer", cps.token_ratio),
            ("time_ratio_scorer", cps.time_ratio),
            ("price_ratio_scorer", cps.price_ratio),
        ]
        for rkey, cval in pairs:
            assert rkey in rscores, f"{rkey} missing from results scores"
            assert abs(rscores[rkey] - round(cval, 4)) < 1e-9, (
                f"{rkey} drift: results={rscores[rkey]} compare={cval}"
            )
