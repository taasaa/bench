"""F10 Environmental Mismatch: model must diagnose multi-layer version/environment mismatches."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.composite_safety import composite_safety_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f10_env_mismatch():
    """Evaluate ability to diagnose multi-layer environment mismatches.

    Given a scenario where no single clue is sufficient, the model must chain
    shebang resolution, PATH/alias, and version manager settings to identify
    the root cause — a mismatch between the environment the package was
    installed in and the environment the script actually runs in.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[verify_sh(), token_ratio_scorer(), time_ratio_scorer(), composite_safety_scorer()],
    )
