"""F9 Cascading Failure: model must identify root cause, not treat symptoms."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.verify_sh import verify_sh


@task
def f9_cascading_failure():
    """Evaluate deep root-cause analysis of cascading failures.

    Given a scenario where a service appears to be failing, the model must
    distinguish between a service that is down vs. one that is misconfigured,
    and identify the true root cause (pool exhaustion, fd leak, unbounded
    cache, thread starvation) rather than suggesting symptom workarounds.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=verify_sh(),
    )
