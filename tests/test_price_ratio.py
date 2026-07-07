"""Tests for price/token ratio scorer self-provisioning + Tier-1 reference (W3b)."""

from __future__ import annotations

import asyncio


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_price_ratio_uses_reference_model_cost(tmp_path, monkeypatch):
    """W3b: scorer resolves the DESIGNATED reference model's cost, not the subject's.

    Register minimax-m3 as reference (cost 999), then score a SUBJECT (a priced
    nemotron alias) and assert reference_cost_usd == 999 (reference-driven).
    """
    from scorers import reference_model as rm
    from scorers.baseline_store import BaselineStore, Baseline
    from scorers.price_ratio import price_ratio_scorer
    from scorers.protocol import TaskBudget
    from unittest.mock import MagicMock

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
            reference_cost_usd=999.0,
        ),
        "add_tests",
        "openai/minimax-m3",
    )
    # Point the lazy-provisioned store at our temp dir so the scorer finds the baseline.
    monkeypatch.setattr("scorers.protocol._maybe_provision_baseline_store", lambda *a, **k: store)

    budget = TaskBudget(reference_cost_usd=0.001)  # Tier-2 fallback; must NOT win
    scorer = price_ratio_scorer(task_budget=budget)

    state = MagicMock()
    state.model = "openai/nemotron-ultra-550b"  # the SUBJECT (a priced alias)
    state.metadata = {"task_name": "add_tests"}

    class U:
        input_tokens = 1_000_000
        output_tokens = 1_000_000

    state.output.usage = U()
    score = _run(scorer(state, MagicMock()))
    assert score.metadata["reference_cost_usd"] == 999.0  # reference-model cost used


def test_scorers_unchanged_when_no_reference_registered(tmp_path, monkeypatch):
    """W3b: with no reference registered, scorers behave exactly as before (store=None)."""
    from scorers import reference_model as rm
    from scorers.price_ratio import price_ratio_scorer
    from scorers.protocol import TaskBudget
    from unittest.mock import MagicMock

    monkeypatch.setattr(rm, "_REFERENCE_FILE", tmp_path / "ref.json")  # does not exist
    budget = TaskBudget(reference_cost_usd=0.001)
    scorer = price_ratio_scorer(task_budget=budget)
    state = MagicMock()
    state.model = "openai/nemotron-ultra-550b"
    state.metadata = {"task_name": "add_tests"}

    class U:
        input_tokens = 1_000_000
        output_tokens = 1_000_000

    state.output.usage = U()
    score = _run(scorer(state, MagicMock()))
    # No reference registered -> Tier-2 task_budget wins (0.001)
    assert score.metadata["reference_cost_usd"] == 0.001


def test_token_ratio_uses_reference_baseline_when_registered(tmp_path, monkeypatch):
    """W3a + Goal #5: token scorer uses a registered reference baseline OVER task_budget."""
    from scorers import reference_model as rm
    from scorers.baseline_store import BaselineStore, Baseline
    from scorers.token_ratio import token_ratio_scorer
    from scorers.protocol import TaskBudget, RatioSource
    from unittest.mock import MagicMock

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
    # Monkeypatch the shared self-provisioning helper to return our test store
    monkeypatch.setattr("scorers.protocol._maybe_provision_baseline_store", lambda *a, **k: store)

    # task_budget.output_tokens=508 would give 508/1016==0.5; reference 200 -> 200/1016
    budget = TaskBudget(output_tokens=508)
    scorer = token_ratio_scorer(task_budget=budget)
    state = MagicMock()
    state.model = "openai/glm-5.1"  # a DIFFERENT subject
    state.metadata = {"task_name": "add_tests"}
    state.token_usage = 1016  # actual total tokens
    score = _run(scorer(state, MagicMock()))
    assert score.metadata["reference_tokens"] == 200  # reference (not budget 508)
    assert score.metadata["reference_source"] == RatioSource.BASELINE.value
    assert score.metadata["reference_model"] == "openai/minimax-m3"


# ---------------------------------------------------------------------------
# Bug 8a68338a: Score free models at real (paid) price, not $0
# ---------------------------------------------------------------------------


def test_free_model_price_ratio_uses_paid_variant():
    """For :free models, price_ratio_scorer should use the paid variant's price
    to compute a meaningful cost_ratio (not inf)."""
    import math
    from unittest.mock import MagicMock, patch
    from scorers.price_ratio import price_ratio_scorer
    from scorers.protocol import TaskBudget

    # Pricing layer is the single source of truth — mock
    # `resolve_market_price` directly to return the paid-variant price
    # ($0.08/M in, $0.45/M out) for the :free alias. This is what the
    # scorer reads; the LiteLLM config + OpenRouter cache plumbing is
    # exercised by other tests.
    budget = TaskBudget(reference_cost_usd=0.001)
    scorer_fn = price_ratio_scorer(task_budget=budget)

    state = MagicMock()
    state.model = "openai/nemotron-super-120b-free"
    state.metadata = {"task_name": "add_tests"}

    class U:
        input_tokens = 1_000_000
        output_tokens = 1_000_000

    state.output.usage = U()

    with patch(
        "scorers.price_ratio.resolve_market_price",
        return_value=(0.08, 0.45),
    ):
        score = _run(scorer_fn(state, MagicMock()))

    # cost_ratio should be finite (paid variant's price used), not inf
    assert not math.isinf(score.value), (
        f"Expected finite cost_ratio, got inf. Metadata: {score.metadata}"
    )
    assert not math.isnan(score.value), (
        f"Expected finite cost_ratio, got nan"
    )
    # actual_cost should be positive (computed from paid variant's price)
    assert score.metadata["actual_cost_usd"] > 0
    # is_free=True (model IS accessed free) but cost_ratio is finite.
    assert score.metadata["is_free"] is True
