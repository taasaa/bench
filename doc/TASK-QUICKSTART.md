# Task Authoring Quickstart

Create a new bench eval task in ~15 minutes. This guide covers the minimum you need to ship a working task.

---

## The Five Files

Every task lives in `tasks/{tier}/{task-name}/` and needs exactly five files:

```
tasks/
└── competence/          ← tier: competence, execution, analysis, or verification
    └── my-new-task/
        ├── task.py      ← Inspect task definition
        ├── dataset.json ← Input/target pairs for evaluation
        ├── verify.sh    ← Scoring script (must be executable)
        ├── fixtures/    ← (optional) supporting files your verify.sh uses
        └── prompt.md    ← (optional) full prompt given to the model
```

---

## 1. Pick a Tier

| Tier | What it tests | Example |
|------|---------------|---------|
| **competence** | Model produces correct output given a clear spec | Format JSON, add tests, surgical fix |
| **execution** | Model completes a multi-step process correctly | Root cause debug, partial impl, intermittent bug |
| **analysis** | Model identifies subtle defects or trade-offs | Cascading failure, ghost constraint, honey trap |
| **verification** | Smoke test for infrastructure (usually doesn't score) | Inspect AI wiring, Docker sandbox, agent bridge |

---

## 2. Write `dataset.json`

```json
[
  {"id": "sample-1", "input": "The model sees this text", "target": "Expected response"},
  {"id": "sample-2", "input": "Another test case", "target": "Another response"}
]
```

- `id`: unique per sample — passed as `SAMPLE_ID` env var to `verify.sh`
- `input`: what the model sees (can be code, a description, a broken file)
- `target`: what correct behavior looks like (used by `includes()` scorer; ignored by `verify_sh`)

---

## 3. Write `task.py`

```python
from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset
from inspect_ai.scorer import match_answer

@task
def my_new_task():
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=verify_sh(),   # use this for custom verify.sh scoring
        # -or-
        scorer=match_answer() # use this for simple target-match scoring
    )
```

For `verify_sh()` scoring:
- `scorer=verify_sh()` — pipes model output to `verify.sh` on stdin
- The scorer resolves `verify.sh` relative to the task directory automatically

---

## 4. Write `verify.sh`

```bash
#!/bin/bash
# Reads model output on stdin, writes PASS N/M or FAIL to stdout

model_output=$(cat)

# Your validation logic here
# Return "PASS 2/3" if 2 of 3 checks pass
# Return "FAIL" if nothing matches

if echo "$model_output" | grep -q "expected_pattern"; then
    echo "PASS 1/1"
else
    echo "FAIL"
fi
```

**Rules:**
- Must output exactly `PASS N/M` (e.g. `PASS 3/4`) or `FAIL` on stdout
- `SAMPLE_ID` env var contains the current sample ID for per-sample routing
- Diagnostics on stderr are captured in the score explanation
- Make it executable: `chmod +x verify.sh`

---

## 5. Test It

```bash
# Test verify.sh with known input
pytest tests/test_tier1_tasks.py -k my_task -v

# Test the full task (requires model configured)
bench run --tier full --model openai/my-model
bench compare
```

**Direct test:**
```python
from tests.conftest import run_verify_script

stdout, stderr, rc = run_verify_script(
    "tasks/competence/my-new-task",
    "model output to test",
    sample_id="sample-1",
)
assert stdout.startswith("PASS")
```

---

## Scoring with `verify.sh`

The `verify_sh` scorer extracts `N/M` from `PASS N/M` → score = `N/M` (normalized to 0–1).

**Score explanation format** (written by the scorer):
```
correctness=N.M
<verify.sh stdout>
--- stderr ---
<verify.sh stderr>
```

The `correctness=N.M` field is what `bench compare` reads to populate the CORRECTNESS and COMPOSITE tables.

---

## Quick Checklist

- [ ] `task.py` has `@task` decorator and correct `dataset=` path
- [ ] `dataset.json` has `input`, `target`, `id` fields
- [ ] `verify.sh` outputs `PASS N/M` or `FAIL` (not `pass` or `Pass`)
- [ ] `verify.sh` is executable (`chmod +x`)
- [ ] Task directory is in correct tier subdirectory
- [ ] `pytest tests/test_tier1_tasks.py` shows your task's tests passing

---

## Common Mistakes

**Wrong tier:** If your task tests debugging, put it in `execution`, not `competence`.

**Missing executable:** `verify.sh` must be `chmod +x`. If it's not, the scorer returns `0.0` with "not executable" explanation.

**Wrong output format:** `bench compare` reads `correctness=N.M` from the explanation. Don't write it yourself — the scorer adds it automatically.

**Sample ID:** `SAMPLE_ID` env var lets your verify.sh route differently per sample. Use it if you have multi-fixture tasks.

**Task discovery:** `bench run --tier full` auto-discovers all `task.py` files under `tasks/competence/`, `tasks/execution/`, `tasks/analysis/`. No registration needed.