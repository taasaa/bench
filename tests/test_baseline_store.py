"""Tests for BaselineStore + reference-model registry (W3)."""

from __future__ import annotations


def test_baseline_has_reference_cost_usd():
    from scorers.baseline_store import Baseline

    b = Baseline(
        task_id="t",
        model_id="m",
        run_at="x",
        correctness=1.0,
        valid_for_reference=True,
        total_tokens=10,
        reference_cost_usd=0.002,
    )
    assert b.reference_cost_usd == 0.002
    assert Baseline.from_dict(b.to_dict()).reference_cost_usd == 0.002  # round-trips


def test_reference_model_registry_get_set(tmp_path, monkeypatch):
    """W3: reference-model registry get/set, file-backed, default None."""
    from scorers import reference_model as rm

    f = tmp_path / "ref.json"
    monkeypatch.setattr(rm, "_REFERENCE_FILE", f)
    assert rm.get_reference_model_id() is None
    rm.set_reference_model_id("openai/minimax-m3")
    assert rm.get_reference_model_id() == "openai/minimax-m3"


def test_resolve_baseline_reference_targets_reference_model(tmp_path, monkeypatch):
    """W3: Tier-1 lookup targets the DESIGNATED reference model, not the subject."""
    from scorers import reference_model as rm
    from scorers.baseline_store import BaselineStore, Baseline
    from scorers.protocol import resolve_baseline_reference, RatioSource

    store_dir = tmp_path / "baselines"
    store = BaselineStore(str(store_dir))
    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")
    rm.set_reference_model_id("openai/minimax-m3")
    # record a baseline FOR THE REFERENCE model
    store.save(
        Baseline(
            task_id="add_tests",
            model_id="openai/minimax-m3",
            run_at="x",
            correctness=0.9,
            valid_for_reference=True,
            total_tokens=10,
            output_tokens=508,
        ),
        "add_tests",
        "openai/minimax-m3",
    )
    # resolve for a DIFFERENT subject -> still uses the reference's value
    ref_val, source, ref_model = resolve_baseline_reference(
        store, "add_tests", "openai/glm-5.1", "output_tokens"
    )
    assert ref_val == 508.0
    assert source is RatioSource.BASELINE
    assert ref_model == "openai/minimax-m3"


def test_resolve_cost_reference_targets_reference_model(tmp_path, monkeypatch):
    """W3: cost Tier-1 lookup also targets the designated reference model."""
    from scorers import reference_model as rm
    from scorers.baseline_store import BaselineStore, Baseline
    from scorers.protocol import resolve_cost_reference, RatioSource

    store = BaselineStore(str(tmp_path / "baselines"))
    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")
    rm.set_reference_model_id("openai/minimax-m3")
    store.save(
        Baseline(
            task_id="add_tests",
            model_id="openai/minimax-m3",
            run_at="x",
            correctness=0.9,
            valid_for_reference=True,
            total_tokens=10,
            reference_cost_usd=0.001,
        ),
        "add_tests",
        "openai/minimax-m3",
    )
    cost, source, ref = resolve_cost_reference(store, "add_tests")
    assert cost == 0.001
    assert source is RatioSource.BASELINE
    assert ref == "openai/minimax-m3"


def test_resolve_returns_system_default_when_no_reference_registered(tmp_path, monkeypatch):
    """W3: no reference registered -> SYSTEM_DEFAULT (back-compat with empty store)."""
    from scorers import reference_model as rm
    from scorers.baseline_store import BaselineStore
    from scorers.protocol import resolve_baseline_reference, RatioSource

    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")  # does not exist -> None
    store = BaselineStore(str(tmp_path / "baselines"))
    ref_val, source, ref_model = resolve_baseline_reference(
        store, "add_tests", "openai/glm-5.1", "output_tokens"
    )
    assert ref_val == 1000.0
    assert source is RatioSource.SYSTEM_DEFAULT
    assert ref_model is None
