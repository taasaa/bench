"""F7 Format Compliance: model must output valid JSON with exact key structure."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.composite_safety import composite_safety_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f7_format_compliance():
    """Evaluate ability to produce structurally exact JSON output.

    Given unstructured text data, the model must output a JSON array with
    objects containing exact keys (name, score, passed) and correct types.
    No markdown fences, no extra text — raw JSON only.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[verify_sh(), token_ratio_scorer(), time_ratio_scorer(), composite_safety_scorer()],
    )
