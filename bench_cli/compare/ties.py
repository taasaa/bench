"""Pairwise CI overlap tie detection for ``bench compare``.

Ties are determined per pair (NOT transitive). ``detect_ties`` returns a
flat list of ``{model_a, model_b}`` groups; a model can appear in multiple
groups. ``annotate_with_ties`` produces display rank + ``≈`` badge +
annotation pointing to the highest-ranked tie-partner for any model whose
CI overlaps with at least one higher-ranked model's CI.
"""

from __future__ import annotations

from typing import Iterable


def detect_ties(
    model_cis: dict[str, tuple[float, float] | None],
) -> list[set[str]]:
    """Detect pairwise overlapping CIs.

    Two models are tied if their CIs overlap on any point. Returns a flat
    list of 2-element groups (one per overlapping pair). Non-transitive —
    a model can appear in multiple groups.

    Models with CI=None (partial evals) are skipped.
    """
    groups: list[set[str]] = []
    valid = {k: v for k, v in model_cis.items() if v is not None}
    models = list(valid.keys())
    for i, a in enumerate(models):
        a_lo, a_hi = valid[a]
        for b in models[i + 1 :]:
            b_lo, b_hi = valid[b]
            # Overlap iff NOT (a_hi < b_lo OR b_hi < a_lo).
            if not (a_hi < b_lo or b_hi < a_lo):
                groups.append({a, b})
    return groups


def annotate_with_ties(
    sorted_models: list[tuple[str, float, tuple[float, float] | None]],
) -> list[tuple[str, int, str, str | None]]:
    """Assign (model, rank, badge, tied_with_rank_str) per spec.

    Rank is ordinal (1, 2, 3, ...) by capability descending — never
    non-advancing on tie. The badge is ``"≈"`` only when this model's CI
    overlaps with at least one higher-ranked model's CI; the annotation
    ``tied_with_rank_str`` is ``"#X"`` for the highest-ranked such
    partner, or ``None`` when no badge.

    Partial-eval models (CI=None) get ``(model, rank, "", None)`` — pairwise
    comparison is undefined.

    Implementation: walk the sorted list forward. For each model M, scan
    earlier sorted entries until the first overlap is found. The first
    earlier entry IS the highest-ranked partner because the list is sorted
    by capability descending.
    """
    out: list[tuple[str, int, str, str | None]] = []
    for i, (model, _cap, ci) in enumerate(sorted_models):
        rank = i + 1
        if ci is None:
            out.append((model, rank, "", None))
            continue
        tie_partner_rank: int | None = None
        for j in range(i):
            _other, _other_cap, other_ci = sorted_models[j]
            if other_ci is None:
                continue
            a_lo, a_hi = other_ci
            b_lo, b_hi = ci
            # Overlap iff NOT (a_hi < b_lo OR b_hi < a_lo).
            if not (a_hi < b_lo or b_hi < a_lo):
                tie_partner_rank = j + 1
                break
        if tie_partner_rank is None:
            out.append((model, rank, "", None))
        else:
            out.append((model, rank, "≈", f"#{tie_partner_rank}"))
    return out
