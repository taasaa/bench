# Bench Eval Results Verification

Run the full eval suite for the specified model, verify the resulting scores, compare to prior runs, and report anomalies.

Parameter: `$ARGUMENTS` — **required** — bench model alias (e.g. `openai/nvidia-nemotron-30b` or `nvidia-nemotron-30b`).

## Context

Bench is a Python + Inspect AI evaluation system. Each task produces eval logs (binary `.eval` files in `logs/`). Each sample is scored by 4 independent scorers producing 4 pillars:
- **Correctness** (verify_sh, llm_judge, or hybrid_scorer)
- **Token efficiency** (token_ratio_scorer — reference/actual tokens)
- **Latency** (time_ratio_scorer — reference/actual seconds, noise floor 5s)
- **Cost** (price_ratio_scorer — reference_cost_usd/actual_cost_usd)

Model cards in `results/` are auto-generated from eval logs.

The `bench inspect` CLI command handles all extraction and formatting. This command orchestrates the full pipeline.

---

## Step 0 — Parse model alias

`$ARGUMENTS` may be a full bench alias (`openai/nvidia-nemotron-30b`) or a short name (`nvidia-nemotron-30b`).

```bash
MODEL_ALIAS_FULL=$(echo "$ARGUMENTS" | sed 's|^models/||; s|^openrouter/||; s|^openai/||; s|^|openai/|')
echo "Full model alias: $MODEL_ALIAS_FULL"
```

---

## Step 1 — Run pytest (gate)

```bash
cd /Users/rut/dev/bench && pytest 2>&1
```

If tests fail: report failures and ask whether to proceed. Do not skip.

---

## Step 2 — Snapshot old baseline

Capture the current per-task correctness averages before the new run. This is the reference for delta comparison.

```bash
cd /Users/rut/dev/bench
bench inspect compare --model "$MODEL_ALIAS_FULL" > /tmp/baseline-compare.txt 2>&1
cat /tmp/baseline-compare.txt
```

Save this output. It shows old averages for all tasks.

---

## Step 3 — Run the eval suite

```bash
cd /Users/rut/dev/bench
python -m bench_cli run --model "$MODEL_ALIAS_FULL" --tier full --concurrency 4 2>&1
```

If the run fails mid-way: report which tasks completed, which failed, and ask whether to verify what we have or abort.

---

## Step 4 — Stats for new run

Print per-task pillar averages for the newly written eval logs.

```bash
bench inspect stats --model "$MODEL_ALIAS_FULL"
```

Review this for:
- Any tasks that are missing or have 0 samples
- Suspicious NaN rates for token_ratio or time_ratio
- All-perfect or all-zero correctness per task

---

## Step 5 — Delta comparison

Compare new scores against the old baseline. Flag tasks where correctness changed significantly.

```bash
bench inspect compare --model "$MODEL_ALIAS_FULL"
```

For each task marked `*** SIGNIFICANT` (>0.15 delta), read the eval log and spot-check samples to determine if the delta is genuine performance change or a scorer artifact.

```python
from inspect_ai.log import read_eval_log, list_eval_logs
# Read a specific eval log to investigate a delta
el = read_eval_log("logs/<file>.eval")
for s in el.samples:
    print(f"Sample {s.id}: correctness={s.scores.get('verify_sh').value if 'verify_sh' in s.scores else s.scores.get('llm_judge').value}")
    print(f"  Output: {str(s.output.completion)[:300]}")
```

---

## Step 6 — Deep check (all tasks)

Run the full QA pass on every task. This reads all sample outputs, judge explanations, and scorer content.

```bash
bench inspect deep-check --model "$MODEL_ALIAS_FULL" --output /tmp/qa-report.md
cat /tmp/qa-report.md
```

Review the full report. Key sections:

1. **Anomalies** — scorer bugs, broken judges, all-perfect/all-zero tasks
2. **Per-Task Deep Check** — judge quality, score soundness, task design, verdict per task
3. **Verdict Summary table** — SOUND / FLAWED / UNCERTAIN for every task

For every task marked **FLAWED** or **UNCERTAIN**, read the task prompt and scorer:
```bash
cat tasks/<pillar>/<task>/task.py | head -30
cat tasks/<pillar>/<task>/judge.md  # or verify.sh
```

Investigate whether the issue is:
- **Scorer broken** — fix the scorer
- **Judge rubber-stamping** — fix the judge prompt or switch to verify_sh
- **Task design** — task is too easy, too hard, or ambiguous
- **Model genuinely different** — real performance change

---

## Step 7 — Reference files (as needed)

```bash
# Reference budgets
cat scorers/task_budgets.py

# Price cache
cat logs/pricing/openrouter-models.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(list(d.keys())[:10])"

# Model alias mapping
cat bench_cli/pricing/model_aliases.py | head -50
```

---

## Step 8 — Report

After reviewing all outputs, compile the final report:

```
## Bench Verification Report

**Date:** YYYY-MM-DD
**Model:** <model alias>
**Test suite:** N passed, M skipped

### Status: PASS / PASS WITH WARNINGS / FAIL

### Eval Run Summary
- Tasks completed: N
- Tasks failed/error: N
- Significant deltas vs baseline (>0.15): N

### Findings

#### Critical (must fix before trusting results)
- [scorer broken, broken judge, all-perfect/zero tasks]

#### Significant Deltas (>0.15 correctness change)
- [task]: old=X new=Y delta=Z — [genuine / scorer artifact / prompt changed]

#### Warnings (anomalies with explanations)
- [NaN token_ratio for tasks with working_time > 5s, etc.]

#### Info (observations)
- [low-signal tasks, inter-model ordering, reasonableness notes]

### Deep Check Summary

| Task | Verdict | Judge Quality | Score Sound? | Task Design | Notes |
|------|---------|--------------|-------------|-------------|-------|
| ...  | SOUND   | SOUND        | SOUND       | REASONABLE  | ...   |
| ...  | FLAWED  | BROKEN       | FLAWED      | —           | judge rubber-stamping |

### Anomaly Details
- [task name]: [what's wrong and root cause]
```
