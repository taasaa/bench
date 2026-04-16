"""Q3 Answer The Question: model must answer briefly without extra preamble."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def q3_answer_the_question():
    """Evaluate ability to answer directly with minimal preamble.

    Given a question with specific format requirements, the model must:
    1. Provide the correct command/steps in the answer
    2. Not explain what virtual environments are
    3. Not mention alternatives
    4. Keep total response under 200 words

    Tests whether models can stop themselves from over-explaining and
    follow scope constraints on preamble/content.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[verify_sh(), token_ratio_scorer(task_budget=get_task_budget("q3_answer_the_question")), time_ratio_scorer(task_budget=get_task_budget("q3_answer_the_question")), price_ratio_scorer(task_budget=get_task_budget("q3_answer_the_question"))],
    )
