"""F1 Multi-File Verification: model must cross-reference claims against actual code across multiple files."""

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec

from scorers.verify_sh import verify_sh


@task
def f1_multi_file_verify():
    """Evaluate multi-file code verification ability.

    The model is told a developer claims "all tests pass and the service works"
    for a 3-file project. It must verify this claim by reading all 3 files,
    finding 2 planted bugs, and correctly reporting the claim is FALSE.

    Tests whether models actually read code carefully rather than agreeing
    with the developer's claim, and whether they can identify subtle bugs
    like wrong attribute names, missing imports, field name mismatches,
    and mutation side effects.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=verify_sh(),
    )
