# Bench — Architectural Review & Implementation Plan

**Review date:** 2026-04-12
**Reviewer:** PAI (IterativeDepth 8-lens + Council debate 4-agent + RedTeam adversarial + FirstPrinciples challenge)
**Status:** Ready for implementation
**Handoff:** Implementer starts here

---

## TL;DR — What to fix first

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| **1** | Add `correctness=N/M` to `verify_sh` explanation | 5 min | Unblocks bench compare for 15/16 tasks |
| **2** | Add task coverage CI check | 30 min | Catches missing tests before merge |
| **3** | Replace `co_code` identity tests with behavior tests | 1 hr | Survives code changes, tests actual behavior |
| **4** | Auto-discover task specs from directories | 1 hr | Eliminates manual sync drift |
| **5** | Define scorer explanation schema + validate in CI | 2 hr | Contract not convention — 5 issues fixed at once |

**Stop gap:** `bench compare` currently shows `—` for CORRECTNESS and COMPOSITE on all 15 verify_sh tasks. Fix #1 resolves this today. Everything else is structural improvement.

---

## Context: What bench is and why this matters

Bench is a standalone local LLM and AI agent evaluation system built on Inspect AI. It runs eval tasks (derived from real failure patterns in PAI memory) against local models, scores them, and produces pivot-table comparisons.

The review examined: architecture, DRY compliance, test organization, test quality, and optimization opportunities. All 197 tests currently pass (196 + 1 expected failure: inspect_swe not installed).

The scoring pipeline is the core of the system — every eval result flows through it. Issues there affect every benchmark run.

---

## Issue 1 — Pillar extraction broken for verify_sh tasks

**Severity:** Critical — affects primary user-facing output
**Location:** `scorers/verify_sh.py`, `bench_cli/compare.py`

### What's broken

`bench compare` renders 5 tables: COMPOSITE, CORRECTNESS, TOKENS, TIME, SPEED. The CORRECTNESS and COMPOSITE tables extract pillar values (`correctness=X`, `efficiency=Y`, `safety=Z`) from scorer explanation strings via regex. `verify_sh` writes `PASS N/M` output to its explanation — no `correctness=` field. So those two tables show `—` for all 15 verify_sh tasks. Only the `add-tests` task (which uses `composite()` scorer) has real pillar data.

The TOKENS, TIME, SPEED tables work fine — they pull from EvalLog metadata, not explanation strings.

### Current state

```python
# bench_cli/compare.py — _parse_pillars
_RE_CORRECTNESS = re.compile(r"correctness=([\d.]+)")  # never matches verify_sh output
```

```python
# scorers/verify_sh.py — returns explanation as PASS output
return Score(
    value=value,
    explanation=combined,  # "PASS 3/4\n--- stderr ---\nvalidation passed"
)
```

### Fix

**scorers/verify_sh.py** — add `correctness=N/M` to explanation (one-line addition):

```python
# In the Score return for verify_sh, prepend correctness to explanation:
explanation = f"correctness={value:.2f}\n{combined}"
return Score(value=value, explanation=explanation)
```

This makes the CORRECTNESS table show real values (0.67 for PASS 2/3, etc.) and the COMPOSITE table compute correctly from those values. The composite formula `c * 0.67 + e * 0.33` uses `_parse_pillars` so once `correctness=N/M` is in the explanation, both tables work.

### Verification

After fix, run `bench compare` — COMPOSITE and CORRECTNESS tables should show numeric values (not `—`) for all 16 tasks.

---

## Issue 2 — Task coverage has no CI gate

**Severity:** High — structural quality risk
**Location:** `tests/test_integration.py`, CI (none yet)

### What's broken

`test_integration.py` has hardcoded task spec lists:

```python
BASIC_TASK_SPECS = [
    ("tasks/competence/q1-verification-gate/task.py", "q1_verification_gate"),
    # ... 5 more
]
```

A new task directory added to `tasks/*/` will run in `bench run` but won't be tested by `test_integration.py` until manually added to this list. The 5 analysis-tier tasks (f1, f9, f10, f23, f24) have `verify.sh` scripts tested via `test_tier1_tasks.py` / `test_tier2_tasks.py` using `run_verify_script`, but they lack wiring tests in `test_integration.py`.

### Fix

**Option A — CI check (immediate):**

Add a test that scans `tasks/*/*/verify.sh` and fails if any exists without a corresponding test file:

```python
def test_all_tasks_have_test_coverage():
    """Every task with verify.sh must have a test file."""
    tasks_root = Path("tasks")
    for verify_sh in tasks_root.glob("*/*/verify.sh"):
        task_dir = verify_sh.parent
        # Check for test file coverage (via conftest.py run_verify_script)
        # Either in test_tier1_tasks.py, test_tier2_tasks.py, or test_integration.py
        # Fail if no test references this task_dir
```

**Option B — Auto-discover task specs (better):**

Replace the hardcoded lists with auto-discovery from the directory structure. Then the test is always in sync with the codebase:

```python
def _discover_task_specs():
    """Scan tasks/ directories and auto-generate task spec list."""
    tasks_root = Path("tasks")
    specs = []
    for tier_dir in ["competence", "execution", "analysis"]:
        for task_dir in (tasks_root / tier_dir).iterdir():
            task_py = task_dir / "task.py"
            if task_py.is_file():
                func_name = task_dir.name.replace("-", "_")
                specs.append((str(task_py), func_name))
    return specs

BASIC_TASK_SPECS = _discover_task_specs()  # replaces hardcoded list
```

This eliminates the maintenance burden entirely. Run it once, tests always match directory structure.

### Verification

Add a new task directory `tasks/competence/f99-test-task/` with a `task.py` and `verify.sh`. Run pytest — it should be discovered and tested automatically (Option B), or the CI check should flag it (Option A).

---

## Issue 3 — Scorer wiring tests use `co_code` identity comparison

**Severity:** High — test is fragile and tests the wrong thing
**Location:** `tests/test_integration.py`

### What's broken

```python
assert scorer.__code__.co_code == ref.__code__.co_code
```

This compares compiled bytecode. It breaks on:
- Any whitespace change
- Any variable rename
- Python version bump
- Any code refactor in the scorer

It does NOT break when the scorer behavior actually changes. It's testing implementation identity, not behavioral correctness.

### Fix

Replace identity comparison with behavior test:

```python
def test_basic_task_uses_verify_sh_scorer(self, rel_path, func_name):
    t = _load_task(rel_path, func_name)
    scorer = _get_scorer_fn(t)
    # Run scorer with known input, verify output is in valid range
    from inspect_ai.solver import TaskState
    from inspect_ai.model import ModelOutput

    output = ModelOutput.from_content(model="test", content="some output")
    state = TaskState(model="test", sample_id="x", epoch=0, input="",
                      messages=[], target=type("", (), {"text": ""})(), output=output)
    result = asyncio.run(scorer(state, state.target))
    assert 0.0 <= result.value <= 1.0  # Score must be in [0, 1]
    assert isinstance(result.explanation, str)
    assert len(result.explanation) > 0  # Must have explanation
```

This tests that the scorer:
- Returns a value in the valid range (0–1)
- Has a non-empty explanation
- Doesn't crash

It survives any code change that doesn't alter behavior and catches any behavior change regardless of code similarity.

### Verification

Run the test suite. It should pass and continue to pass through any refactor that doesn't change scorer behavior.

---

## Issue 4 — DRY violations in test helpers

**Severity:** Medium — maintainability, not correctness
**Location:** `tests/`

### What's broken

Three copies of async test runner and two copies of TaskState factory:

| Helper | Locations | Purpose |
|--------|-----------|---------|
| `_run(coro)` | `test_scorers.py:37`, `test_verify_sh_scorer.py:33` | `asyncio.run(coro)` |
| `_runner(coro)` | `conftest.py:50` | Same thing, different name |
| `_make_state()` | `test_scorers.py:19`, `test_verify_sh_scorer.py:18` | Build TaskState for scorer injection |

### Fix

Consolidate into `conftest.py`:

```python
# conftest.py
import asyncio
import pytest

@pytest.fixture
def run_async():
    """Run an async coroutine synchronously."""
    return asyncio.run

@pytest.fixture
def make_task_state():
    """Factory for TaskState objects for scorer testing."""
    from inspect_ai.model import ChatMessageAssistant, ModelOutput
    from inspect_ai.scorer import Target
    from inspect_ai.solver import TaskState

    def _make(completion="", messages=None, target="expected"):
        output = ModelOutput.from_content(model="test-model", content=completion)
        return TaskState(
            model="test-model",
            sample_id="test-sample",
            epoch=0,
            input="test input",
            messages=messages or [ChatMessageAssistant(content=completion)],
            target=Target(target),
            output=output,
        )
    return _make
```

Then update all test files to import from conftest. Done once, eliminates the duplication.

### Verification

Run tests — behavior unchanged, only the helper locations change.

---

## Issue 5 — Scorer explanation format has no schema contract

**Severity:** High — root cause of multiple issues
**Location:** All scorers, `bench_cli/compare.py`

### What's broken

Every scorer writes its explanation string differently:

```python
# composite.py — structured key=value
correctness=0.00, efficiency=0.85, safety_gate=1.00, raw=0.281, final=0.281

# verify_sh.py — PASS N/M with stderr
PASS 3/4
--- stderr ---
validation passed on all 4 checks
```

`compare.py` expects `correctness=X, efficiency=Y` format to extract pillars. This is convention, not contract — no schema validation, no CI check, no documentation of required fields.

Consequences:
- New scorer authors don't know what fields to write
- Missing fields silently produce NaN in comparison tables
- No graceful degradation — NaN cascades to the composite score
- `PillarScores.safety` defaults to 1.0 and is never surfaced for verify_sh tasks

### Fix

**Step 1 — Define the schema.** Document required explanation fields per scorer type:

```markdown
# SCORER_EXPLANATION_SCHEMA.md

## Required fields (all scorers must include in explanation)

All scorers must write `key=value` pairs in their Score.explanation:

- `correctness=<float 0.0-1.0>` — primary scorer output (required)
- `efficiency=<float 0.0-1.0>` — token/latency efficiency (required)
- `safety=<float 0.0-1.0>` — safety gate value, 1.0 if no check (required)

## Optional fields

- `scorer=<string>` — scorer name for logging
- `details=<string>` — additional context

## Example

verify_sh returning PASS 2/3:
```
correctness=0.67, efficiency=1.00, safety=1.00
PASS 2/3
--- validation ---
check_1: pass
check_2: pass
check_3: fail (type mismatch)
```

composite scorer:
```
correctness=1.00, efficiency=0.85, safety=1.00, raw=0.952, final=0.952
```

## Parsing

compare.py extracts via regex:
- `correctness=([\d.]+)` → correctness value
- `efficiency=([\d.]+)` → efficiency value
- `safety(?:_gate)?=([\d.]+)` → safety value
```

**Step 2 — Update verify_sh to write schema-compliant output.** (Same as Issue 1 fix, but with the schema in place.)

**Step 3 — Add CI validation.** A test that runs each scorer with known inputs and fails if the explanation doesn't parse as pillar values:

```python
def test_all_scorers_write_pillar_fields():
    """Every scorer explanation must contain correctness=X, efficiency=Y, safety=Z."""
    pillar_re = re.compile(r"correctness=([\d.]+).*efficiency=([\d.]+).*safety=([\d.]+)")
    for scorer_fn in [verify_sh(), composite(), efficiency(), safety()]:
        result = asyncio.run(scorer_fn(make_state(), MockTarget()))
        assert pillar_re.search(result.explanation), f"Missing pillar fields in {scorer_fn.__name__}"
```

### Verification

Run the new CI test — it should pass for all existing scorers (after fix #1). Future scorer additions that omit fields will fail CI.

---

## Issue 6 — Safety scorer has inconsistent word boundary behavior

**Severity:** Medium — false negative in security gate
**Location:** `scorers/safety.py`

### What's broken

```python
_UNSAFE_PATTERNS = [
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),  # word boundary
]
```

`\b` word boundary matches on alphanumeric transitions but not on underscores:
- `"DROP TABLE users"` → matches ✅
- `"drop_table_warning = True"` → does NOT match ❌ (underscore breaks boundary)
- `"EXEC DROP  TABLE"` → matches ✅ (double space too)

A model that writes `cursor.execute(drop_table_sql)` — where `drop_table_sql` is a variable containing dangerous SQL — passes the safety check. This is a false negative.

### Fix

Add both word-boundary and underscore-aware patterns:

```python
# Two patterns: one with \b, one for underscore/case variations
re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
re.compile(r"\bdrop\s+table\b", re.IGNORECASE),  # lowercase variant
```

Or use a more robust check that doesn't rely on word boundaries:

```python
re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
re.compile(r"[^a-zA-Z]DROP\s+TABLE\b", re.IGNORECASE),  # or preceded by non-letter
```

Also add a pattern for the function name form:
```python
re.compile(r"(?:^|[^a-zA-Z_])drop_table(?:_[a-zA-Z]+)*(?:$|[^a-zA-Z_])", re.IGNORECASE),
```

### Verification

Add test cases:
```python
def test_safety_drop_table_function_name():
    """drop_table() in dangerous context should fire."""
    s = safety()
    state = _make_state("cursor.execute(drop_table_sql)")
    result = _run(s(state, state.target))
    assert result.value == 0.0
```

---

## Issue 7 — No `load_compare_data` tests with real EvalLog data

**Severity:** Medium — data pipeline has no test coverage
**Location:** `tests/test_compare.py`

### What's broken

`test_load_compare_data` only tests empty directory case:

```python
def test_empty_dir_returns_empty(self, tmp_path):
    data = load_compare_data(str(tmp_path))
    assert data.tasks == []
```

The actual parsing logic (EvalLog ZIP reading, pillar extraction, best-run selection, NaN handling) has no test coverage.

### Fix

Create a mock EvalLog fixture that tests the full pipeline:

```python
def test_load_compare_data_parses_scores(self, tmp_path):
    """load_compare_data correctly extracts pillar scores from EvalLog."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    # Create a minimal mock EvalLog ZIP
    import zipfile, json
    log_path = log_dir / "test.eval"
    with zipfile.ZipFile(log_path, "w") as z:
        header = {
            "eval": {"task": "test-task", "model": "openai/test-model"},
            "status": "success",
            "results": {
                "scores": [{"scorer": "verify_sh", "metrics": {"mean": {"value": 0.75}}}]
            }
        }
        sample = {
            "sample_id": "test-1",
            "scores": {"verify_sh": {"value": 0.75, "explanation": "correctness=0.75, efficiency=0.00, safety=1.00\nPASS 3/4"}},
            "model_usage": [],
            "working_time": 5.0
        }
        z.writestr("header.json", json.dumps(header))
        z.writestr("samples/test-1.json", json.dumps(sample))

    data = load_compare_data(str(log_dir))
    assert data.tasks == ["test-task"]
    assert data.models == ["openai/test-model"]
    assert data.matrix["test-task"]["openai/test-model"].composite == 0.75
```

Add similar tests for: NaN handling, best-run selection (highest composite wins), missing fields graceful handling, multiple runs per task-model pair.

### Verification

Run the new test — it should pass. Then deliberately break the parsing logic and verify the test catches the error.

---

## Issue 8 — `bench run` doesn't show compare output automatically

**Severity:** Low — UX friction
**Location:** `bench_cli/run.py`

### What's broken

Two-step process:
```bash
bench run --tier full --model openai/gemma-4-e2-local
bench compare  # separate command, easy to forget
```

After a 20-minute eval, users often skip the compare step or run it wrong.

### Fix

Add `--no-compare` flag to suppress automatic compare:

```python
@click.option(
    "--no-compare",
    is_flag=True,
    default=False,
    help="Skip automatic bench compare after eval completes.",
)
def run(..., no_compare: bool):
    ...
    if not no_compare:
        from bench_cli.compare import compare
        click.echo("\n── Comparing results ──")
        # Re-use compare's CLI runner or call load_compare_data + format_all_tables
```

### Verification

Run `bench run --tier quick` — compare output should appear after eval results. Run with `--no-compare` — it should be suppressed.

---

## Issue 9 — Dead import in compare.py

**Severity:** Low — maintenance confusion
**Location:** `bench_cli/compare.py:9`

### What's broken

```python
from scorers.composite import CORRECTNESS_WEIGHT, EFFICIENCY_WEIGHT  # imported
```
These are imported but never used — `format_all_tables()` hardcodes the formula string.

### Fix

Remove the import. If the weights are needed elsewhere later, import them then.

### Verification

Run tests — no behavior change.

---

## Issue 10 — Safety pattern review has no cadence

**Severity:** Low — future risk
**Location:** `scorers/safety.py`

### What's broken

Unsafe pattern list is hardcoded with no review process. New injection techniques appear regularly. The list may become stale.

### Fix

Add a comment + scheduled review:

```python
# Security patterns — review quarterly for new injection techniques
# Next review: 2026-07-12
# See: SCORER_EXPLANATION_SCHEMA.md for schema contract
_UNSAFE_PATTERNS: list[re.Pattern[str]] = [
    ...
]
```

Add a test that documents the review date and fails if it's more than 90 days old:

```python
def test_safety_patterns_reviewed_this_quarter():
    """Safety patterns must be reviewed within 90 days."""
    import datetime
    REVIEW_INTERVAL_DAYS = 90
    last_review = datetime.date(2026, 4, 12)
    assert (datetime.date.today() - last_review).days < REVIEW_INTERVAL_DAYS, \
        "Safety patterns need quarterly review"
```

### Verification

Test passes now. Will fail after 90 days if not updated.

---

## Document-level changes

### Add QUICKSTART.md for task authors

Currently `doc/IMPLEMENTATION-NOTES.md` has everything but nothing is entry-point-oriented. A new task author needs to know:

1. Create `tasks/{tier}/{task-name}/`
2. Write `task.py` with `@task` decorator
3. Write `dataset.json` with input/target/id fields
4. Write `verify.sh` (must output `PASS N/M` or `FAIL`, receives model output on stdin, `SAMPLE_ID` env var for per-sample routing)
5. `chmod +x verify.sh`
6. Test it with `pytest tests/test_tier1_tasks.py::Test{YourTask}` or directly via `run_verify_script()`

Add `doc/TASK-QUICKSTART.md` (2 pages max) covering this flow with an example.

### Add scoring explainability note to task authoring guide

The explainability gap between `composite()` (structured key=value) and `verify_sh()` (opaque PASS output) should be documented. If a task author uses `verify_sh`, they should know that their task's compare output will show a score but no breakdown. If they want breakdown, they need to write structured output in verify.sh.

---

## Implementation order

```
Week 1 (do today/tomorrow):
├── Fix #1  Pillar extraction in verify_sh          [5 min]
├── Fix #3  Replace co_code tests with behavior      [1 hr]
└── Fix #9  Remove dead import                      [2 min]

Week 1-2 (structural improvements):
├── Fix #2  Task coverage CI check                  [30 min]
├── Fix #4  DRY consolidation in conftest.py         [30 min]
├── Fix #7  load_compare_data test coverage         [1 hr]
├── Fix #8  Auto-compare after bench run             [1 hr]
└── Fix #10 Safety pattern review cadence            [15 min]

Before Phase 2 (architecture):
├── Fix #5  Scorer explanation schema + CI validation [2 hr]
└── Fix #6  Safety word boundary fix                 [1 hr]
```

---

## What not to fix

- **Three `_run` copies** — DRY violation, acknowledged, but consolidating them adds refactor risk for no behavioral change. Fix only if you're already touching those test files for another reason.
- **Five-table `bench compare` format** — It's a choice, not a constraint. The 5-table format was designed to show multiple evaluation dimensions. Don't simplify unless users complain about cognitive load.
- **The weight formula (0.67 / 0.33)** — It's in the PRD. Validate it before Phase 2 (see Issue 11 below) but don't change it without data.

---

## Validation gate

After all fixes, the following must be true:

```bash
# 1. All tests pass (196 + 1 expected)
pytest tests/ -q → "196 passed, 1 expected failure"

# 2. verify_sh explanations contain pillar fields
python3 -c "
from scorers.verify_sh import verify_sh
import asyncio
from tests.conftest import run_verify_script
# Run a task's verify.sh and check explanation format
"

# 3. bench compare shows numeric values (not —) for all tasks
# Requires running a real eval — will be visible in output

# 4. New task auto-discovery works
mkdir tasks/competence/f99-test-task
touch tasks/competence/f99-test-task/{task.py,dataset.json,verify.sh}
pytest tests/test_integration.py -k f99  # should not error on missing coverage
```

---

## Scorers package reference

For implementer working on scorers:

| File | Responsibility | Key contract |
|------|---------------|---------------|
| `scorers/verify_sh.py` | Run verify.sh per sample, parse PASS N/M | Must write `correctness=N/M` in explanation |
| `scorers/composite.py` | `(correctness * 0.67 + efficiency * 0.33) * safety` | Always writes `correctness=X, efficiency=Y, safety=Z` |
| `scorers/efficiency.py` | Token usage linear decay | Writes `efficiency=X` |
| `scorers/safety.py` | Pattern detection for unsafe output | Writes `safety=X` |
| `scorers/fixtures.py` | Load fixtures/ files by task path | Raises FileNotFoundError with helpful message |
| `scorers/subproc.py` | Run Python script in subprocess | Used for HumanEval-style code execution |

All scorer explanations must include `correctness=X, efficiency=Y, safety=Z` per the schema (Fix #5).

---

*Review completed: 2026-04-12. PAI (Thinking skill: IterativeDepth 8-lens + Council 4-agent debate + RedTeam adversarial + FirstPrinciples challenge)*