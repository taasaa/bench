"""Integration tests: verify tasks use correct scorers end-to-end."""

import importlib.util
import os
import sys

import pytest

# Ensure project root is on sys.path for scorers import
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Each task is defined in a subdirectory with hyphens, so they can't be
# imported as regular Python packages.  We load them via importlib and
# instantiate in their own directory so dataset.json resolves.

# Tasks that use the composite scorer (code_gen tier)
COMPOSITE_TASK_SPECS = [
    ("tasks/code_gen/add-tests/task.py", "add_tests"),
]

# Tasks that use the verify_sh scorer (basic tier)
BASIC_TASK_SPECS = [
    ("tasks/competence/q1-verification-gate/task.py", "q1_verification_gate"),
    ("tasks/competence/q2-do-not-touch/task.py", "q2_do_not_touch"),
    ("tasks/competence/f7-format-compliance/task.py", "f7_format_compliance"),
    ("tasks/competence/f12-surgical-fix/task.py", "f12_surgical_fix"),
    ("tasks/competence/f20-scope-calibration/task.py", "f20_scope_calibration"),
]

# All known task specs (for generic wiring checks)
ALL_TASK_SPECS = COMPOSITE_TASK_SPECS + BASIC_TASK_SPECS


def _load_task(rel_path: str, func_name: str):
    """Load a task module and return the instantiated Task object."""
    task_dir = os.path.dirname(rel_path)
    orig_cwd = os.getcwd()
    try:
        os.chdir(os.path.join(ROOT, task_dir))
        spec = importlib.util.spec_from_file_location(
            "task", os.path.join(ROOT, rel_path)
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, func_name)()
    finally:
        os.chdir(orig_cwd)


def _get_scorer_fn(task_obj):
    """Extract the inner scorer function from a Task (may be wrapped in a list)."""
    scorer = task_obj.scorer
    if isinstance(scorer, list):
        scorer = scorer[0]
    return scorer


class TestCompositeScorerWiring:
    """Code-gen tasks must use the composite scorer."""

    @pytest.mark.parametrize("rel_path,func_name", COMPOSITE_TASK_SPECS)
    def test_task_uses_composite_scorer(self, rel_path, func_name):
        t = _load_task(rel_path, func_name)
        scorer = _get_scorer_fn(t)

        from scorers.composite import composite

        ref = composite()
        assert scorer.__code__.co_code == ref.__code__.co_code, (
            f"{func_name} scorer does not match composite()"
        )

    def test_composite_importable_from_package(self):
        from scorers.composite import composite

        assert callable(composite)


class TestBasicTasksUseVerifySh:
    """Basic tier tasks must use the verify_sh scorer."""

    @pytest.mark.parametrize("rel_path,func_name", BASIC_TASK_SPECS)
    def test_basic_task_uses_verify_sh(self, rel_path, func_name):
        t = _load_task(rel_path, func_name)
        scorer = _get_scorer_fn(t)

        from scorers.verify_sh import verify_sh

        ref = verify_sh()
        assert scorer.__code__.co_code == ref.__code__.co_code, (
            f"{func_name} scorer does not match verify_sh()"
        )

    @pytest.mark.parametrize("rel_path,func_name", BASIC_TASK_SPECS)
    def test_basic_task_has_samples(self, rel_path, func_name):
        t = _load_task(rel_path, func_name)
        assert len(t.dataset) >= 3, (
            f"{func_name} should have at least 3 samples, got {len(t.dataset)}"
        )


class TestAllTasksScorerName:
    """All tasks should have a scorer function named 'score'."""

    @pytest.mark.parametrize("rel_path,func_name", ALL_TASK_SPECS)
    def test_task_scorer_name(self, rel_path, func_name):
        t = _load_task(rel_path, func_name)
        scorer = _get_scorer_fn(t)
        assert scorer.__name__ == "score"


class TestVerificationTasksUnmodified:
    """Verification tasks should NOT use the composite scorer."""

    VERIFICATION_TASKS = [
        ("tasks/verification/smoke/task.py", "smoke"),
        ("tasks/verification/agent_smoke/task.py", "agent_smoke"),
    ]

    @pytest.mark.parametrize("rel_path,func_name", VERIFICATION_TASKS)
    def test_verification_task_not_composite(self, rel_path, func_name):
        t = _load_task(rel_path, func_name)
        scorer = _get_scorer_fn(t)

        from scorers.composite import composite

        ref = composite()
        assert scorer.__code__.co_code != ref.__code__.co_code, (
            f"{func_name} should NOT use composite scorer"
        )
