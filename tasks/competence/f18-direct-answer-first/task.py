"""F18 Direct Answer First: model must give the answer in the first sentence, briefly."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f18_direct_answer_first():
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            verify_sh(),
            token_ratio_scorer(task_budget=get_task_budget("f18_direct_answer_first")),
            time_ratio_scorer(task_budget=get_task_budget("f18_direct_answer_first")),
            price_ratio_scorer(task_budget=get_task_budget("f18_direct_answer_first")),
        ],
    )
