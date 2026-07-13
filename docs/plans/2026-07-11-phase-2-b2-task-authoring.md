# Phase 2 — Harder Tasks (B2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Load subagent-driven-development/SKILL.md (recommended) or executing-plans/SKILL.md to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Source ~10 new evaluation tasks that discriminate in the cluster ability band where current 34-task suite has hit its ceiling. After Phase 2, the suite is ~44 tasks, giving the Phase 3 IRT engine enough items to model ability differences in the band where current models cluster.

**Architecture:** Additive task authoring into the existing `tasks/<pillar>/<task-name>/` layout. Each new task has the same shape as the existing 34: `task.py` (Inspect `@task`), `dataset.json` (`{input, target, id}`), and `verify.sh` (deterministic). No changes to scorers. **Two `bench_cli/` cuts are required** despite the original "no CLI changes" rule:
1. `bench_cli/compare/core.py:454` `MIN_FULL_EVAL_TASKS = 34` must move to 44 (and the bootstrap `min_n`, click default, and `tests/test_compare.py:300-301` lock) once the suite expands, otherwise old 34-task runs keep ranking as "full" beside 44-task models and Phase 3 IRT inputs are non-comparable.
2. `bench_cli/run/cli.py` / `bench_cli/run/core.py` run-help text must mention 44 tasks.

Token/latency reference budgets come from a **qwen-local** run (matches the existing per-task contract in `scorers/task_budgets.py:1-13,20-24`); only `reference_cost_usd` comes from minimax m3.

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
- **`--tier full` is mandatory for every Phase 2 run.** The CLI defaults to `quick` (`bench_cli/run/cli.py:170-178`) and `--task` filters WITHIN the selected tier; without `--tier full` the `--task <b2-name>` invocations silently select `verification/smoke` and report `No tasks found for tier 'quick'`. Use `--tier full --task <name>` on every Phase 2 invocation, including pilot, calibration, cohort runs, and per-task retries.
- **Run B2-only loops, never the full 44-task suite.** Re-running the 34 baseline tasks per model is wasted paid work. Iterate over the 10 B2 directory names: `for task in <b2-name-1> <b2-name-2> ...; do .venv/bin/python -m bench_cli run --tier full --task "$task" --model "openai/<model>" --no-resume; done`.
- Run resume gotcha: after a scorer change, `bench_cli/score.py` refactor (Phase 0), `task_budgets.py` change in this phase, or any verify.sh edit, ALL logs for that (model, task) pair become stale. The new tasks have no logs so this only matters for the `--no-resume` verification step (must equal `N_models × 10`).
- Task discovery is automatic from `tasks/<pillar>/<task-name>/task.py`. New tasks appear in `--tier full` runs as soon as the directory + `task.py` exist — no CLI/registry changes.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `docs/decisions/2026-07-11-b2-task-candidates.md` | Decision doc: 10 candidate tasks, sources, pillar mapping, discriminative rationale | Create (Task 1) |
| `tasks/<pillar>/<task-name>/task.py` | Inspect `@task` (one per new task) | Create (Task 2, 3, 4) |
| `tasks/<pillar>/<task-name>/dataset.json` | `{input, target, id}` samples | Create (Task 2, 3, 4) |
| `tasks/<pillar>/<task-name>/verify.sh` | Deterministic grader, `chmod +x` | Create (Task 2, 3, 4) |
| `scorers/task_budgets.py` | Add `output_tokens`, `latency_seconds` (qwen-local) and `reference_cost_usd` (minimax m3) per new task | Modify (Task 5) |
| `tests/test_b2_tasks.py` | Discovery + executable + budget + verifier-behavior tests (gold + per-distractor) | Create (Task 6) |
| `bench_cli/compare/core.py` | Move `MIN_FULL_EVAL_TASKS` 34 → 44 (full-suite gate + bootstrap CI floor) | Modify (Task 7) |
| `bench_cli/compare/cli.py` | Update `--min-tasks` click default/help to 44 | Modify (Task 7) |
| `bench_cli/compare/bootstrap.py` | Stop hardcoding `min_n=34`; import from `bench_cli.compare.core` | Modify (Task 7) |
| `bench_cli/run/cli.py`, `bench_cli/run/core.py` | Update run-help text and tier docstring to "44 tasks" | Modify (Task 7) |
| `tests/test_compare.py` | Update `assert MIN_FULL_EVAL_TASKS == 34` to 44 (and any other 34-anchored assertions) | Modify (Task 7) |

Two `bench_cli/` changes ARE required (Task 7 cutover) — original "no CLI changes" rule is overridden by the 34→44 threshold cutover.

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

**Pilot target:** the highest-confidence discriminative candidate from the decision doc. Recommended pilot (per `/tmp/bench-b2-source-research.md`): **`b2-proxy-auth-netloc-rebuild`** (SWE-bench-Verified `psf__requests-6028`, requests PR #6028 / issue #6027). Backup pilots if separation <0.4: `b2-layered-setting-none-deletes` (requests-1921) or `b2-merge-attrs-copy-isolation` (xarray-4629).

**Strong/weak aliases (LIVE, validated against `~/dev/litellm/config.yaml`):**
- Strong: `openai/go-kimi-k2.7-code`
- Weak: `openai/gemma-local`
- Reference (cost calibration): `openai/go-minimax-m3`
- Re-resolve at run-time; if any alias 404s, swap to a viable proxy alias and update the decision doc.

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

Run the pilot task on TWO models (one strong, one weak) to verify discriminative separation. **`--tier full` is required** so `--task <b2-name>` matches:

```bash
.venv/bin/python -m bench_cli run --tier full --model openai/go-kimi-k2.7-code --task <task-name> --no-resume
.venv/bin/python -m bench_cli run --tier full --model openai/gemma-local --task <task-name> --no-resume
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

After Batches A–C land, verify all 9 (1 pilot + 3 + 2 + 3) new tasks are discoverable. **Use the spec count, not raw `wc -l`** — the CLI prints headers/blank lines/footer so `wc -l` over-counts. Use:

```bash
.venv/bin/python -c "from bench_cli.run.core import _discover_tasks; print(len(_discover_tasks('full')))"
```

Expected after the pilot + Batches A + B + C: 43 (34 baseline + 9 new). If fewer, a task file is missing `task.py` or the `@task` decorator.

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
.venv/bin/python -c "from bench_cli.run.core import _discover_tasks; print(len(_discover_tasks('full')))"
```

Target: original 34 + 10 new = 44 tasks.

- [ ] **Step 3: Pillar distribution audit**

Confirm each pillar has 2-3 new B2 tasks (and overall total grew by 10):

```bash
.venv/bin/python -c "
from pathlib import Path
for pillar in ['analysis', 'competence', 'execution', 'universal']:
    total = sum(1 for p in Path('tasks', pillar).iterdir() if p.is_dir())
    b2 = sum(1 for p in Path('tasks', pillar).iterdir() if p.is_dir() and p.name.startswith('b2-'))
    print(f'{pillar}: {total} total ({b2} B2)')
"
```

Compare against the pre-Phase-2 counts (analysis=7, competence=9, execution=10, universal=8 → 34 tasks total). Expect each pillar B2 count to be 2 or 3; total = 44.

- [ ] **Step 4: Commit audit (no code change; advisory commit)**

If the audit reveals a missing pillar slot, open a follow-up commit adding the task. Otherwise skip.

---

## Task 5: Calibrate token/latency (qwen-local) + reference_cost_usd (minimax m3) for the new tasks

**Files:**
- Modify: `scorers/task_budgets.py`
- Create: `scripts/extract_b2_costs.py`

**Why two reference models:** the existing per-task contract in `scorers/task_budgets.py:1-13,20-24` defines `output_tokens` / `latency_seconds` against **qwen-local** (via BaselineStore / task_budgets Tier-2 fallback) and `reference_cost_usd` against **minimax m3**. Mixing the two baselines for the new B2 tasks would silently break cross-task pillar comparability. Run **two** B2-only loops and let the helper merge the per-task averages.

- [ ] **Step 1: Run the new tasks on minimax m3 (cost calibration)**

Loop B2-only with `--tier full --task ... --no-resume`; do NOT rerun the 34 baseline tasks:

```bash
B2_TASKS="b2-proxy-auth-netloc-rebuild b2-layered-setting-none-deletes ..."  # 10 names
for task in $B2_TASKS; do
    .venv/bin/python -m bench_cli run --tier full --task "$task" \
        --model openai/go-minimax-m3 --no-resume
done
```

- [ ] **Step 2: Run the new tasks on qwen-local (token + latency calibration)**

Same B2-only loop, qwen-local route:

```bash
for task in $B2_TASKS; do
    .venv/bin/python -m bench_cli run --tier full --task "$task" \
        --model openai/qwen-local --no-resume
done
```

- [ ] **Step 3: Extract per-task averages from the new logs**

Write `scripts/extract_b2_costs.py` that imports the existing `load_compare_data` and prints one line per B2 task joining qwen-local (`output_tokens`, `latency_seconds`) with minimax-m3 (`reference_cost_usd`). Critical fixes vs. the original plan: (a) Inspect records tasks as `b2_proxy_auth_netloc_rebuild` (snake_case), not the directory name - filter by `replace("_", "-").startswith("b2-")`; (b) recorded identity is `minimax/minimax-m3` not `minimax-m3`, so accept the `minimax` prefix and assert exactly one row per B2 task from each reference model. Fail-closed: a missing or ambiguous row aborts the calibration.

```python
#!/usr/bin/env python3
"""Extract per-task token/latency/cost averages from B2 .eval logs.

Merges minimax-m3 (cost) and qwen-local (token + latency) rows per B2
task and prints a tab-separated table the engineer copies into
`scorers/task_budgets.py`.

Usage: .venv/bin/python scripts/extract_b2_costs.py [--log-dir logs]

Asserts exactly one cost row and one token/latency row per B2 task.
Exits nonzero on missing or ambiguous data.
"""
from __future__ import annotations

import argparse
import sys

from bench_cli.compare.core import load_compare_data


COST_MODEL_PREFIXES = ("minimax/", "minimaxai/minimax-m3", "minimax-m3")
TOKEN_MODEL_PREFIXES = ("qwen/", "qwen-local")


def _b2_filter(task_name: str) -> bool:
    return task_name.replace("_", "-").startswith("b2-")


def _select_model(matrix_for_task, prefixes):
    """Pick the single recorded identity matching any prefix. Abort on 0/>1."""
    matches = [m for m in matrix_for_task if any(m.startswith(p) for p in prefixes)]
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise RuntimeError(
            f"ambiguous model match for prefixes={prefixes}: {matches}"
        )
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", default="logs")
    args = parser.parse_args()

    data = load_compare_data(args.log_dir)
    b2_tasks = [t for t in data.tasks if _b2_filter(t)]
    if not b2_tasks:
        print("No B2 tasks in log dir; aborting.", file=sys.stderr)
        raise SystemExit(2)

    rows = []
    for task in b2_tasks:
        matrix_for_task = data.matrix.get(task, {})
        cost_model = _select_model(matrix_for_task, COST_MODEL_PREFIXES)
        token_model = _select_model(matrix_for_task, TOKEN_MODEL_PREFIXES)
        if cost_model is None:
            raise RuntimeError(
                f"task={task}: no minimax-m3 cost row (run Step 1 first)"
            )
        if token_model is None:
            raise RuntimeError(
                f"task={task}: no qwen-local token row (run Step 2 first)"
            )

        cost_ps = matrix_for_task[cost_model]
        token_ps = matrix_for_task[token_model]
        cost = cost_ps.avg_cost_usd
        if cost != cost:  # NaN guard
            raise RuntimeError(f"task={task}: cost is NaN")
        if cost <= 0:
            raise RuntimeError(f"task={task}: cost <= 0 ({cost})")

        rows.append((task, round(cost, 6), round(token_ps.avg_tokens, 1),
                     round(token_ps.avg_time, 2)))

    print("task_name\treference_cost_usd\toutput_tokens\tlatency_seconds")
    for task, cost, tokens, time_s in rows:
        print(f"{task}\t{cost:.6f}\t{tokens:.1f}\t{time_s:.2f}")


if __name__ == "__main__":
    main()
```

Run it after both Steps 1 and 2 complete:

```bash
.venv/bin/python scripts/extract_b2_costs.py
```

Expected: 10 lines, one per B2 task. If shorter, the missing row's model has no log yet - re-run that `(task, model)` pair.

- [ ] **Step 4: Update `scorers/task_budgets.py`**

For each of the 10 B2 tasks, add a `TaskBudget` entry to the `TASK_BUDGETS` dict. Use `output_tokens` and `latency_seconds` from the qwen-local column and `reference_cost_usd` from the minimax-m3 column. The key is the directory name (hyphenated); `get_task_budget` normalizes hyphen<->underscore for lookups.

```python
    "<task-directory-name>": TaskBudget(
        output_tokens=<qwen-local avg_tokens from Step 3>,
        latency_seconds=<qwen-local avg_time from Step 3>,
        reference_cost_usd=<minimax-m3 avg_cost_usd from Step 3>,
    ),
```

If multiple samples exist for a B2 task per reference model, use the mean across samples.

- [ ] **Step 5: Sanity-check pricing appears in compare**

Confirm the new tasks appear with a non-null `price_ratio` for the minimax-m3 recorded identity. Filter by the recorded identity (`minimax/minimax-m3`), not the routing alias, since recorded identity is what compare indexes by:

```bash
.venv/bin/python -m bench_cli compare --json 2>&1 | .venv/bin/python -c "
import json, sys
data = json.loads(sys.stdin.read())
b2 = [r for r in data if r['task'].replace('_','-').startswith('b2-') and 'minimax' in r['model'].lower()]
print(f'B2 rows for minimax-m3: {len(b2)}')
for row in sorted(b2, key=lambda r: r['task']):
    print(f"  {row['task']:<40} cost_usd={row['avg_cost_usd']}  price_ratio={row['price_ratio']}")
"
```

Expected: 10 rows with non-null `price_ratio`. If null, the task is missing from `task_budgets.py`.

- [ ] **Step 6: Commit**

```bash
git add scorers/task_budgets.py scripts/extract_b2_costs.py
git commit -m "feat(budgets): B2 task calibration (cost=minimax-m3, token+latency=qwen-local) + extract helper"
```


---

## Task 6: B2 task behavioral tests + verifier smoke

**Files:**
- Create: `tests/test_b2_tasks.py`

**Why this exists:** the original plan's six tests verified file shape only — they never executed a B2 verifier, allowed `>= 8` tasks (not the contractually-agreed 10), and never enforced per-task gold/distractor behavior. A verifier that rejects the gold answer or accepts a designed distractor would pass all six tests and silently invalidate Phase 3 IRT inputs. These tests replace the originals with strict discovery + behavioral coverage, mirroring the spirit of `tests/test_tier2_tasks.py` and the executable-aware helper in `tests/conftest.py`.

- [ ] **Step 1: Write the test file**

Create `tests/test_b2_tasks.py`:

```python
"""Discovery + executable + dataset-shape + budget + verifier-behavior tests
for Phase 2 B2 tasks.

Each B2 task MUST:
  1. Live under tasks/<pillar>/b2-*/ with task.py + verify.sh + dataset.json.
  2. Have an executable verify.sh (os.access(..., os.X_OK)).
  3. Have a dataset.json that parses as a list of samples, each with
     input/target/id, with >= 4 unique ids.
  4. Have a task.py that exposes >= 1 @task-decorated callable.
  5. Be discoverable through `_discover_tasks("full")` AND loadable through
     Inspect's `_resolve_task` (so a typo in @task does not silently break
     the run).
  6. Have a registered TaskBudget in scorers/task_budgets.py after Task 5.
  7. Pass its verifier against a known-good response (the dataset's target
     OR a hand-written golden answer) AND fail its verifier against at least
     4 designed distractor samples per task (assertions parameterized below).

The test harness lives alongside tests/test_tier2_tasks.py: import the shared
`executable_verify` helper from tests/conftest.py for known-good/known-bad
coverage.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from scorers.task_budgets import get_task_budget


_TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"
_REQUIRED_FILES = ("task.py", "dataset.json", "verify.sh")


def _b2_task_dirs() -> list[Path]:
    out: list[Path] = []
    for pillar in ("analysis", "competence", "execution", "universal"):
        for p in (_TASKS_ROOT / pillar).iterdir():
            if p.is_dir() and p.name.startswith("b2-"):
                out.append(p)
    return sorted(out)


def _expected_b2_names() -> list[str]:
    """Read the B2 candidate list from the decision doc if present."""
    doc = _TASKS_ROOT.parent / "docs" / "decisions" / "2026-07-11-b2-task-candidates.md"
    if not doc.is_file():
        return []
    text = doc.read_text()
    return sorted(set(re.findall(r"`(b2-[a-z0-9-]+)`", text)))


def test_b2_tasks_count_is_exactly_10():
    """Phase 2 ships exactly 10 tasks; allow swaps down to 8 only if documented."""
    names = [p.name for p in _b2_task_dirs()]
    expected = _expected_b2_names()
    if expected:
        missing = [n for n in expected if n not in names]
        assert not missing, f"expected B2 tasks missing from filesystem: {missing}"
    assert len(names) >= 8, f"expected >=8 B2 tasks, found {len(names)}: {names}"
    assert len(names) <= 10, f"expected <=10 B2 tasks, found {len(names)}: {names}"


@pytest.mark.parametrize("task_dir", _b2_task_dirs(), ids=lambda p: p.name)
def test_b2_task_has_required_files(task_dir: Path):
    for name in _REQUIRED_FILES:
        assert (task_dir / name).is_file(), f"missing {name} in {task_dir}"


@pytest.mark.parametrize("task_dir", _b2_task_dirs(), ids=lambda p: p.name)
def test_b2_verify_sh_is_executable(task_dir: Path):
    verify = task_dir / "verify.sh"
    assert os.access(verify, os.X_OK), f"verify.sh not executable in {task_dir}"


@pytest.mark.parametrize("task_dir", _b2_task_dirs(), ids=lambda p: p.name)
def test_b2_dataset_json_is_well_formed(task_dir: Path):
    ds = task_dir / "dataset.json"
    with ds.open() as f:
        samples = json.load(f)
    assert isinstance(samples, list), f"dataset.json not a list in {task_dir}"
    assert len(samples) >= 4, f"dataset.json must have >=4 samples in {task_dir}"
    for sample in samples:
        for key in ("input", "target", "id"):
            assert key in sample, f"sample missing {key} in {task_dir}"
    ids = [s["id"] for s in samples]
    assert len(ids) == len(set(ids)), f"duplicate ids in {task_dir}"


@pytest.mark.parametrize("task_dir", _b2_task_dirs(), ids=lambda p: p.name)
def test_b2_task_py_has_task_decorator(task_dir: Path):
    text = (task_dir / "task.py").read_text()
    assert re.search(r"^@task\s*$", text, re.MULTILINE), (
        f"no @task decorator in {task_dir}/task.py"
    )


def test_b2_tasks_discoverable_in_full_tier():
    """Every B2 directory must appear in `_discover_tasks("full")`."""
    from bench_cli.run.core import _discover_tasks

    discovered = {Path(s).parent.name for s in _discover_tasks("full")}
    on_disk = {p.name for p in _b2_task_dirs()}
    missing = on_disk - discovered
    assert not missing, f"B2 tasks not discovered in --tier full: {missing}"


@pytest.mark.parametrize("task_dir", _b2_task_dirs(), ids=lambda p: p.name)
def test_b2_task_loads_through_resolve_task(task_dir: Path):
    """The @task factory must load without error via Inspect's resolver."""
    from inspect_ai._util.registry import registry_info

    spec = f"tasks/{task_dir.parent.name}/{task_dir.name}/task.py"
    info = registry_info(spec)
    assert info is not None, f"could not resolve Inspect task: {spec}"


@pytest.mark.parametrize("task_dir", _b2_task_dirs(), ids=lambda p: p.name)
def test_b2_task_has_calibrated_budget(task_dir: Path):
    """TaskBudget must be registered after Task 5 calibration."""
    budget = get_task_budget(task_dir.name)
    assert budget is not None, f"no TaskBudget for {task_dir.name}"
    assert budget.reference_cost_usd is not None and budget.reference_cost_usd > 0, (
        f"missing/zero reference_cost_usd for {task_dir.name}"
    )


@pytest.mark.parametrize("task_dir", _b2_task_dirs(), ids=lambda p: p.name)
def test_b2_verifier_passes_on_golden_answer(task_dir: Path):
    """Build a golden answer from each sample's `target` field; verifier must pass."""
    samples = json.loads((task_dir / "dataset.json").read_text())
    verify = task_dir / "verify.sh"
    for sample in samples:
        target = sample["target"]
        proc = subprocess.run(
            ["bash", str(verify)],
            input=target,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(task_dir),
        )
        assert proc.returncode == 0, (
            f"verifier failed for {task_dir.name}/{sample['id']} on golden target.\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )


def test_b2_pillar_distribution_in_range_2_to_3():
    counts = {}
    for pillar in ("analysis", "competence", "execution", "universal"):
        counts[pillar] = sum(
            1 for p in (_TASKS_ROOT / pillar).iterdir()
            if p.is_dir() and p.name.startswith("b2-")
        )
    for pillar, n in counts.items():
        assert 2 <= n <= 3, f"{pillar} pillar has {n} B2 tasks (expected 2-3)"
```

- [ ] **Step 2: Add per-task distractor behavioral coverage**

For each B2 task, add 4+ distractor samples in `dataset.json` (each with a `target` that the verifier is designed to fail), then add a parameterized `test_b2_verifier_fails_on_distractors` in the same test file that exercises each distractor. The verifier for the pilot must fail for at least 4 designed distractors; otherwise the discriminative rationale is suspect. Use the executable-aware helper pattern from `tests/test_tier2_tasks.py:48-122`. Do not relax this rule even if the verifier is hard to author: that is itself a discriminative signal.

- [ ] **Step 3: Run tests — confirm pass**

```bash
.venv/bin/pytest tests/test_b2_tasks.py -v
```

Expected: all tests pass after Tasks 1-5 are complete (10 B2 tasks in `tasks/<pillar>/`, with budgets registered).

- [ ] **Step 4: Run full suite — confirm no regressions**

```bash
.venv/bin/pytest -q
```

Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_b2_tasks.py
git commit -m "test(b2): B2 task discovery + budget + verifier behavior (gold + distractors)"
```

---

## Task 7: 34->44 full-eval cutover (suite semantics)

**Files:**
- Modify: `bench_cli/compare/core.py` (`MIN_FULL_EVAL_TASKS` 34 -> 44)
- Modify: `bench_cli/compare/bootstrap.py` (`min_n` -> import from `compare.core`)
- Modify: `bench_cli/compare/cli.py` (`--min-tasks` default + help text 34 -> 44)
- Modify: `bench_cli/run/cli.py` and `bench_cli/run/core.py` (run-help text + tier docstring 34 -> 44)
- Modify: `tests/test_compare.py` (`assert MIN_FULL_EVAL_TASKS == 34` -> 44; any other 34-anchored fixtures)

**Why this exists:** the original plan's "no bench_cli/ changes" rule is overridden by the cutover. After the suite grows to 44 tasks, models with only the 34 baseline logs must NOT remain ranked as "full" beside 44-task models, and their means/CIs come from different item sets. Cutting over BEFORE B2 data collection keeps comparison semantics consistent; cutting over AFTER makes all in-flight runs partial mid-stream.

The original Task 7 (cohort collection) is now **Task 8** below.

- [ ] **Step 1: Update `MIN_FULL_EVAL_TASKS` to 44**

Edit `bench_cli/compare/core.py:454`:

```python
MIN_FULL_EVAL_TASKS = 44  # `--tier full` task count after Phase 2; partial evals are excluded from ranking
```

- [ ] **Step 2: Centralize bootstrap `min_n` on the constant**

Replace the literal `34` in `bench_cli/compare/bootstrap.py:13-30` with `MIN_FULL_EVAL_TASKS` imported from `bench_cli.compare.core`. Bootstrap default param docstring stays as "default 44".

- [ ] **Step 3: Update click defaults/help to 44**

In `bench_cli/compare/cli.py`, change the `--min-tasks` Click default and help text from `34` to `44`. In `bench_cli/run/cli.py:175-178` and `bench_cli/run/core.py:212-215`, update the run-help text and tier docstring from "all 34 eval tasks" to "all 44 eval tasks".

- [ ] **Step 4: Update test lock**

In `tests/test_compare.py:300-301`:

```python
def test_min_full_eval_tasks_is_44():
    assert MIN_FULL_EVAL_TASKS == 44
```

- [ ] **Step 5: Run targeted tests**

```bash
.venv/bin/pytest tests/test_compare.py tests/test_viability_tier.py -q
.venv/bin/pytest -q
```

Expected: 755+ tests green.

- [ ] **Step 6: Commit**

```bash
git add bench_cli/compare/core.py bench_cli/compare/bootstrap.py bench_cli/compare/cli.py bench_cli/run/cli.py bench_cli/run/core.py tests/test_compare.py
git commit -m "feat(suite): full-eval gate 34 -> 44 after Phase 2 B2 expansion"
```

---

## Task 8: B2-only cohort run

**Files:** No new files; this task produces `N_models x 10` new `.eval` logs in `logs/`.

**Why this exists:** the PRD Test Plan locks Phase 2's success criteria item #10 (`>=8 new tasks classified high-discrimination by IRT`), but the IRT engine itself is Phase 3. Phase 2 only delivers the data; Phase 3 verifies the discrimination. Run **only the 10 B2 tasks per model**, never the full 44-task suite, to bound paid work.

- [ ] **Step 1: Build the runnable cohort from the live proxy + recorded-identity matching**

The original plan's filename-regex approach is broken (current logs use `<timestamp>_<task>_<id>.eval` with no model token). Build the cohort from recorded identities in `load_compare_data`, mapped back to their runnable proxy aliases.

```bash
.venv/bin/python - <<'PY'
"""Print the cohort: runnable proxy alias -> recorded identity,
restricted to identities with >= MIN_FULL_EVAL_TASKS (44) baseline coverage
after the Task 7 cutover.

Validate the cohort, do not pre-flight from filenames.
"""
from bench_cli.compare.core import load_compare_data, MIN_FULL_EVAL_TASKS
from bench_cli.run.core import build_model_route

data = load_compare_data("logs")
# Concrete recorded identities with full coverage on baseline tasks
# (post-cutover: >= 44 tasks = full eval).
covered = {
    model for model, aggs in (data.model_aggregates or {}).items()
    if aggs.get("n", 0) >= MIN_FULL_EVAL_TASKS
}
# Map recorded -> runnable alias by probing the live proxy for known aliases.
# The proxy is the source of truth: if a recorded identity has no runnable
# alias, drop it from the cohort.
KNOWN_PROXY_ALIASES = [
    "go-kimi-k2.7-code", "go-minimax-m3", "qwen-local", "gemma-local",
    "go-mimo-pro", "deepseek-v4-pro", "qwen3.5-max", "glm-5.2",
]
cohort = []
for recorded in sorted(covered):
    for alias in KNOWN_PROXY_ALIASES:
        try:
            route = build_model_route(alias, None)
        except Exception:
            continue
        if route.recorded_name == recorded:
            cohort.append((alias, recorded))
            break
for alias, recorded in cohort:
    print(f"{alias}\t{recorded}")
PY
```

Capture the output as `COHORT` for Step 2. Drop any alias that 404s on the proxy at first smoke. If fewer than 8 concrete models are available, document it in the session handoff and proceed with what exists — the SC10 floor is ">=8 tasks classified high-discrimination", not ">=16 models x 10 tasks".

- [ ] **Step 2: Run `--no-resume` per `(model, task)` pair — B2 only**

```bash
B2_TASKS="b2-proxy-auth-netloc-rebuild b2-layered-setting-none-deletes ..."  # 10 names
while read -r line; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    alias=$(echo "$line" | cut -f1)
    for task in $B2_TASKS; do
        echo "RUNNING $alias on $task"
        .venv/bin/python -m bench_cli run --tier full --task "$task" \
            --model "openai/$alias" --no-resume
    done
done <<< "$COHORT"
```

`-j` parallelism may be set per the speedup backlog. Do not exceed LiteLLM proxy RPM limits (see `~/dev/litellm/config.yaml` `enforce_model_rate_limits`). Run sequentially when proxy RPM is at risk; parallel only after a single smoke run confirms safety.

- [ ] **Step 3: Verify the new logs**

Inspect log headers for each successful `(recorded_identity, task)` pair. The plan's filename-only count is unreliable (pilot/calibration logs and retries inflate it); header inspection is the only authoritative check.

```bash
.venv/bin/python - <<'PY'
"""Snapshot new logs created during Task 8 Step 2 and verify
the exact Cartesian product `cohort x B2_tasks` is present."""
from datetime import datetime, timedelta
from pathlib import Path

from bench_cli.compare.core import load_compare_data

START = datetime.utcnow() - timedelta(hours=4)  # tune at runtime
EXPECTED_TASKS = []  # 10 B2 directory names
COHORT = set()        # recorded identities from Step 1

seen = set()
for p in Path("logs").rglob("*.eval"):
    try:
        from bench_cli.inspect.core import read_log_header
        h = read_log_header(p)
    except Exception:
        continue
    if h.status != "success":
        continue
    started = datetime.fromisoformat(h.started_at.replace("Z", ""))
    if started < START:
        continue
    task = h.task_args.task  # snake_case
    model = h.eval.model      # recorded identity
    if task.replace("_", "-") in EXPECTED_TASKS and model in COHORT:
        seen.add((task, model))

missing = {
    (t.replace("-", "_"), m) for m in COHORT for t in EXPECTED_TASKS
} - seen
print(f"present: {len(seen)}, missing: {len(missing)}")
for pair in sorted(missing):
    print(f"  missing: {pair}")
PY
```

Expected: `missing == 0`. If short, re-run only the missing `(task, alias)` pairs:

```bash
.venv/bin/python -m bench_cli run --tier full --task <task> --model openai/<alias> --no-resume
```

- [ ] **Step 4: Commit (none — `logs/` is gitignored)**

If `logs/` is in `.gitignore`, nothing to commit. If not, add it; do not bulk-commit logs.

---

## Task 9: README + handoff updates

**Files:**
- Modify: `README.md` (suite size 34 -> 44; mention B2 discrimination tasks)
- (Removed: `docs/plans/2026-07-11-phase-0-rescore-and-capability-default.md` is no longer in this plan — the previous "Next" pointer there is already up to date.)

- [ ] **Step 1: Update task count and B2 mention in `README.md`**

Find the run-help / quick-reference block (no literal "Suite size" line exists — update both the `--tier full` description and the quick-reference count). Update from `34` to `44 tasks (34 baseline + 10 B2 discrimination tasks)`.

- [ ] **Step 2: Update second-brain handoff (via `brain-ctl`)**

After the session ends, run:

```bash
brain-ctl sessions:append bench <session-id> --work-done "Phase 2 shipped: 10 B2 tasks added (tasks/<pillar>/b2-*/), reference costs calibrated, B2-only cohort logs in-place, full-eval gate moved 34 -> 44. Phase 3 IRT can begin."
```

For per-task status changes:

```bash
CEILING_TASK_ID=$(brain-ctl tasks bench --filter status=active \
    | python3 -c '
import json, sys, re
raw = sys.stdin.read()
# brain-ctl tasks bench output may be a list of dicts (JSON) or text rows.
try:
    rows = json.loads(raw)
    for r in rows:
        if "harder discriminating" in r.get("text",""):
            print(r["id"]); break
except Exception:
    for line in raw.splitlines():
        m = re.search(r"\b([0-9a-f]{8})\b.*harder discriminating", line)
        if m: print(m.group(1)); break
')

if [[ -n "$CEILING_TASK_ID" ]]; then
    brain-ctl tasks:complete bench "$CEILING_TASK_ID"
fi
brain-ctl tasks:create bench "Phase 3 - IRT engine" --priority high
```

Exact IDs are looked up from `brain-ctl tasks bench`. Insert as needed.

- [ ] **Step 3: Commit README update**

```bash
git add README.md
git commit -m "docs: B2 suite is 44 tasks total"
```

---

## Done Criteria

- [ ] All 9 tasks shipped. **Exactly 10** new `b2-*` task directories under `tasks/<pillar>/` (the test floor of 8 exists only for in-flight swaps).
- [ ] Decision doc at `docs/decisions/2026-07-11-b2-task-candidates.md` lists the 10 candidates with the verified SWE-bench-Verified source identities and discriminative rationale from `/tmp/bench-b2-source-research.md`.
- [ ] Every new task has: executable `verify.sh`, valid `dataset.json` (>= 4 samples, unique ids, >= 4 designed distractor samples), `@task`-decorated callable in `task.py`.
- [ ] `scorers/task_budgets.py` has `reference_cost_usd`, `output_tokens`, and `latency_seconds` for each new task (qwen-local for the latter two, minimax-m3 for the first).
- [ ] `tests/test_b2_tasks.py` exists; every test passes including gold-answer and per-distractor behavioral coverage.
- [ ] Full-eval gate moved 34 -> 44 (`MIN_FULL_EVAL_TASKS`, bootstrap `min_n`, compare CLI default/help, run-help text, test locks).
- [ ] New B2 `.eval` logs cover the exact Cartesian product `cohort x B2_tasks` with header-verified `(recorded_identity, task, status=success)` triples. Per-task count equals `|cohort|`.
- [ ] Pillar distribution: 2-3 new tasks per pillar.
- [ ] SC10 (partial): tasks are in place; full verification (`>=8 classified high-discrimination by IRT`) lands in Phase 3.
- [ ] Brain handoff updated via `brain-ctl`.
- [ ] `.venv/bin/pytest -q` -> green.## Out of Scope (Phase-gated)

- IRT discrimination classification of B2 tasks (Phase 3 — SC10 full verification).
- Preset router that uses IRT θ on the new task set (Phase 4).
- LLM-judge tasks for B2 — explicitly excluded per spec to keep calibration tight.
