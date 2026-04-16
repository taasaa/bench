# Bench Verification Runbook

**Purpose:** Repeatable full benchmark verification — run all tasks, collect logs, verify scoring, report findings. Hand this document to a code agent; they do everything.

**Time estimate:** ~15–20 min with 4 parallel runners (33 tasks)

---

## Overview

The orchestrator (you) does ALL the thinking. Runner agents just run tasks and report artifacts.

**Split of labor:**
| Who | Does | Does NOT |
|-----|------|----------|
| **Orchestrator** | Read codebase, decompose tasks, verify logs, find bugs, build report | Run tasks |
| **Runner agents** | Run `bench run` per task, note execution status | Analyze scores, compare outputs, decide correctness |

---

## Setup

### Step 1 — Detect project
```bash
CWD=$(pwd) && PROJECT_NAME=$(bun ~/.claude/skills/Session/scripts/locate_project.ts --dir "$CWD" 2>/dev/null) || PROJECT_NAME=""
echo "PROJECT_NAME=$PROJECT_NAME"
```
Confirm: should print `Bench`

### Step 2 — Find default model
Check `bench_cli/run.py` line 109:
```python
DEFAULT_MODEL = "openai/default"
```
Use `--model openai/default` for all runs.

### Step 3 — Discover all tasks
```bash
python -m bench_cli run --tier full --list-tasks
```
Read the list. Count tasks. Split into 4 runner groups (~8-9 tasks each).

**Group strategy — roughly equal by count, mix task types:**
- Runner A: smoke + competence tasks (10-11 tasks)
- Runner B: execution tasks (9-10 tasks)
- Runner C: analysis tasks (9-10 tasks)
- Runner D: universal tasks (7-8 tasks)

### Step 4 — Read scorers and CLI (NOT runners — orchestrator only)

Before launching runners, the orchestrator reads these to understand the system:

**Core scorers:**
- `scorers/verify_sh.py` — text/JSON output from verify.sh scripts
- `scorers/llm_judge.py` — judge model grades via SCORE: N format
- `scorers/token_ratio.py` — efficiency = reference/actual tokens
- `scorers/time_ratio.py` — latency = reference/actual seconds (noise floor: 5s)
- `scorers/task_budgets.py` — per-task reference values

**CLI and scoring system:**
- `bench_cli/run.py` — task discovery, solver routing, metadata injection
- `bench_cli/compare.py` — eval log reading, pillar extraction, table formatting

**Auxiliary scorers (code review, not every run):**
- `scorers/safety.py`, `scorers/output_safety.py`, `scorers/execution_safety.py`
- `scorers/composite_safety.py` — min() aggregation
- `scorers/constraint.py` — unused in Phase 1
- `scorers/tool_call_efficiency.py` — agent eval only
- `scorers/instruction_overhead.py` — harness A/B only

### Step 5 — Set up orchestrator verification tools

**Python path:** tasks run in `.venv/bin/python` (Python 3.14 with inspect_ai installed).

**Reading eval logs:**
```python
.venv/bin/python3 -c "
from inspect_ai.log import read_eval_log

el = read_eval_log('logs/<FILENAME>.eval')
print(f'Status: {el.status}')
print(f'Task: {el.eval.task}')
print(f'Model: {el.eval.model}')
print(f'Samples: {len(el.samples) if el.samples else 0}')
for i, s in enumerate(el.samples):
    out = str(s.output.completion)[:300] if s.output else 'NONE'
    print(f'Sample {i}: {out}')
    if s.scores:
        for n, sc in s.scores.items():
            print(f'  {n}: {sc.value}')
            if sc.explanation:
                print(f'  exp: {sc.explanation[:200]}')
"
```

**Batch score extraction:**
```python
.venv/bin/python3 -c "
from inspect_ai.log import read_eval_log
import math

el = read_eval_log('logs/<FILENAME>.eval')
n = len(el.samples)
scores = []
for s in el.samples:
    if s.scores:
        for n_sc, sc in s.scores.items():
            v = sc.value
            if isinstance(v, float) and not math.isnan(v):
                scores.append((n_sc, v))

corr = [v for n,v in scores if n in ('llm_judge','verify_sh','includes')]
eff = [v for n,v in scores if n == 'token_ratio_scorer']
lat = [v for n,v in scores if n == 'time_ratio_scorer' and not math.isnan(v)]

print(f'status={el.status} n={n} corr={sum(corr)/len(corr):.2f if corr else \"--\"} '
      f'eff={sum(eff)/len(eff):.2f if eff else \"--\"} '
      f'lat={sum(lat)/len(lat):.2f if lat else \"--\"}')
"
```

**Finding latest logs:**
```bash
ls -lt logs/ | grep "2026-04-16T18"   # today's run
ls -t logs/ | grep "2026-04-16T18" | wc -l  # count
```

---

## Step 6 — Launch 4 Runner Agents

Create a team with `TeamCreate`. Create one task per runner. Spawn all 4 in parallel with `run_in_background=true`.

### Team setup
```
team_name: bench-verification
agent_type: orchestrator
description: Parallel benchmark verification — split tasks across 4 runners
```

### Orchestrator prompt (what YOU used — copy this)

```
You are the Orchestrator on the bench-verification team.
Your job is to run tasks and produce eval log files. You do NOT analyze results.

Work directory: /Users/rut/dev/bench
Model: openai/default via LiteLLM proxy at smallbox:4000
Python: .venv/bin/python3 (has inspect_ai installed)
TASK: <task-name> (from the list below)

For EACH task in your group, run:
  cd /Users/rut/dev/bench && python -m bench_cli run --tier full --model openai/default --task <task-name> 2>&1

Wait for each task to COMPLETE before moving to the next.
After ALL tasks done, report:
  1. Which tasks ran successfully
  2. Any that crashed, errored, or produced no samples
  3. Count of eval log files created
  4. Any anomalous output (script errors, timeout messages)

DO NOT analyze scores. DO NOT read logs. DO NOT decide if scoring is correct.
Your only job: run the tasks and report what happened.

Your task group: <list of task names>
```

### Runner A prompt template
```
You are Runner A on bench-verification team.
Run these tasks: <list>
For each: python -m bench_cli run --tier full --model openai/default --task <name>
Wait for completion. Report execution status only.
Work dir: /Users/rut/dev/bench
Python: .venv/bin/python3
```

### Runner B/C/D prompts — same structure, different task lists

---

## Step 7 — Orchestrator: Wait and Monitor

While runners execute:
- Periodically check `ls -lt logs/ | grep "2026-04-16T18"`
- Note new logs appearing
- Track which task groups are done
- Runners will send idle notifications when done

Do NOT interrupt runners. Just watch and wait.

---

## Step 8 — Orchestrator: Verify Results

After all runners complete, YOU verify everything.

### Phase A — Quick scan all logs
```python
import math
from inspect_ai.log import read_eval_log

tasks = {
    'smoke': 'logs/...eval',
    'q1': 'logs/...eval',
    # ... all 33 tasks
}

for name, path in sorted(tasks.items()):
    el = read_eval_log(path)
    status = el.status
    n = len(el.samples) if el.samples else 0
    scores = []
    for s in el.samples or []:
        for n_sc, sc in (s.scores or {}).items():
            v = sc.value
            if isinstance(v, float) and not math.isnan(v):
                scores.append((n_sc, v))
    corr = [v for n_sc,v in scores if n_sc in ('llm_judge','verify_sh','includes')]
    eff = [v for n_sc,v in scores if n_sc == 'token_ratio_scorer']
    lat = [v for n_sc,v in scores if n_sc == 'time_ratio_scorer' and not math.isnan(v)]
    c = f'{sum(corr)/len(corr):.2f}' if corr else '--'
    e = f'{sum(eff)/len(eff):.2f}' if eff else '--'
    l = f'{sum(lat)/len(lat):.2f}' if lat else '--'
    print(f'{name:24} {status:12} {n:7} {c:8} {e:9} {l:9}')
```

### Phase B — Deep verify task-by-task

For each task, read the actual model output:
```python
el = read_eval_log(path)
for i, s in enumerate(el.samples):
    print(f'=== Sample {i} ===')
    print(f'output: {str(s.output.completion)[:400]}')
    if s.scores:
        for n_sc, sc in s.scores.items():
            print(f'{n_sc}: {sc.value}')
            if sc.explanation:
                print(f'exp: {sc.explanation[:300]}')
```

Verify:
1. **Correctness scorer** — does the score match what the model actually said?
2. **Token ratio** — does reference/actual ratio make sense?
3. **Time ratio** — does latency ratio make sense? (check for NaN = suppressed)
4. **Status** — "started" = still running, "success" = done

### Phase C — Scorer system audit

Read each scorer file to confirm:
- verify_sh: JSON parsing, text parsing, SAMPLE_ID injection, subprocess call
- llm_judge: rubric loading, judge model call, SCORE: extraction regex
- token_ratio: ratio formula (reference/actual), floor value
- time_ratio: noise floor suppression, reference resolution chain

### Phase D — Task-specific verification

**verify.sh tasks:** Read the verify.sh script and simulate its logic against the model output.
- Does the script match what the model said?
- Are fixture paths correct relative to task directory?
- Are regex patterns correct (macOS grep compatibility)?

**llm_judge tasks:** Read judge.md and compare against the actual judge explanation in the log.
- Is the judge's reasoning sound?
- Does the SCORE: N match the rubric?

---

## Step 9 — Build Bug Report

Classify findings:
- **🔴 P0 CRASH**: verify.sh script broken (wrong paths, undefined variables)
- **🟡 P1 FALSE NEGATIVE**: scorer too strict, model was correct
- **🟡 P2 DESIGN**: mismatched defaults, unused code, cosmetic issues
- **🟡 P3 MINOR**: cosmetic stderr, doesn't affect scores

Format:
```
[TYPE] [PRIORITY] file/line — description
  Problem: what broke
  Fix: how to fix
  Impact: who was affected
```

---

## Step 10 — Shutdown

```python
SendMessage(to="runner-a", message={"type": "shutdown_request", "reason": "All done"})
SendMessage(to="runner-b", message={"type": "shutdown_request", "reason": "All done"})
SendMessage(to="runner-c", message={"type": "shutdown_request", "reason": "All done"})
SendMessage(to="runner-d", message={"type": "shutdown_request", "reason": "All done"})
# Wait, then:
TeamDelete()
```

---

## Runner Agent Prompt Template

Use this exact template — copy and substitute the task list:

```
You are Runner [X] on the bench-verification team. Your job is ONLY to run
tasks and report execution status. You do NOT analyze, verify, or compare results.

Work directory: /Users/rut/dev/bench
Python with inspect_ai: .venv/bin/python3
Model: openai/default (LiteLLM proxy at smallbox:4000)

TASKS TO RUN:
<task-1>
<task-2>
<task-3>
... (8-9 tasks)

PROTOCOL:
1. For each task: cd /Users/rut/dev/bench && python -m bench_cli run --tier full --model openai/default --task <task-name>
2. Wait for it to COMPLETE before next task
3. After ALL done: ls -lt logs/ | grep "$(date +%Y-%m-%d)" to confirm log files exist
4. Report: tasks run, logs created, any crashes or errors

IMPORTANT:
- Do NOT read eval logs
- Do NOT analyze scores
- Do NOT verify scoring correctness
- Do NOT interpret what model outputs mean
- Just run tasks and report execution status

CLAUDE.md context: Bench is a Python project using Inspect AI. No PAI dependencies.
Use NATIVE mode only. No Algorithm mode.
```

---

## Orchestrator Prompt Template (for spawning runners)

Use this exact template for each runner:

```
You are Runner [X] on the bench-verification team. Your job is ONLY to run
tasks and report execution status. You do NOT analyze, verify, or compare results.

Work directory: /Users/rut/dev/bench
Python with inspect_ai: .venv/bin/python3
Model: openai/default (LiteLLM proxy at smallbox:4000)

TASKS TO RUN:
- smoke
- q1-verification-gate
- q2-do-not-touch
... (8-9 tasks)

PROTOCOL:
1. For each task: cd /Users/rut/dev/bench && python -m bench_cli run --tier full --model openai/default --task <task-name>
2. Wait for completion before next
3. After all done: ls -lt logs/ | grep "2026-04-XX" (today's date) to confirm logs created
4. Report: tasks completed, logs created, any errors

DO NOT: read logs, analyze scores, verify correctness, interpret model output.
Just run tasks and report what happened.
```

---

## Task Group Assignment

Split 33-34 tasks across 4 runners:

**Runner A (10 tasks):** smoke, agent_smoke, q1, q2, q3, q5, f7, f12, f18, f20, add-tests

**Runner B (9 tasks):** f4, f5, f6, f8, f11, f14, q4, f15, f16

**Runner C (8 tasks):** f1, f9, f10, f19, f21, f22, f23, f24

**Runner D (8 tasks):** f17, f25, f26, f27, u7, u8, f25?, (adjust split)

Actually split based on actual count:
```
Total: 33 tasks
Runner A (9):  smoke, q1, q2, q3, q5, f7, f12, f18, f20
Runner B (9):  f4, f5, f6, f8, f11, f14, f15, f16, f17
Runner C (8):  f1, f9, f10, f19, f21, f22, f23, f24
Runner D (7):  q4, add-tests, f25, f26, f27, u7, u8
```

Add-tests was verified separately (scorer bug), so could group with Runner D.

---

## Verification Checklist

Use this to systematically verify each task:

### Quick checks (orchestrator, 1 min each)
- [ ] Eval log exists in logs/ with today's timestamp
- [ ] Status is "success" (not "started" or "error")
- [ ] Sample count matches dataset size
- [ ] Primary scorer (verify_sh or llm_judge) has non-None value
- [ ] token_ratio and time_ratio are non-NaN

### Deep checks (orchestrator, 2-3 min each)
- [ ] Read model output — does it answer the task correctly?
- [ ] Compare score against model output — do they agree?
- [ ] Check verify.sh logic vs model output (for verify_sh tasks)
- [ ] Check judge.md rubric vs judge explanation (for llm_judge tasks)
- [ ] Verify SAMPLE_ID mapping worked (check stderr of verify.sh tasks)
- [ ] Check for NaN in time_ratio (noise floor suppression correct?)
- [ ] Check fixture file paths exist for verify_sh tasks

### Scorer system checks (code review, 5 min total)
- [ ] verify_sh: subprocess call, JSON/text parsing, SAMPLE_ID injection
- [ ] llm_judge: rubric loading, judge model call, SCORE: regex
- [ ] token_ratio: ratio = reference/actual, floor value 0.01
- [ ] time_ratio: noise floor 5.0s, suppression working
- [ ] Compare: extracts correctness from llm_judge first, verify_sh fallback

---

## Score Reasonableness Checklist

After running a task, verify scores make sense:

### Correctness scores
- [ ] 1.0 = model clearly solved the task (check output)
- [ ] 0.0 = model clearly failed or didn't attempt (check output)
- [ ] 0.5-ish = model partially solved (check explanation)

### Efficiency ratios
- [ ] >1.0 = model used fewer tokens than reference budget → good
- [ ] 0.3-0.5 = model verbose but within reason
- [ ] <0.2 = model extremely verbose relative to budget

### Latency ratios
- [ ] NaN = task completed in <5s (noise floor suppressed) → OK
- [ ] 1.0 = at reference speed
- [ ] >2.0 = model fast for task type
- [ ] <0.5 = model slow relative to budget

---

## Bug Classification Guide

| Class | Description | Examples from this run |
|-------|-------------|----------------------|
| P0 CRASH | verify.sh broken, 100% wrong scores | add-tests fixture path, f15 undefined var |
| P1 FALSE NEGATIVE | scorer too strict, model was right | f18 whitespace, f20 markdown fence |
| P2 DESIGN | defaults wrong, unused code, cosmetic | compare log-dir, smoke includes |
| P3 MINOR | stderr noise, doesn't affect scoring | f5 grep macOS flag |

**Fix order:** P0 → P1 → P2 → P3

---

## What Went Well

1. **3-runner parallelization** — 33 tasks in ~15 min vs 60+ min sequential
   - NEXT RUN: Use 4 runners, smaller groups = faster

2. **Orchestrator read scorers first** — understanding verify_sh/llm_judge/token_ratio/time_ratio mechanics before running meant the verification was informed, not blind
   - Keep this: always read scorers before launching runners

3. **Runner agents only ran tasks** — no analysis, no interpretation
   - This was the right split. Runners executed, orchestrator thought.

4. **All 33 tasks produced eval logs** — zero crashes in the bench run itself
   - Model-only eval is stable. Docker agent eval (agent_smoke) was skipped correctly.

5. **llm_judge quality was high** — judge explanations were substantive, nuanced, and correct
   - No unparseable scores, no judge errors

6. **Noise floor suppression worked correctly** — fast tasks (f6 at 1.2s, q1 sample at 3.4s) correctly showed NaN instead of inflated ratios

7. **Runner reports confirmed orchestrator findings** — runner-b found f15 $RESPONSE bug independently, runner-a confirmed f18 and f20 scorer issues
   - Cross-validation worked: three independent checks on each finding

---

## What to Improve for Next Run

### 1. Run 4 agents, not 3
Current split: Runner A had 11 tasks, B had 10, C had 13.
With 4 runners: ~8-9 tasks each, tighter batches.

### 2. Run a quick smoke check BEFORE launching full team
Before running all 34 tasks, run 3-4 representative tasks (smoke + q1 + f7 + f22)
to confirm the system is working. Catch any proxy/connectivity issues early.

```
# Quick smoke (run first, before team launch):
python -m bench_cli run --tier full --model openai/default --task smoke
python -m bench_cli run --tier full --model openai/default --task q1
python -m bench_cli run --tier full --model openai/default --task f7
```

If any fail, fix before spinning up 4 runners.

### 3. Capture runner stdout/stderr during execution
Runners might miss things if they don't capture subprocess output.
Ensure each runner task logs: `2>&1 | tee /tmp/runner-[X]-output.txt`
Then orchestrator can read these files if needed.

### 4. Parallel orchestrator verification
While runners are still running (after first few complete), orchestrator
can start verifying completed tasks. Don't wait for all runners to finish.

### 5. Pre-built verification script
Create a single `verify_run.py` script that:
- Reads all eval logs from today's run
- Produces the score table automatically
- Flags anomalies (status != success, score=0.0, NaN patterns)
- Then orchestrator does deep-dive on flagged items

```python
# Pre-built verify script (save to bench_cli/verify_run.py)
import math, sys
from pathlib import Path
from inspect_ai.log import read_eval_log, list_eval_logs

today = "2026-04-16"
log_dir = Path("logs")
logs = sorted(log_dir.glob(f"{today}*T*.eval"), key=lambda p: p.stat().st_mtime)

print(f"Found {len(logs)} eval logs for {today}")
print()
print("TASK                    STATUS        N  CORRECT EFF    LAT")

for log in logs:
    try:
        el = read_eval_log(str(log))
        name = log.name.split("_")[2]  # task name
        status = el.status
        n = len(el.samples) if el.samples else 0

        corr_vals, eff_vals, lat_vals = [], [], []
        for s in el.samples or []:
            for nm, sc in (s.scores or {}).items():
                v = sc.value
                if not isinstance(v, float) or math.isnan(v): continue
                if nm in ('llm_judge','verify_sh','includes'):
                    corr_vals.append(v)
                elif nm == 'token_ratio_scorer':
                    eff_vals.append(v)
                elif nm == 'time_ratio_scorer':
                    lat_vals.append(v)

        c = f'{sum(corr_vals)/len(corr_vals):.2f}' if corr_vals else '--'
        e = f'{sum(eff_vals)/len(eff_vals):.2f}' if eff_vals else '--'
        l = f'{sum(lat_vals)/len(lat_vals):.2f}' if lat_vals else '--'
        flag = ' ⚠️' if status != 'success' else ''
        print(f'{name:24} {status:12} {n:2} {c:7} {e:5} {l:5}{flag}')
    except Exception as ex:
        print(f'{log.name:40} ERROR: {ex}')
```

### 6. Known bugs to fix before next run
All bugs below have been fixed as of 2026-04-16. If re-running, these should NOT appear.

```
P0 - add-tests verify.sh line 82: ✅ FIXED
     FIXTURE_FILE=tasks/competence/add-tests/fixtures/$SAMPLE.py → fixtures/$SAMPLE.py

P0 - f15-workspace-setup verify.sh: ✅ FIXED
     Added: RESPONSE=$(cat "$WORK_DIR/response.txt") before the if statement

P1 - f18 verify.sh: ✅ FIXED
     Strip leading/trailing whitespace before all checks
     Use first non-blank line instead of head -1
     Port position threshold 30 → 80

P1 - f20 verify.sh: ✅ FIXED
     Strip markdown fences and indentation from both fixture and response
     Allowance increased to ≤2 diff lines (had been wrong in test before)

P1 - compare.py: ✅ FIXED
     default log_dir="baselines" → default log_dir="logs"

P3 - f5 verify.sh: ✅ FIXED
     Added -- before grep patterns containing -> (macOS grep flag issue)
```

### 7. Add agent_smoke to the verification (Docker check)
If Docker is available, run agent_smoke separately:
```
python -m bench_cli run --tier quick --model openai/default --task agent_smoke --agent claude
```
This verifies the agent eval pipeline, not just model eval.

---

## Quick-Start Checklist (copy this for fast reference)

```
PRE-RUN:
  □ Run 3-task smoke (smoke + q1 + f7) to confirm system works
  □ Read scorers: verify_sh, llm_judge, token_ratio, time_ratio, compare
  □ Split 33 tasks across 4 runners (8-9 each)
  □ Create team "bench-verification"
  □ Create 4 tasks (Runner A/B/C/D)
  □ Spawn all 4 runners with prompts

MONITORING:
  □ ls -lt logs/ | grep today → watch logs appear
  □ Check for "started" status = still running
  □ Watch for crash logs (tiny files, <1KB)

POST-RUN:
  □ Run pre-built verify script → score table
  □ Deep verify: read outputs, compare to scores
  □ Check scorer code for correctness
  □ Classify bugs: P0/P1/P2/P3
  □ Fix P0/P1 before next run
  □ Shutdown team
```

---

## File Locations Reference

```
Work dir:          /Users/rut/dev/bench
Python (venv):     /Users/rut/dev/bench/.venv/bin/python3
Eval logs:         /Users/rut/dev/bench/logs/
Baselines:         /Users/rut/dev/bench/baselines/
Tasks:             /Users/rut/dev/bench/tasks/<category>/<name>/
Scorers:           /Users/rut/dev/bench/scorers/
CLI:               /Users/rut/dev/bench/bench_cli/run.py
Compare:           /Users/rut/dev/bench/bench_cli/compare.py
Bench task dirs:   /Users/rut/dev/bench/tasks/<cat>/<name>/

Key patterns:
  verify.sh tasks:    q1, q2, q3, q5, f5, f6, f7, f8, f12, f14, f15, f16, f17, f18, f20, add-tests
  llm_judge tasks:    f1, f4, f9, f10, f11, f19, f21, f22, f23, f25, f26, f27, q4, u7, u8
  includes() task:    smoke
  includes_numeric(): agent_smoke

Date format for logs: 2026-04-16T18-MM-SS (April 16, 2026, 18:xx hour)
```