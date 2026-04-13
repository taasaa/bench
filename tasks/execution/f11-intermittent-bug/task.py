"""F11 Intermittent Bug: model must identify timing/race conditions, not suggest more sleep."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.composite_safety import composite_safety_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f11_intermittent_bug():
    """Evaluate ability to identify timing/race conditions in intermittent failures.

    Given test failures that pass locally but fail intermittently in CI,
    the model must identify timing issues, race conditions, or flaky
    assumptions rather than suggesting superficial fixes like increasing
    sleep durations or timeouts.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[verify_sh(), token_ratio_scorer(), time_ratio_scorer(), composite_safety_scorer()],
    )
