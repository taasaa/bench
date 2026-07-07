"""Tests for the --tier viability pass: discovery, CLI surface, and error handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from bench_cli.main import cli
from bench_cli.run import _discover_tasks
from bench_cli.run.core import VIABILITY_TASKS, _discover_viability_tasks

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VIABILITY_TASK_DIRS = [
    "competence/q3-answer-the-question",
    "execution/q4-root-cause",
    "analysis/f1-multi-file-verify",
    "universal/u17-dirty-workspace-triage",
]


def _make_viability_tasks_root(tmp_path: Path) -> Path:
    """Create a tasks/ directory with the 4 viability task stubs (valid @task)."""
    tasks = tmp_path / "tasks"
    task_file_content = '''\
"""Fixture viability task for CLI testing."""
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset

@task
def fixture_task():
    return Task(
        dataset=MemoryDataset(samples=[]),
        scorer=None,
    )
'''
    for d in VIABILITY_TASK_DIRS:
        (tasks / d).mkdir(parents=True)
        (tasks / d / "task.py").write_text(task_file_content)
    return tasks


@pytest.fixture
def viability_tasks_root(tmp_path: Path, monkeypatch):
    """Create a temporary tasks/ tree with the 4 viability tasks, chdir to it."""
    _make_viability_tasks_root(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path / "tasks"


@pytest.fixture
def missing_one_viability_task(tmp_path: Path, monkeypatch):
    """Like viability_tasks_root but missing one task (the third one)."""
    tasks = tmp_path / "tasks"
    task_file_content = '''\
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset

@task
def fixture_task():
    return Task(dataset=MemoryDataset(samples=[]), scorer=None)
'''
    # Create only 3 of the 4 viability tasks (drop f1-multi-file-verify)
    for d in VIABILITY_TASK_DIRS:
        if d.endswith("f1-multi-file-verify"):
            continue
        (tasks / d).mkdir(parents=True)
        (tasks / d / "task.py").write_text(task_file_content)
    monkeypatch.chdir(tmp_path)
    return tmp_path / "tasks"


# ---------------------------------------------------------------------------
# VIABILITY_TASKS constant
# ---------------------------------------------------------------------------


class TestViabilityTasksConstant:
    def test_has_four_tasks(self):
        assert len(VIABILITY_TASKS) == 4

    def test_all_unique(self):
        assert len(VIABILITY_TASKS) == len(set(VIABILITY_TASKS))

    def test_covers_all_four_pillars(self):
        # Pillar coverage: the 4 tasks should map to 4 different pillars
        # when looked up in the real tasks/ tree. This is a guard against
        # accidentally picking two tasks from the same pillar.
        real = Path("tasks")
        pillars = set()
        for name in VIABILITY_TASKS:
            for sub in sorted(p for p in real.iterdir() if p.is_dir()):
                if (sub / name / "task.py").is_file():
                    pillars.add(sub.name)
                    break
            else:
                pytest.fail(f"VIABILITY_TASKS entry {name!r} not found in real tasks/ tree")
        assert pillars == {"competence", "execution", "analysis", "universal"}, (
            f"VIABILITY_TASKS must cover all 4 pillars, got {pillars}"
        )

    def test_all_use_verify_sh(self):
        # Viability is supposed to be deterministic + judge-free. The 4 tasks
        # should all have a verify.sh (no judge.md without verify.sh).
        for name in VIABILITY_TASKS:
            real = Path("tasks")
            task_dir = None
            for sub in sorted(p for p in real.iterdir() if p.is_dir()):
                if (sub / name).is_dir():
                    task_dir = sub / name
                    break
            assert task_dir is not None, f"{name!r} not found in real tasks/ tree"
            assert (task_dir / "verify.sh").is_file(), (
                f"{name!r} is in VIABILITY_TASKS but has no verify.sh. "
                "Judge-only tasks don't belong in the viability tier."
            )
            assert (task_dir / "verify.sh").stat().st_mode & 0o111, (
                f"{name!r}/verify.sh is not executable"
            )


# ---------------------------------------------------------------------------
# _discover_viability_tasks
# ---------------------------------------------------------------------------


class TestDiscoverViabilityTasks:
    def test_returns_four_specs(self, viability_tasks_root):
        specs = _discover_viability_tasks(viability_tasks_root, None, None)
        assert len(specs) == 4

    def test_specs_are_relative_paths_under_tasks_root(self, viability_tasks_root):
        specs = _discover_viability_tasks(viability_tasks_root, None, None)
        for s in specs:
            assert s.startswith("tasks/")
            assert s.endswith("/task.py")

    def test_specs_match_expected_pillars_and_order(self, viability_tasks_root):
        specs = _discover_viability_tasks(viability_tasks_root, None, None)
        assert specs == [
            "tasks/competence/q3-answer-the-question/task.py",
            "tasks/execution/q4-root-cause/task.py",
            "tasks/analysis/f1-multi-file-verify/task.py",
            "tasks/universal/u17-dirty-workspace-triage/task.py",
        ]

    def test_resolves_task_regardless_of_pillar(self, tmp_path, monkeypatch):
        # If q3-answer-the-question was moved to a different pillar, it should
        # still be found. We move it from competence/ to execution/ here.
        tasks = tmp_path / "tasks"
        for d in VIABILITY_TASK_DIRS:
            src = tasks / d
            src.mkdir(parents=True)
            (src / "task.py").write_text(
                "from inspect_ai import Task, task\n"
                "from inspect_ai.dataset import MemoryDataset\n"
                "@task\n"
                "def fixture_task():\n"
                "    return Task(dataset=MemoryDataset(samples=[]), scorer=None)\n"
            )
        # Move q3-answer-the-question to execution/
        (tasks / "competence" / "q3-answer-the-question").rename(
            tasks / "execution" / "q3-answer-the-question"
        )
        monkeypatch.chdir(tmp_path)
        specs = _discover_viability_tasks(tasks, None, None)
        # The first spec should now be under execution/, not competence/.
        assert specs[0] == "tasks/execution/q3-answer-the-question/task.py"

    def test_max_tasks_caps_results(self, viability_tasks_root):
        specs = _discover_viability_tasks(viability_tasks_root, max_tasks=2, task_filter=None)
        assert len(specs) == 2
        assert specs[0].endswith("q3-answer-the-question/task.py")
        assert specs[1].endswith("q4-root-cause/task.py")

    def test_max_tasks_zero_returns_empty(self, viability_tasks_root):
        specs = _discover_viability_tasks(viability_tasks_root, max_tasks=0, task_filter=None)
        assert specs == []

    def test_task_filter_selects_one(self, viability_tasks_root):
        specs = _discover_viability_tasks(
            viability_tasks_root, max_tasks=None, task_filter="q4-root-cause"
        )
        assert len(specs) == 1
        assert specs[0].endswith("q4-root-cause/task.py")

    def test_task_filter_no_match_returns_empty(self, viability_tasks_root):
        specs = _discover_viability_tasks(
            viability_tasks_root, max_tasks=None, task_filter="nonexistent-task"
        )
        assert specs == []

    def test_missing_task_raises_clear_error(self, missing_one_viability_task):
        with pytest.raises(Exception, match="f1-multi-file-verify") as exc_info:
            _discover_viability_tasks(missing_one_viability_task, None, None)
        msg = str(exc_info.value)
        assert "Update VIABILITY_TASKS" in msg
        assert "tasks/" in msg


# ---------------------------------------------------------------------------
# _discover_tasks with viability tier
# ---------------------------------------------------------------------------


class TestDiscoverTasksViabilityBranch:
    def test_viability_tier_routes_to_helper(self, viability_tasks_root):
        with patch(
            "bench_cli.run.core._discover_viability_tasks",
            wraps=_discover_viability_tasks,
        ) as mock:
            specs = _discover_tasks("viability")
        assert mock.called
        assert len(specs) == 4

    def test_quick_tier_unchanged(self, viability_tasks_root):
        # _discover_tasks("quick") should not be affected by the new branch.
        # It scans tasks/verification/ — none of which exist in this fixture,
        # so it returns an empty list. The point is the viability branch
        # doesn't shadow quick.
        specs = _discover_tasks("quick")
        assert specs == []

    def test_full_tier_unchanged(self, viability_tasks_root):
        # Similar: the viability branch must not affect the full tier.
        # The fixture has 4 tasks, but full scans specific pillar subdirs
        # (competence/execution/analysis/universal) — so it should find 4
        # but ordered by pillar subdir sort + task name sort, NOT in
        # VIABILITY_TASKS order.
        specs = _discover_tasks("full")
        assert len(specs) == 4
        # Order must NOT match VIABILITY_TASKS (which is a fixed curated order).
        viability_specs = _discover_viability_tasks(viability_tasks_root, None, None)
        assert specs != viability_specs
