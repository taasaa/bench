"""Pareto front computation on flat arrays — (capability, -cost, -time)."""

from __future__ import annotations


def compute_pareto_front(
    models: list[str],
    capability: list[float],
    cost: list[float],
    time: list[float],
) -> tuple[list[int], list[list[int]]]:
    """Compute Pareto front across (capability, -cost, -time).

    A model dominates another if it is >= on all axes and > on at least one.
    Objectives: maximize capability, minimize cost, minimize time.
    """
    n = len(models)
    dominated_by: list[list[int]] = [[] for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            cap_ge = capability[j] >= capability[i]
            cost_ge = cost[j] <= cost[i]
            time_ge = time[j] <= time[i]

            cap_gt = capability[j] > capability[i]
            cost_gt = cost[j] < cost[i]
            time_gt = time[j] < time[i]

            if cap_ge and cost_ge and time_ge and (cap_gt or cost_gt or time_gt):
                dominated_by[i].append(j)

    pareto_indices = [i for i in range(n) if not dominated_by[i]]
    return pareto_indices, dominated_by
