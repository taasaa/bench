"""F25 Tenant Leakage: test if model notices contextvars when caching."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer


@task
def f25_tenant_leakage():
    """Evaluate cross-tenant data safety during performance optimization.

    The model is asked to cache get_active_configuration(), which reads a
    ContextVar for the tenant ID. A naive `@lru_cache` causes a data leak.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            hybrid_scorer(),
            token_ratio_scorer(task_budget=get_task_budget("f25_tenant_leakage")),
            time_ratio_scorer(task_budget=get_task_budget("f25_tenant_leakage")),
            price_ratio_scorer(task_budget=get_task_budget("f25_tenant_leakage")),
        ],
    )
