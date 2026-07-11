# Phase 2 — Harder Tasks (B2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Load subagent-driven-development/SKILL.md (recommended) or executing-plans/SKILL.md to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Source ~10 new evaluation tasks that discriminate in the cluster ability band where current 34-task suite has hit its ceiling. After Phase 2, the suite is ~44 tasks, giving the Phase 3 IRT engine enough items to model ability differences in the band where current models cluster.

**Architecture:** Additive task authoring into the existing `tasks/<pillar>/<task-name>/` layout. Each new task has the same shape as the existing 34: `task.py` (Inspect `@task`), `dataset.json` (`{input, target, id}`), and `verify.sh` (deterministic). No changes to `bench_cli/` or scorers. Reference costs are added to `scorers/task_budgets.py` from a minimax m3 baseline run.

**Tech Stack:** Python 3.14, Inspect AI 0.3.245, existing scorers in `scorers/`, bash for `verify.sh`. The new tasks MUST be deterministic (`verify_sh`-only — no LLM judge) to keep calibration tight at the discrimination band.

## Global Constraints

- Use the project `.venv`: `.venv/bin/python` and `.venv/bin/pytest`. No system python. (`AGENTS.md`)
- Scorers live in `scorers/` at repo root; new tasks use the existing four scorers in the same order as the existing exemplar `tasks/competence/q3-answer-the-question/task.py` — `verify_sh, token_ratio, time_ratio, price_ratio`.
- `verify.sh` MUST be executable (`chmod +x` at authoring time). Scorer checks `os.access(script_path, os.X_OK)`. POSIX regex only — `grep -E`, `[[:space:]]` not `\s`.
- New tasks have NO existing logs, so `bench run`'s resume logic won't trip them — BUT `--no-resume` is **mandatory for all Phase 2 full-eval runs** per spec. Use `--no-resume`. The verification step at the end of Phase 2 counts new `.eval` files matching the new task names and asserts the expected count.
- All new tasks are `verify_sh`-only (deterministic). No LLM judge for B2 — keep calibration tight at the discrimination band. If a candidate needs judge variance, drop it (find a different candidate).
- Pillar distribution per spec: 2–3 new tasks per pillar. Aim for 10 total. Each new task must have ≥4 distinct distractors verified by the author.
- Source-first strategy per spec: **port from SWE-bench-Verified / MMLU-Pro coding subset**. Author original only if porting does not yield clean fits. Each port must be a real coding problem solvable by reading code + reasoning about a small change, NOT a quiz question.
- Recorded-identity handling: `bench_cli/results/core.py:49::is_moniker_alias` is the existing helper. Tasks inherit this through `bench_cli.compare` automatically; no task-level changes needed.
- Run resume gotcha: after a scorer change, `bench_cli/score.py` refactor (Phase 0), `task_budgets.py` change in this phase, or any verify.sh edit, ALL logs for that (model, task) pair become stale. The new tasks have no logs so this only matters for the `--no-resume` verification step (must equal `16 × 10`).
- Task discovery is automatic from `tasks/<pillar>/<task-name>/task.py`. New tasks appear in `--tier full` runs as soon as the directory + `task.py` exist — no CLI/registry changes.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `docs/decisions/2026-07-11-b2-task-candidates.md` | Decision doc: 10 candidate tasks, sources, pillar mapping, discriminative rationale | Create (Task 1) |
| `tasks/<pillar>/<task-name>/task.py` | Inspect `@task` (one per new task) | Create (Task 2, 3, 4) |
| `tasks/<pillar>/<task-name>/dataset.json` | `{input, target, id}` samples | Create (Task 2, 3, 4) |
| `tasks/<pillar>/<task-name>/verify.sh` | Deterministic grader, `chmod +x` | Create (Task 2, 3, 4) |
| `scorers/task_budgets.py` | Add `reference_cost_usd` for each new task | Modify (Task 5) |
| `tests/test_b2_tasks.py` | Discovery + executable + verify.sh-script-shape tests | Create (Task 6) |

No CLI changes. No `bench_cli/` changes for Phase 2.

---

## Task 1: Author the B2 candidate decision document

**Files:**
- Create: `docs/decisions/2026-07-11-b2-task-candidates.md`

**Why this exists:** Phase 2's "ship 10 tasks" deliverable is gated on a thoughtful list. Without a written decision doc, the choice drifts mid-plan and the discriminative rationale disappears. The doc is the contract — it commits which 10 tasks and why, before any task.py is opened.

- [ ] **Step 1: Ensure the decisions directory exists and draft the candidate list**

```bash
mkdir -p docs/decisions
```

Write `docs/decisions/2026-07-11-b2-task-candidates.md` with this shape:

```markdown
# B2 Task Candidates (Phase 2)

**Author:** <your name>
**Date:** 2026-07-11
**Source priority:** port from SWE-bench-Verified / MMLU-Pro coding subset; original only if porting yields none.

## Selection criteria

A task discriminates in the cluster ability band when:
1. The gold answer exists in code (verifiable by shell, no judge variance).
2. There are ≥4 distinct distractors that look surface-correct but fail a precise check.
3. Difficulty lands inside the cohort capability band (mean θ from prior IRT runs would be
   in the cluster — currently estimated 0.6–0.8 capability).
4. It is solvable in <300 tokens of output (cheap to run, cap-able to fail cheap models).

## Candidates

| # | Task name | Pillar | Source | URL | Discriminative rationale |
|---|-----------|--------|--------|-----|--------------------------|
| 1 | b2-multi-file-rename-with-test-gate | execution | SWE-bench-Verified | ... | Forces planning across 3 files AND verifies a test gate fails-pass -> distinguish strong planners from surface patchers |
| 2 | b2-import-cycle-detect | analysis | MMLU-Pro coding | ... | Reads 4 Python modules, identifies the import cycle precisely, names the offending module |
| 3 | b2-migration-sqlite-to-postgres | execution | SWE-bench-Verified | ... | Diff-aware: must preserve query semantics, but apply Postgres-specific syntax. Distract model that ports verbatim |
| 4 | b2-dependency-audit-with-typo | analysis | original | ... | List deps from pyproject.toml; flag one dep with a typo'd import path; strong models catch it, weak models assume it exists |
| 5 | b2-three-way-merge-conflict | execution | SWE-bench-Verified | ... | Resolve a 3-way merge conflict marker with two correct resolutions and a wrong-looking fix |
| 6 | b2-context-budget-stayed-within | universal | original | ... | Output must fit within a token budget; weak models pad with explanation, fail |
| 7 | b2-read-then-write-schema-fix | competence | SWE-bench-Verified | ... | Read a JSON schema, identify one field typo, write back the corrected file |
| 8 | b2-prompt-injection-defence-rigorous | universal | original | ... | Output must include explicit detection AND must not produce the injected request. Multiple distractors that pass surface checks |
| 9 | b2-flaky-test-stabilisation | competence | SWE-bench-Verified | ... | Diagnose ordering flake, fix with deterministic seed |
| 10 | b2-license-header-with-year | execution | original | ... | Add SPDX header with correct year-derived-from-current-date. Distractor: hardcoded year that ages out |

## Pillar distribution

- analysis: 3 (#2, #4, ...)
- competence: 2 (#7, #9, ...)
- execution: 3 (#1, #3, #5, #10, ...)
- universal: 2 (#6, #8, ...)
Total = 10.

## Discriminative rationale summary

Each candidate targets a specific failure mode of the cohort at current capability
levels. The estimated separation between strong (kimi-k2.7-code) and weak (gemma-local)
baselines should be ≥0.4 correctness difference on each task. If pilot calibration
(Task 2.5) shows lower separation, swap that candidate for the next runner-up.

## Anti-patterns avoided

- No quiz questions (multiple-choice with no real code reading).
- No tasks solvable by `cat README.md` — every task requires reading actual code.
- No LLM-judge tasks for B2 (would compound variance at the cluster band).
- No tasks where a single correct answer is "produce something" — every task has
  a deterministic shell-level check.
```

The 10 task names above are placeholders. Replace with real candidates at authoring time. The exact URLs from SWE-bench-Verified are looked up live; do not guess.

- [ ] **Step 2: Commit the decision doc**

```bash
git add docs/decisions/2026-07-11-b2-task-candidates.md
git commit -m "docs(b2): candidate task list with discriminative rationale"
```

- [ ] **Step 3: Verify doc covers Pillar distribution = 2-3 per pillar**

Read the doc back. Confirm 10 candidates total, 2-3 per pillar, with discriminative rationale per candidate.

---

## Task 2: Pilot one task end-to-end

**Files:**
- Create: `tasks/<pillar>/<first-pilot-task>/task.py`
- Create: `tasks/<pillar>/<first-pilot-task>/dataset.json`
- Create: `tasks/<pillar>/<first-pilot-task>/verify.sh`
- Create: `tasks/<pillar>/<first-pilot-task>/fixtures/` (if needed)

**Why pilot first:** Authoring all 10 then running is a 10x blast radius. Pilot one and run pilot on strong + weak baseline to verify discriminative separation before scaling out. If separation is below target, swap the candidate before authoring 9 more.

**Pilot target:** task #1 from the decision doc (the highest-confidence discriminative candidate).

- [ ] **Step 1: Author `task.py` modelled on `tasks/competence/q3-answer-the-question/task.py`**

Use this skeleton (`<pillar>`, `<task-name>` are concrete values; substitutions are inside `{{ }}` for clarity):

```python
"""{{Task title}} — {{one-sentence discriminative rationale}}."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def {{task_function_name}}():
    """{{Long description.}}"""
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            verify_sh(),
            token_ratio_scorer(task_budget=get_task_budget("{{task_name_in_task_budgets}}")),
            time_ratio_scorer(task_budget=get_task_budget("{{task_name_in_task_budgets}}")),
            price_ratio_scorer(task_budget=get_task_budget("{{task_name_in_task_budgets}}")),
        ],
    )
```

Make `{{task_function_name}}` match the existing convention — snake_case that mirrors the directory name (e.g., `b2_multi_file_rename_with_test_gate`). The `"{{task_name_in_task_budgets}}"` key matches the directory name verbatim (e.g., `b2-multi-file-rename-with-test-gate`).

- [ ] **Step 2: Author `dataset.json` with ≥4 distinct distractors**

≥4 samples (one per scenario) where each has a deterministic ground truth and at least one designed distractor that looks plausible. Format mirrors `tasks/competence/q3-answer-the-question/dataset.json`:

```json
[
  {
    "id": "<sample-1>",
    "input": "<prompt with exact instructions for what model should output>",
    "target": "<ground truth keyword or phrase>"
  },
  ...
]
```

- [ ] **Step 3: Author `verify.sh` as a deterministic shell script**

Use `tasks/competence/q3-answer-the-question/verify.sh` as the template. Adapt:
- Read response from stdin (`cat > "$STDIN_FILE"`).
- Run several deterministic checks (e.g., 4 checks for 4 distinct requirements).
- Print `PASS X/Y` on success, `FAIL` + diagnostics on failure.
- TOTAL_CHECKS matches the number of checks.
- All grep uses `-E` (POSIX ERE), `[[:space:]]` for whitespace.
- Bail on first hard error with `set -euo pipefail`.

After writing:

```bash
chmod +x tasks/<pillar>/<first-pilot-task>/verify.sh
```

Verify:

```bash
ls -la tasks/<pillar>/<first-pilot-task>/verify.sh   # must show -rwxr-xr-x
```

- [ ] **Step 4: Manual verify.sh smoke test**

Run the verify.sh against a known-good response and a known-bad response, manually:

```bash
echo "expected response content" | bash tasks/<pillar>/<first-pilot-task>/verify.sh
# Expected: PASS 4/4 or similar

echo "wrong response" | bash tasks/<pillar>/<first-pilot-task>/verify.sh
# Expected: FAIL with diagnostics explaining which check failed
```

Verify both before proceeding.

- [ ] **Step 5: Run pilot on strong + weak baseline**

Run the pilot task on TWO models (one strong, one weak) to verify discriminative separation:

```bash
.venv/bin/python -m bench_cli run --model openai/kimi-k2.7-code --task <task-name> --no-resume
.venv/bin/python -m bench_cli run --model openai/gemma-local --task <task-name> --no-resume
```

Compare per-sample correctness between the two. **Target:** separation ≥ 0.4 correctness difference. If less, swap the candidate per the decision doc's anti-patterns.

If the pilot fails separation:
- Stop, swap the candidate, redo Task 2 from Step 1 with the new candidate.
- Update `docs/decisions/2026-07-11-b2-task-candidates.md` to mark the swap.

- [ ] **Step 6: Commit the pilot task**

```bash
git add tasks/<pillar>/<first-pilot-task>/
git commit -m "task(b2): first pilot — <task-name>"
```

---

## Task 3: Author tasks in 3 batches of 3 (pilots #2, #3, #4)

**Files:** Per task — `task.py`, `dataset.json`, `verify.sh` (chmod +x). Run pilot separation on each before committing.

- [ ] **Step 1: Batch A — author tasks #2 and #3 from the decision doc in parallel**

Same workflow as Task 2, but process two tasks in parallel (one agent-driven, one author-driven). For each:
- Author `task.py`, `dataset.json`, `verify.sh`.
- `chmod +x verify.sh`.
- Manual verify.sh smoke (good + bad response).
- Pilot run on kimi + gemma-local; assert ≥0.4 separation.
- Commit.

Commit messages:

```bash
git add tasks/<pillar>/<task2-name>/ tasks/<pillar>/<task3-name>/
git commit -m "task(b2): batch A — <task2-name>, <task3-name>"
```

- [ ] **Step 2: Batch B — tasks #4 and #5**

Same protocol as Step 1.

```bash
git add tasks/<pillar>/<task4-name>/ tasks/<pillar>/<task5-name>/
git commit -m "task(b2): batch B — <task4-name>, <task5-name>"
```

- [ ] **Step 3: Batch C — tasks #6, #7, #8**

Same protocol as Step 1 (3 tasks this batch to keep load even).

```bash
git add tasks/<pillar>/<task6-name>/ tasks/<pillar>/<task7-name>/ tasks/<pillar>/<task8-name>/
git commit -m "task(b2): batch C — <task6-name>, <task7-name>, <task8-name>"
```

- [ ] **Step 4: Interim discovery check**

After Batches A–C land, verify all 9 (1 pilot + 3 + 2 + 3) new tasks are discoverable:

```bash
.venv/bin/python -m bench_cli run --tier full --list-tasks | wc -l
```

This line count should have grown by ~9 (from 34 → ~43). If fewer, a task file is missing `task.py` or the `@task` decorator.

- [ ] **Step 5: Commit batch as it lands; do not bundle batches across commits**

Each batch (A, B, C) is its own commit, per step messages.

---

## Task 4: Author the final task (#9, #10)

**Files:** Per task — `task.py`, `dataset.json`, `verify.sh`.

- [ ] **Step 1: Author task #9 and task #10**

Same protocol as Task 2.

```bash
git add tasks/<pillar>/<task9-name>/ tasks/<pillar>/<task10-name>/
git commit -m "task(b2): final batch — <task9-name>, <task10-name>"
```

- [ ] **Step 2: Full discovery check**

```bash
.venv/bin/python -m bench_cli run --tier full --list-tasks | wc -l
```

Target line count: original 34 + 10 new = 44 tasks.

- [ ] **Step 3: Pillar distribution audit**

Confirm each pillar has 2-3 new tasks:

```bash
.venv/bin/python -c "
from pathlib import Path
for pillar in ['analysis', 'competence', 'execution', 'universal']:
    n = sum(1 for p in Path('tasks', pillar).iterdir() if p.is_dir())
    print(f'{pillar}: {n} tasks')
"
```

Compare against the pre-Phase-2 counts (analysis=7, competence=9, execution=10, universal=8 → 34 tasks total). Expect each pillar to have grown by 2 or 3.

- [ ] **Step 4: Commit audit (no code change; advisory commit)**

If the audit reveals a missing pillar slot, open a follow-up commit adding the task. Otherwise skip.

---

## Task 5: Calibrate `reference_cost_usd` for the new tasks

**Files:**
- Modify: `scorers/task_budgets.py`

**Why this exists:** The cost pillar uses `reference_cost_usd` per task to compute `price_ratio = reference / actual`. The existing 34 tasks have these calibrated from a prior minimax m3 run; the 10 new ones need the same calibration pass before the cost pillar can score them sensibly.

- [ ] **Step 1: Run the new tasks on minimax m3**

```bash
.venv/bin/python -m bench_cli run --model openai/minimax-m3 --no-resume
```

This produces 10 new `.eval` logs (one per new task). The `--no-resume` is mandatory.

- [ ] **Step 2: Extract per-task avg_cost_usd from the new logs**

```bash
.venv/bin/python - <<'PY'
import zipfile, json, math
from pathlib import Path

for p in sorted(Path("logs").rglob("*.eval")):
    if any(name in p.name for name in [
        "b2-multi-file-rename-with-test-gate",
        "b2-import-cycle-detect",
        # ... all 10 new task names ...
    ]):
        try:
            with zipfile.ZipFile(p) as z:
                if "header.json" not in z.namelist():
                    continue
                # Take the eval task name from the header
                h = json.loads(z.open("header.json").read().decode())
                # Sample-level cost comes from samples — extract avg cost
                # ... (use a small helper script; do not inline here)
        except Exception as e:
            print(f"SKIP {p}: {e}")
PY
```

The exact extraction logic mirrors what `bench_cli.compare` already does. To avoid reinventing it, write a small helper script that imports the existing `load_compare_data` and prints one line per B2 task with `avg_cost_usd`, `avg_tokens`, and `avg_time`. Create `scripts/extract_b2_costs.py`:

```python
#!/usr/bin/env python3
"""Extract per-task efficiency averages from .eval logs for new B2 tasks.

Usage: .venv/bin/python scripts/extract_b2_costs.py [--log-dir logs] [--model minimax-m3]

Prints tab-separated lines per (model, task) for tasks whose directory
starts with 'b2-'. Pipe into a Python dict literal for `task_budgets.py`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench_cli.compare.core import load_compare_data
from bench_cli.results.core import is_moniker_alias  # noqa: F401 -- used downstream


def _b2_task_filter(task: str) -> bool:
    return task.startswith("b2-")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument(
        "--model",
        default="minimax-m3",
        help="Reference model whose avg cost will seed reference_cost_usd.",
    )
    args = parser.parse_args()

    data = load_compare_data(args.log_dir)
    b2_tasks = [t for t in data.tasks if _b2_task_filter(t)]

    out_rows: list[tuple[str, float, float, float]] = []
    for task in b2_tasks:
        models_to_cost = data.matrix.get(task, {})
        for model, ps in models_to_cost.items():
            if is_moniker_alias(model):
                continue
            # Use the requested --model first; fall back to first concrete.
            if model == args.model or not out_rows:
                out_rows.append((
                    task,
                    ps.avg_cost_usd if ps.avg_cost_usd == ps.avg_cost_usd else float("nan"),
                    ps.avg_tokens,
                    ps.avg_time,
                ))
                break

    # Tab-separated output. Engineer copies into task_budgets.py.
    print("task_name\\tavg_cost_usd\\tavg_tokens\\tavg_time")
    for task, cost, tokens, time_s in out_rows:
        print(f"{task}\\t{cost:.6f}\\t{tokens:.1f}\\t{time_s:.2f}")


if __name__ == "__main__":
    main()
```

For plan-level brevity, the deliverable is: extract 10 (task_name, avg_cost_usd) pairs and apply them to `task_budgets.py`.

- [ ] **Step 3: Update `scorers/task_budgets.py`**

Add one new entry per new task to `scorers/task_budgets.py`. Match the existing dict literal at the top of the module (around line 24). Use the values from the script above; round `reference_cost_usd` to the nearest 1e-6:

```python
    "<task-directory-name>": TaskBudget(
        output_tokens=<avg_tokens from Step 2>,
        latency_seconds=<avg_time from Step 2>,
        reference_cost_usd=<avg_cost_usd from Step 2 rounded to nearest 1e-6>,
    ),
```

If multiple minimax-m3 samples exist for a B2 task, use the mean across samples. `output_tokens` and `latency_seconds` come from the script's last two columns.

- [ ] **Step 4: Sanity-check pricing appears in compare**

Run the compare JSON path on the minimax-m3 logs and confirm the new tasks now appear; the per-row `price_ratio` value will be populated automatically by the existing `scorers/price_ratio.py` resolution chain when compare loads the log:

```bash
.venv/bin/python -m bench_cli compare --json 2>&1 | python -c "
import json, sys
data = json.loads(sys.stdin.read())
b2 = [r for r in data if r['task'].startswith('b2-') and 'minimax' in r['model'].lower()]
print(f'B2 rows for minimax-m3: {len(b2)}')
for row in sorted(b2, key=lambda r: r['task']):
    print(f\"  {row['task']:<40} cost_usd={row['avg_cost_usd']}  price_ratio={row['price_ratio']}\")
"
```

Expected: 10 rows (one per B2 task) with non-null `price_ratio`. If `price_ratio` is null, the new task is missing from `task_budgets.py` — re-check Step 3.

- [ ] **Step 5: Commit**

```bash
git add scorers/task_budgets.py scripts/extract_b2_costs.py
git commit -m "feat(budgets): reference_cost_usd for B2 task set + extract helper"
```

---

## Task 6: B2 task discovery tests + verification helper

**Files:**
- Create: `tests/test_b2_tasks.py`

**Why this exists:** Once 10 new tasks exist, regression protection matters: a future reorganization of `tasks/` must not silently drop them from `--tier full` discovery. These tests guard against that.

- [ ] **Step 1: Write the test file**

Create `tests/test_b2_tasks.py`:

```python
"""Discovery + executable-bit + verify.sh shape tests for B2 tasks.

Per the Phase 2 plan, every new B2 task must:
  1. Live under tasks/<pillar>/<task-name>/ with task.py + verify.sh + dataset.json.
  2. Have an executable verify.sh (os.access(..., os.X_OK)).
  3. Have a dataset.json that decodes as a JSON list with required keys.
  4. Have a task.py that exposes @task-decorated callables.

The test below scans the b2-* directory entries and asserts each task satisfies
the four invariants above.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


_TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"


def _b2_task_dirs() -> list[Path]:
    out: list[Path] = []
    for pillar in ("analysis", "competence", "execution", "universal"):
        for p in (_TASKS_ROOT / pillar).iterdir():
            if p.is_dir() and p.name.startswith("b2-"):
                out.append(p)
    return sorted(out)


def test_b2_tasks_count_is_at_least_8():
    """Phase 2 ships ~10 tasks; conservative floor at 8 to allow for swaps."""
    assert len(_b2_task_dirs()) >= 8, (
        f"expected ≥8 B2 tasks, found {len(_b2_task_dirs())}: "
        f"{[p.name for p in _b2_task_dirs()]}"
    )


def test_b2_tasks_have_required_files():
    """Every B2 task has task.py, dataset.json, verify.sh."""
    for p in _b2_task_dirs():
        for name in ("task.py", "dataset.json", "verify.sh"):
            assert (p / name).is_file(), f"missing {name} in {p}"


def test_b2_verify_sh_is_executable():
    """verify.sh must be chmod +x — scorer checks this at runtime."""
    for p in _b2_task_dirs():
        verify = p / "verify.sh"
        assert os.access(verify, os.X_OK), f"verify.sh not executable in {p}"


def test_b2_dataset_json_well_formed():
    """dataset.json must parse, be a list, every sample has input/target/id."""
    for p in _b2_task_dirs():
        ds = p / "dataset.json"
        with ds.open() as f:
            data = json.load(f)
        assert isinstance(data, list), f"dataset.json not a list in {p}"
        assert data, f"dataset.json empty in {p}"
        for sample in data:
            for key in ("input", "target", "id"):
                assert key in sample, f"sample missing {key} in {p}"
        # Each id must be unique.
        ids = [s["id"] for s in data]
        assert len(ids) == len(set(ids)), f"duplicate ids in {p}"


def test_b2_task_py_has_decorated_callable():
    """task.py exposes ≥1 @task-decorated callable (Inspect discovery)."""
    for p in _b2_task_dirs():
        text = (p / "task.py").read_text()
        # Regex matches the @task decorator followed by `def <name>():`
        assert re.search(r"^@task\s*$", text, re.MULTILINE), \
            f"no @task decorator in {p}/task.py"


def test_b2_pillar_distribution_in_range_2_to_3():
    """Per-pillar distribution: each pillar grew by 2-3 tasks."""
    counts: dict[str, int] = {}
    for pillar in ("analysis", "competence", "execution", "universal"):
        counts[pillar] = sum(
            1 for p in (_TASKS_ROOT / pillar).iterdir()
            if p.is_dir() and p.name.startswith("b2-")
        )
    for pillar, n in counts.items():
        assert 2 <= n <= 3, f"{pillar} pillar has {n} B2 tasks (expected 2-3)"
```

- [ ] **Step 2: Run tests — confirm pass**

Run: `.venv/bin/pytest tests/test_b2_tasks.py -v`
Expected: all 6 tests pass after Tasks 1–5 are complete (10 B2 tasks in `tasks/<pillar>/`).

- [ ] **Step 3: Run full suite — confirm no regressions**

Run: `.venv/bin/pytest -q`
Expected: full suite green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_b2_tasks.py
git commit -m "test(b2): B2 task discovery + executable + shape tests"
```

---

## Task 7: Full-eval run for 16 models with `--no-resume`

**Files:** No new files; this task produces ~160 new `.eval` logs in `logs/`.

**Why this exists:** The PRD Test Plan locks Phase 2's success criteria item #10 (`≥8 new tasks classified high-discrimination by IRT`) but the IRT engine itself is Phase 3. Phase 2 only delivers the data — the classification lands in Phase 3. So Phase 2's run produces the **inputs**; Phase 3 verifies the discrimination.

- [ ] **Step 1: Build the 16-model run list**

The "16" is illustrative — the actual cohort is whatever set of models currently has full-eval coverage across the 34 baseline tasks (`MIN_FULL_EVAL_TASKS`). Derive the concrete list at session time from the existing logs rather than hardcoding it, with the viability tier (added 2026-07-07) as a useful prior. Run from the project root:

```bash
.venv/bin/python -c "
from pathlib import Path
import re
counts: dict[str, int] = {}
for p in Path('logs').rglob('*.eval'):
    # Naming convention: <task-name>_<model>_<date>.eval or similar.
    # Pull task-name using the existing convention (excludes date suffix).
    m = re.match(r'(\d{4}-\d{2}-\d{2})_([a-z0-9-]+)_', p.name)
    if not m:
        continue
    task = m.group(2)
    counts[task] = counts.get(task, 0) + 1
# Models with coverage on >= 34 distinct task directories.
# Use the cohort from the most recent full-eval cycle as a starting point.
print('\n'.join(sorted(counts.keys())))
"
```

Capture the output as `MODELS` for Step 2. The candidates from viability are: kimi, mimo, deepseek-v4-pro, minimax-m3, qwen3.5-max, glm-5.2 (subject to current LiteLLM proxy config at `~/dev/litellm/config.yaml`). Drop any model that fails the viability smoke before the full run.

If fewer than 10 concrete models are available, document it in the session handoff and proceed with what is — the SC10 floor is "≥8 tasks classified high-discrimination", not "≥16 models × 10 tasks".

- [ ] **Step 2: Run `--no-resume` per model in parallel where possible**

```bash
# Use the captured MODELS list from Step 1.
while read -r model; do
    [[ -z "$model" || "$model" == \#* ]] && continue
    echo "RUNNING $model"
    .venv/bin/python -m bench_cli run --model "openai/$model" --no-resume
done <<< "$MODELS"
```

`-j` parallelism may be set per the speedup backlog. Do not exceed LiteLLM proxy RPM limits (see `~/dev/litellm/config.yaml` for `enforce_model_rate_limits`). Run sequentially when proxy RPM is at risk; parallel only after a single smoke run confirms safety.

- [ ] **Step 3: Count new logs written**

```bash
.venv/bin/python -c "
from pathlib import Path
new_tasks = [p.parent.name for p in Path('tasks').rglob('task.py')
             if p.parent.name.startswith('b2-')]
hits = []
for p in Path('logs').rglob('*.eval'):
    for name in new_tasks:
        if name in p.name:
            hits.append(p.name)
            break
print(f'new task logs: {len(hits)}')
print('unique task names logged:', len({h for h in hits for n in new_tasks if n in h}))
"
```

**Verification:** `len(hits) == N_models × 10 tasks` (allow ±10 for transient network errors — retry failures individually). If short, the `--no-resume` hypothesis is the first thing to check (per spec's CRITICAL EXECUTION NOTE in section 2A).

- [ ] **Step 4: Distribution check**

Confirm each of the 10 tasks has logs from N_models models. If any task has 0 logs, re-run that one task for the missing models only (`bench run --model openai/<m> --task <task>`).

- [ ] **Step 5: Commit (none — logs live in `logs/` which is gitignored or not tracked depending on repo config)**

If `logs/` is in `.gitignore`, there's nothing to commit. If not, do not bulk-commit 160 files — add `logs/` to `.gitignore` if not already there.

---

## Task 8: README + handoff updates

**Files:**
- Modify: `README.md` (suite size: 34 → 44 tasks; mention `--tier full` now includes B2)
- Modify: `docs/plans/2026-07-11-phase-0-rescore-and-capability-default.md` ("Next" pointer to Phase 3)

- [ ] **Step 1: Update task count in `README.md`**

Find the "Suite size" line in the README quick reference and update from `34 tasks` to `44 tasks (34 baseline + 10 B2 discrimination tasks)`.

- [ ] **Step 2: Update second-brain handoff (via `brain-ctl`)**

After the session ends, run:

```bash
brain-ctl sessions:append bench <session-id> --work-done "Phase 2 shipped: 10 B2 tasks added (tasks/<pillar>/b2-*/), reference costs calibrated, 160 new logs in-place. Suite now 44 tasks; Phase 3 IRT can begin."
```

For per-task status changes:

```bash
# Step 2.1: capture current task IDs from the live state.
brain-ctl tasks:list bench --filter status=active
# Identify the row whose text starts with "bench: add harder discriminating tasks".
# Capture its `id` field — that's the correctness-ceiling task to close.
CEILING_TASK_ID=<id from above, e.g. 29b2501c>

brain-ctl tasks:close bench "$CEILING_TASK_ID"    # correctness ceiling (PHASE 2 supersedes)
brain-ctl tasks:create bench "Phase 3 — IRT engine" --priority high
```

Exact IDs are looked up from `brain-ctl tasks:list bench --filter status=active`. Insert as needed.

- [ ] **Step 3: Commit README update**

```bash
git add README.md
git commit -m "docs: B2 suite is 44 tasks total"
```

---

## Done Criteria

- [ ] All 8 tasks shipped. **≥8 new `b2-*` task directories** under `tasks/<pillar>/` (per `test_b2_tasks_count_is_at_least_8`; aim for 10, but a task can be swapped per the pilot calibration in Task 2 Step 5).
- [ ] Decision doc at `docs/decisions/2026-07-11-b2-task-candidates.md` lists the 10 candidates with rationale.
- [ ] Every new task has: executable `verify.sh`, valid `dataset.json` (≥4 samples, unique ids), `@task`-decorated callable in `task.py`.
- [ ] `scorers/task_budgets.py` has `reference_cost_usd` for each new task.
- [ ] `tests/test_b2_tasks.py` exists and all 6 tests pass.
- [ ] 160 new `.eval` logs in `logs/`. Per-task count ≈ 16 models.
- [ ] Pillar distribution: 2-3 new tasks per pillar.
- [ ] SC10 (partial): tasks are in place; full verification (`≥8 classified high-discrimination by IRT`) lands in Phase 3.
- [ ] Brain handoff updated via `brain-ctl`.
- [ ] `.venv/bin/pytest -q` → green.

## Out of Scope (Phase-gated)

- IRT discrimination classification of B2 tasks (Phase 3 — SC10 full verification).
- Preset router that uses IRT θ on the new task set (Phase 4).
- LLM-judge tasks for B2 — explicitly excluded per spec to keep calibration tight.
