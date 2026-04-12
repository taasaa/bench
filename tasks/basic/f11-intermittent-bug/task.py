"""F11 Intermittent Bug: model must identify timing/race conditions, not suggest more sleep."""

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec

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
        scorer=verify_sh(),
    )
