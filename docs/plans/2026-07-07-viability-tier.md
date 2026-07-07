# Viability Tier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Load subagent-driven-development/SKILL.md (recommended) or executing-plans/SKILL.md to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--tier viability` to `bench run` as a third tier alongside `--tier quick` and `--tier full`. It runs a curated 4-task subset (one per pillar: competence/execution/analysis/universal) that gives a fast diagnostic answer to "is this model worth a full 34-task run?" Reuses the entire existing `bench run` machinery — no new probe code, no new modules, no new artifact formats.

**Architecture:** Add a `VIABILITY_TASKS` constant in `bench_cli/run/core.py`. Add a new branch at the top of `_discover_tasks()` that resolves the 4 task names by searching all pillar subdirs (so a future `tasks/` reorganization doesn't break this tier) and returns the 4 `tasks/<pillar>/<name>/task.py` paths in fixed order. Add `"viability"` to the `click.Choice` in `bench_cli/run/cli.py` and update the help text. Update `README.md` quick reference. Everything downstream — price gate, Inspect invocation, cross-run resume, heartbeat, `bench compare`, model card generation — is unchanged: a viability run is a `bench run` with a 4-task list. The 4 produced `.eval` logs are first-class and feed into `bench compare` and the same resume logic, so a later `--tier full` re-run picks up where viability left off.

**Tech Stack:** Python 3.10+ (running on 3.14 in the project `.venv`), Click 8, pytest, Inspect AI 0.3.210.

## Global Constraints

- Use the project `.venv`: `.venv/bin/python` and `.venv/bin/pytest`. No system python. (`AGENTS.md`)
- Scorers live in `scorers/` at repo root, imported as `from scorers import ...`. `bench_cli/scorers/` does NOT exist. (`AGENTS.md`)
- Models route through a LiteLLM proxy as `openai/<alias>`; `.env` holds credentials. (SB Operating Rules)
- `bench_cli/run/` is a package: `from bench_cli.run.core import ...`, not `from bench_cli.run import ...`. (SB Operating Rules)
- Reuse the existing `_discover_tasks` machinery: `Docker`-required task skip, `max_tasks` cap, `task_filter` suffix match, sorted output, relative paths.
- The viability subset is `verify_sh`-only (no LLM judge) — keep it that way. If a future change adds a judge-based task to `VIABILITY_TASKS`, add a comment in the constant explaining why.
- The 4 hardcoded task names must be searchable across any pillar subdir — do NOT hardcode the pillar path. A future `tasks/` reorganization must not break the viability tier.
- Default tier stays `"quick"`. Do not change the default.

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `bench_cli/run/core.py` | Add `VIABILITY_TASKS` constant. Add `_discover_viability_tasks()` helper. Branch in `_discover_tasks()` for `tier == "viability"`. | Modify |
| `bench_cli/run/cli.py` | Add `"viability"` to the `click.Choice` for `--tier`. Update help text. | Modify |
| `README.md` | Add `viability` tier to quick reference. | Modify |
| `tests/test_viability_tier.py` | New test file: tier discovery, missing-task error, CLI choice, `--list-tasks`, `--task` filter, end-to-end CliRunner. | Create |

No new production modules. No new probe code. No new artifact paths.

---

## Task 1: Implement the viability tier core (constant + discovery + tests)

**Files:**
- Modify: `bench_cli/run/core.py:18-30` (add `VIABILITY_TASKS` constant after `TIER_DIRS`)
- Modify: `bench_cli/run/core.py:99-160` (add `viability` branch + `_discover_viability_tasks` helper)
- Create: `tests/test_viability_tier.py` (new file, full test coverage)

**Interfaces:**
- Consumes: `Path("tasks")` (the existing tasks root), `VIABILITY_TASKS` (defined in same module), `click.ClickException` (for missing-task error)
- Produces:
  - `VIABILITY_TASKS: tuple[str, ...]` — 4 hardcoded task directory names, in fixed order
  - `_discover_viability_tasks(tasks_root: Path, max_tasks: int | None, task_filter: str | None) -> list[str]` — returns 4 Inspect task spec strings (e.g. `tasks/competence/q3-answer-the-question/task.py`)
  - `_discover_tasks(tier, ...)` — unchanged for `quick`/`full`; new `tier == "viability"` branch delegates to the helper

- [ ] **Step 1: Write the failing tests**

Create `tests/test_viability_tier.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_viability_tier.py -v`
Expected: ALL tests fail with `ImportError` (no `VIABILITY_TASKS`, no `_discover_viability_tasks`) or `AttributeError`.

- [ ] **Step 3: Add `VIABILITY_TASKS` constant to `bench_cli/run/core.py`**

In `bench_cli/run/core.py`, after the `TIER_DIRS` definition (around line 19), add:

```python
# Viability tier: a curated 4-task subset that demonstrates model viability
# across all 4 main pillars (competence / execution / analysis / universal)
# in a few minutes. Each task is verify_sh-based (deterministic, no judge
# variance), small-sample (4-7), no Docker, no agent. Use this to decide
# whether a model is worth a full 34-task run. Order is fixed: each task
# answers one pillar-level question (can you answer / reason / verify /
# handle real-world mess?).
VIABILITY_TASKS: tuple[str, ...] = (
    "q3-answer-the-question",      # competence:  can you actually answer the question?
    "q4-root-cause",               # execution:   can you reason about code, not just patch?
    "f1-multi-file-verify",        # analysis:    can you check claims against reality?
    "u17-dirty-workspace-triage",  # universal:   can you handle real-world mess?
)
```

- [ ] **Step 4: Add `_discover_viability_tasks` helper + branch in `_discover_tasks`**

In `bench_cli/run/core.py`, add the helper just before `_discover_tasks` (around line 95):

```python
def _discover_viability_tasks(
    tasks_root: Path,
    max_tasks: int | None,
    task_filter: str | None,
) -> list[str]:
    """Return Inspect task specs for the viability tier.

    Resolves each name in ``VIABILITY_TASKS`` by searching all pillar subdirs
    under ``tasks_root`` (not a fixed-pillar lookup), so a future ``tasks/``
    reorganization that moves a viability task to a different pillar won't
    break this tier. Raises ``click.ClickException`` if a hardcoded task
    name is missing — that means ``VIABILITY_TASKS`` is stale.

    Args:
        tasks_root: Path to the ``tasks/`` directory.
        max_tasks: If set, cap the returned list to this many entries.
        task_filter: If set, only include the task whose directory name matches.

    Returns:
        List of relative task spec paths, e.g.
        ``["tasks/competence/q3-answer-the-question/task.py", ...]``
    """
    specs: list[str] = []
    for name in VIABILITY_TASKS:
        if task_filter is not None and name != task_filter:
            continue
        found: Path | None = None
        for sub in sorted(p for p in tasks_root.iterdir() if p.is_dir()):
            candidate = sub / name / "task.py"
            if candidate.is_file():
                found = candidate
                break
        if found is None:
            raise click.ClickException(
                f"Viability task '{name}' not found under {tasks_root}/. "
                "Update VIABILITY_TASKS in bench_cli/run/core.py."
            )
        specs.append(str(found))
        if max_tasks is not None and len(specs) >= max_tasks:
            break
    return specs
```

Then update `_discover_tasks` to add the viability branch at the top (before the `TIER_DIRS.get` call):

```python
def _discover_tasks(
    tier: str,
    max_tasks: int | None = None,
    task_filter: str | None = None,
) -> list[str]:
    """Return Inspect-compatible task spec strings for the given tier.

    Scans the configured subdirectories under ``tasks/`` for ``task.py``
    files and returns them as relative paths that Inspect's ``eval()``
    can resolve (e.g. ``tasks/verification/smoke/task.py``).

    Tasks that require Docker (``sandbox="docker"``) are automatically
    skipped with a warning when Docker is not available.

    Parameters
    ----------
    tier:
        ``"quick"`` runs verification/smoke only; ``"full"`` runs all 34
        eval tasks across the 4 main pillars; ``"viability"`` runs a
        curated 4-task diagnostic subset (one per pillar).
    max_tasks:
        If set, cap the returned list to this many entries.
    task_filter:
        If set, select only the task whose directory name matches.
        Matches exactly (e.g. ``"smoke"`` matches only ``"smoke"`` and
        not ``"agent_smoke"``).  Use ``--list-tasks`` first to see all names.
    """
    tasks_root = Path("tasks")
    if tier == "viability":
        return _discover_viability_tasks(tasks_root, max_tasks, task_filter)
    dirs = TIER_DIRS.get(tier)
    if dirs is None:
        raise click.BadParameter(f"Unknown tier {tier!r}", param_hint="--tier")
    # ... rest of the function unchanged
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_viability_tier.py -v`
Expected: ALL tests pass.

- [ ] **Step 6: Run the full test suite to confirm no regression**

Run: `.venv/bin/pytest -x -q`
Expected: All tests pass, including the pre-existing 645-pass / 1-known-fail baseline.

- [ ] **Step 7: Commit**

```bash
git add bench_cli/run/core.py tests/test_viability_tier.py
git commit -m "feat(tiers): add --tier viability (4-task diagnostic subset)

Promotes the old NIM-viability probe concept to a first-class tier that
uses the existing bench run machinery (Inspect, scorers, resume, compare,
model cards) instead of a standalone probe script.

VIABILITY_TASKS = (q3-answer-the-question, q4-root-cause,
f1-multi-file-verify, u17-dirty-workspace-triage) — one per pillar,
verify_sh only, no Docker, no agent. _discover_tasks() routes the new
tier to _discover_viability_tasks() which searches all pillar subdirs so
the tier survives tasks/ reorganization.

The 4 produced .eval logs feed into bench compare and the same resume
logic as --tier full, so a later full-tier run picks up where viability
left off."
```

---

## Task 2: Wire up CLI surface (click Choice + help text + README + tests)

**Files:**
- Modify: `bench_cli/run/cli.py:114-121` (extend `click.Choice` + help text)
- Modify: `README.md:8-10` (add `viability` to quick reference)
- Modify: `tests/test_viability_tier.py` (add CLI surface tests)

**Interfaces:**
- Consumes: `click.Choice`, `bench_cli.run.cli.run` command
- Produces: `bench run --tier viability` works through the full CLI invocation; `bench run --help` lists the new tier; `bench run --tier viability --list-tasks` lists the 4 tasks

- [ ] **Step 1: Add failing tests for CLI surface**

Append to `tests/test_viability_tier.py`:

```python
# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


class TestViabilityCliSurface:
    def test_viability_in_click_choice(self):
        from bench_cli.run.cli import run

        # Walk the Click options on the `run` command and find the --tier option.
        tier_param = next(p for p in run.params if p.name == "tier")
        assert "viability" in tier_param.type.choices

    def test_help_text_mentions_viability(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "viability" in result.output

    def test_list_tasks_viability(self, viability_tasks_root):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--tier", "viability", "--list-tasks"])
        assert result.exit_code == 0, result.output
        assert "q3-answer-the-question" in result.output
        assert "q4-root-cause" in result.output
        assert "f1-multi-file-verify" in result.output
        assert "u17-dirty-workspace-triage" in result.output
        assert "4 task(s) found" in result.output

    def test_unknown_tier_still_rejected(self, viability_tasks_root):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--tier", "bogus", "--list-tasks"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "Unknown tier" in result.output
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `.venv/bin/pytest tests/test_viability_tier.py::TestViabilityCliSurface -v`
Expected: The 4 new tests fail. `test_viability_in_click_choice` and `test_help_text_mentions_viability` fail because `"viability"` is not yet in the choice. `test_list_tasks_viability` and `test_unknown_tier_still_rejected` may also fail (the latter is a regression guard — it might already pass; that's fine).

- [ ] **Step 3: Update `--tier` option in `bench_cli/run/cli.py`**

Find the existing `--tier` option (around line 114) and replace it:

Before:
```python
@click.option(
    "--tier",
    type=click.Choice(["quick", "full"]),
    default="quick",
    show_default=True,
    help="Task tier: quick (verification) or full (all eval tasks).",
)
```

After:
```python
@click.option(
    "--tier",
    type=click.Choice(["quick", "full", "viability"]),
    default="quick",
    show_default=True,
    help=(
        "Task tier: quick (verification smoke only), full (all 34 eval tasks), "
        "or viability (4-task diagnostic subset, one per pillar, ~3-8 min)."
    ),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_viability_tier.py::TestViabilityCliSurface -v`
Expected: All 4 new tests pass.

- [ ] **Step 5: Update README quick reference**

In `README.md`, find the quick reference block (around line 8-12) and add a `viability` example. Insert after the existing `python -m bench_cli run --concurrency 4 --tier full` line:

```bash
python -m bench_cli run --tier viability --model openai/<new-model>  # 4-task diagnostic pass
```

Keep the comment terse — one line.

- [ ] **Step 6: Run the full test suite**

Run: `.venv/bin/pytest -x -q`
Expected: All tests pass (645+ baseline + new viability tests).

- [ ] **Step 7: Verify the CLI end-to-end with `--list-tasks`**

Run: `.venv/bin/python -m bench_cli run --tier viability --list-tasks`
Expected output (abbreviated):
```
Tasks available for tier 'viability':
  (use --tier to filter; default is 'quick')

  tasks/competence/q3-answer-the-question/task.py
  tasks/execution/q4-root-cause/task.py
  tasks/analysis/f1-multi-file-verify/task.py
  tasks/universal/u17-dirty-workspace-triage/task.py

4 task(s) found. Run one with --task <name>.
```

- [ ] **Step 8: Commit**

```bash
git add bench_cli/run/cli.py README.md tests/test_viability_tier.py
git commit -m "feat(cli): add viability to --tier click.Choice + help + README

Surfacing the new --tier viability option that was implemented in the
previous commit. The 4 produced .eval logs are first-class and feed
into bench compare and the same resume logic as --tier full."
```

---

## Verification

After both tasks:

```bash
# All tests pass
.venv/bin/pytest -x -q

# --list-tasks works
.venv/bin/python -m bench_cli run --tier viability --list-tasks

# Help text mentions viability
.venv/bin/python -m bench_cli run --help | grep -i viability

# Unknown tier still rejected
.venv/bin/python -m bench_cli run --tier bogus  # exits non-zero
```

Manual smoke (optional, requires a working model + proxy): run viability on a known model and confirm:
1. 4 .eval logs land in `logs/`
2. `bench compare` shows the model in the pivot table with 4 task columns
3. `bench run --tier full --model <same>` resumes past the 4 already-done tasks

---

## Out of Scope

- Agent-mode viability (the 4 tasks are model-only). If a future need arises, add a comment to `VIABILITY_TASKS` and a follow-up task.
- Viability-specific model card. The existing card generation handles partial data fine; no change needed.
- Removing the old `scripts/probe_nim_routes.py` and `scripts/report_viability.py`. Those are retired by this change but the deletion is a separate commit for a future cleanup pass — the user may still have workflows pointing at them. (Per the brainstorming decision: the goal is to retire them organically by making the new tier the obvious tool. Explicit deletion can come later.)
- Adding more viability tasks. The 4 are a deliberate minimum; adding more changes the runtime budget materially and is a different design discussion.
