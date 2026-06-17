"""Tests for compare recompute + labels (W3a/W3c)."""

from __future__ import annotations


def test_recompute_token_time_ratios_from_budget(tmp_path, monkeypatch):
    """W3a: token/time ratios recomputed at view time; no reference -> budget tier."""
    from scorers import reference_model as rm
    from scorers.task_budgets import get_task_budget
    from bench_cli.compare.core import _recompute_token_ratio, _recompute_time_ratio

    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")  # no reference -> budget tier
    budget = get_task_budget("add_tests")  # output_tokens=508
    assert _recompute_token_ratio(baseline_store=None, task="add_tests", avg_tokens=1016, budget=budget) == 0.5
    assert (
        _recompute_time_ratio(baseline_store=None, task="add_tests", avg_time=34.0, budget=budget)
        != float("nan")
    )


def test_recompute_uses_reference_baseline_when_registered(tmp_path, monkeypatch):
    """W3a + Goal #5: a registered reference baseline wins over task_budget for ALL subjects."""
    from scorers import reference_model as rm
    from scorers.baseline_store import BaselineStore, Baseline
    from scorers.task_budgets import get_task_budget
    from bench_cli.compare.core import _recompute_token_ratio

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
    # reference 200 / actual 1016 != budget 508 / 1016 — proves the reference (not budget) is used
    assert (
        _recompute_token_ratio(baseline_store=store, task="add_tests", avg_tokens=1016, budget=budget)
        == 200 / 1016
    )


def test_ratio_reference_labels_default_and_registered(tmp_path, monkeypatch):
    """W3c: legend names the reference model; defaults when none registered."""
    from scorers import reference_model as rm
    from bench_cli.compare.core import _ratio_reference_labels

    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")  # none registered
    labels = _ratio_reference_labels()
    assert "qwen-local" in labels["efficiency_latency"]  # SYSTEM_DEFAULT calibration source
    assert "minimax-m2.7" in labels["cost"]  # task_budgets reference source

    rm.set_reference_model_id("openai/minimax-m3")
    labels = _ratio_reference_labels()
    assert labels["efficiency_latency"] == "openai/minimax-m3"
    assert labels["cost"] == "openai/minimax-m3"
