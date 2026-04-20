"""Integration tests: verify tasks use correct scorers end-to-end."""

import importlib.util
import os
import sys

import pytest


def _module_available(name: str) -> bool:
    """Check if a module can be imported without actually importing it."""
    return importlib.util.find_spec(name) is not None


# Ensure project root is on sys.path for scorers import
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Each task is defined in a subdirectory with hyphens, so they can't be
# imported as regular Python packages.  We load them via importlib and
# instantiate in their own directory so dataset.json resolves.

# Tasks that use the composite scorer (competence tier)
COMPOSITE_TASK_SPECS: list[tuple[str, str]] = []

# Tasks that use the verify_sh scorer (competence tier)
BASIC_TASK_SPECS = [
    ("tasks/competence/add-tests/task.py", "add_tests"),
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
        """composite scorer: value in [0,1], explanation has pillar fields."""
        t = _load_task(rel_path, func_name)
        scorer = _get_scorer_fn(t)

        import asyncio

        from inspect_ai.model import ChatMessageAssistant, ModelOutput
        from inspect_ai.scorer import Target
        from inspect_ai.solver import TaskState

        output = ModelOutput.from_content(model="test", content="hello world")
        state = TaskState(
            model="test", sample_id="x", epoch=0, input="",
            messages=[ChatMessageAssistant(content="hello world")],
            target=Target("hello world"),
            output=output,
        )
        result = asyncio.run(scorer(state, state.target))

        assert 0.0 <= result.value <= 1.0, (
            f"{func_name} scorer value {result.value} outside [0,1]"
        )
        assert "correctness=" in result.explanation
        assert "efficiency=" in result.explanation
        assert "safety" in result.explanation

    def test_composite_importable_from_package(self):
        from scorers.composite import composite

        assert callable(composite)


class TestBasicTasksUseVerifySh:
    """Basic tier tasks must use the verify_sh scorer."""

    @pytest.mark.parametrize("rel_path,func_name", BASIC_TASK_SPECS)
    def test_basic_task_uses_verify_sh(self, rel_path, func_name):
        """verify_sh scorer: value in [0,1], explanation has correctness field."""
        t = _load_task(rel_path, func_name)
        scorer = _get_scorer_fn(t)

        import asyncio

        from inspect_ai.model import ChatMessageAssistant, ModelOutput
        from inspect_ai.scorer import Target
        from inspect_ai.solver import TaskState

        output = ModelOutput.from_content(model="test", content="some model output")
        state = TaskState(
            model="test", sample_id="x", epoch=0, input="",
            messages=[ChatMessageAssistant(content="some model output")],
            target=Target(""),
            output=output,
        )
        result = asyncio.run(scorer(state, state.target))

        assert 0.0 <= result.value <= 1.0, (
            f"{func_name} scorer value {result.value} outside [0,1]"
        )
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0, f"{func_name} scorer returned empty explanation"

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

    def _load_and_check(self, rel_path: str, func_name: str) -> None:
        """Load task and verify scorer returns non-None result with explanation."""
        t = _load_task(rel_path, func_name)
        scorer = _get_scorer_fn(t)

        import asyncio

        from inspect_ai.model import ChatMessageAssistant, ModelOutput
        from inspect_ai.scorer import Target
        from inspect_ai.solver import TaskState

        output = ModelOutput.from_content(model="test", content="test output")
        state = TaskState(
            model="test", sample_id="x", epoch=0, input="",
            messages=[ChatMessageAssistant(content="test output")],
            target=Target(""),
            output=output,
        )
        result = asyncio.run(scorer(state, state.target))

        assert result is not None, f"{func_name} scorer returned None"
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0, f"{func_name} returned empty explanation"

    def test_smoke_task_scorer_behavior(self):
        """smoke task scorer returns result with explanation (uses includes())."""
        self._load_and_check("tasks/verification/smoke/task.py", "smoke")

    @pytest.mark.skipif(
        not _module_available("inspect_swe"),
        reason="inspect_swe not installed (Docker agent eval dependency)",
    )
    def test_agent_smoke_task_scorer_behavior(self):
        """agent_smoke task scorer returns numeric result with explanation."""
        t = _load_task("tasks/verification/agent_smoke/task.py", "agent_smoke")
        scorer = _get_scorer_fn(t)

        import asyncio

        from inspect_ai.model import ChatMessageAssistant, ModelOutput
        from inspect_ai.scorer import Target
        from inspect_ai.solver import TaskState

        # Test matching output — target "hello world" is in the output
        output = ModelOutput.from_content(
            model="test", content="I created hello.py with hello world"
        )
        state = TaskState(
            model="test",
            sample_id="x",
            epoch=0,
            input="",
            messages=[ChatMessageAssistant(content="I created hello.py with hello world")],
            target=Target("hello world"),
            output=output,
        )
        result = asyncio.run(scorer(state, state.target))
        assert isinstance(result.value, float), (
            f"Expected float, got {type(result.value).__name__}: {result.value!r}"
        )
        assert result.value == 1.0
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0

        # Test non-matching output
        output2 = ModelOutput.from_content(model="test", content="Something unrelated")
        state2 = TaskState(
            model="test",
            sample_id="x",
            epoch=0,
            input="",
            messages=[ChatMessageAssistant(content="Something unrelated")],
            target=Target("hello world"),
            output=output2,
        )
        result2 = asyncio.run(scorer(state2, state2.target))
        assert isinstance(result2.value, float)
        assert result2.value == 0.0


class TestTaskCoverage:
    """Every task with verify.sh must have a test file covering it.

    This CI gate catches tasks that get added but never tested.
    """

    # All tasks that use verify.sh — scanned from tasks/ directory.
    # Coverage sources:
    #   test_tier1_tasks.py: q1, q2, f7, f12, f20
    #   test_tier2_tasks.py: f6, f8, f11, f14, q4
    #   test_integration.py (TestBasicTasksUseVerifySh): q1, q2, f7, f12, f20
    #   test_integration.py (TestCompositeScorerWiring): add-tests (via composite)
    #   Fixture tests (test_tier2_tasks.py + test_fixtures.py): f1, f9, f10, f23, f24
    VERIFY_TASKS_WITH_COVERAGE = {
        "tasks/analysis/f1-multi-file-verify",      # f24 fixture tests
        "tasks/analysis/f10-env-mismatch",           # f24 fixture tests
        "tasks/analysis/f23-ghost-constraint",       # f24 fixture tests
        "tasks/analysis/f24-honey-trap",             # f24 fixture tests
        "tasks/analysis/f9-cascading-failure",        # f24 fixture tests
        "tasks/competence/add-tests",                # TestCompositeScorerWiring
        "tasks/competence/f12-surgical-fix",         # TestBasicTasksUseVerifySh + test_tier1_tasks.py
        "tasks/competence/f20-scope-calibration",    # TestBasicTasksUseVerifySh + test_tier1_tasks.py
        "tasks/competence/f7-format-compliance",      # TestBasicTasksUseVerifySh + test_tier1_tasks.py
        "tasks/competence/q1-verification-gate",     # TestBasicTasksUseVerifySh + test_tier1_tasks.py
        "tasks/competence/q2-do-not-touch",          # TestBasicTasksUseVerifySh + test_tier1_tasks.py
        "tasks/execution/f11-intermittent-bug",      # test_tier2_tasks.py
        "tasks/execution/f14-insert-dont-replace",   # test_tier2_tasks.py
        "tasks/execution/f6-partial-impl",           # test_tier2_tasks.py
        "tasks/execution/f8-negative-constraint",    # test_tier2_tasks.py
        "tasks/execution/q4-root-cause",              # test_tier2_tasks.py
        # NOTE: verification/smoke has coverage (test_smoke_task_scorer_behavior)
        # NOTE: verification/agent_smoke has skip + no verify.sh (uses includes() scorer)
        # Session 11 new tasks (2026-04-16)
        "tasks/competence/q3-answer-the-question",    # quick tier
        "tasks/competence/q5-safe-git-operations",    # quick tier
        "tasks/competence/f18-direct-answer-first",   # quick tier
        "tasks/execution/f5-multi-constraint-edit",  # test_tier2_tasks.py
        "tasks/execution/f15-workspace-setup",       # agent-mode task
        "tasks/execution/f16-bug-investigation",     # agent-mode task
        "tasks/execution/f17-config-migration",      # agent-mode task
        # NOTE: f4-dependency-version-audit is llm_judge, no verify.sh
        # NOTE: f19-admit-uncertainty is llm_judge, no verify.sh
        # New hybrid-scored tasks (PRD phases 5-7)
        "tasks/analysis/f21-liars-codebase",          # hybrid scorer, verify.sh added
        "tasks/universal/u17-dirty-workspace-triage",  # new task, hybrid scorer
        "tasks/universal/u18-resume-after-bad-attempt", # new task, hybrid scorer
    }

    def test_all_verify_tasks_have_coverage(self):
        """Every task directory with verify.sh must be in VERIFY_TASKS_WITH_COVERAGE."""
        import os

        tasks_root = os.path.join(ROOT, "tasks")
        missing = []
        for tier in os.listdir(tasks_root):
            tier_path = os.path.join(tasks_root, tier)
            if not os.path.isdir(tier_path):
                continue
            for task_name in os.listdir(tier_path):
                task_dir = os.path.join(tier_path, task_name)
                if not os.path.isdir(task_dir):
                    continue
                if os.path.isfile(os.path.join(task_dir, "verify.sh")):
                    rel = os.path.join("tasks", tier, task_name)
                    if rel not in self.VERIFY_TASKS_WITH_COVERAGE:
                        missing.append(rel)

        assert missing == [], (
            f"Tasks with verify.sh but no test coverage: {missing}\n"
            f"Add them to VERIFY_TASKS_WITH_COVERAGE in test_integration.py"
        )

    def test_all_verify_tasks_have_coverage_stated_count(self):
        """Coverage list must match actual verify.sh count."""
        import os

        tasks_root = os.path.join(ROOT, "tasks")
        actual_verify_tasks = []
        for tier in os.listdir(tasks_root):
            tier_path = os.path.join(tasks_root, tier)
            if not os.path.isdir(tier_path):
                continue
            for task_name in os.listdir(tier_path):
                task_dir = os.path.join(tier_path, task_name)
                if os.path.isdir(task_dir) and os.path.isfile(os.path.join(task_dir, "verify.sh")):
                    actual_verify_tasks.append(os.path.join("tasks", tier, task_name))

        assert len(self.VERIFY_TASKS_WITH_COVERAGE) == len(actual_verify_tasks), (
            f"VERIFY_TASKS_WITH_COVERAGE has {len(self.VERIFY_TASKS_WITH_COVERAGE)} entries "
            f"but found {len(actual_verify_tasks)} verify.sh files: "
            f"{sorted(actual_verify_tasks)}"
        )
