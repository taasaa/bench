# Bench — Implementation Notes

> Comprehensive record of M001 and M002: architecture, decisions, tasks, current state.
> Derived from GSD artifacts, PRDs, and direct code analysis. Updated 2026-04-12.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [CLI and Entry Points](#3-cli-and-entry-points)
4. [Task Format and Infrastructure](#4-task-format-and-infrastructure)
5. [Scorers](#5-scorers)
6. [Eval Task Inventory](#6-eval-task-inventory)
7. [Bench Compare — Pivot Table](#7-bench-compare--pivot-table)
8. [File Layout](#8-file-layout)
9. [Scoring Design](#9-scoring-design)
10. [Key Decisions](#10-key-decisions)
11. [Test Suite](#11-test-suite)
12. [Known Issues and Gotchas](#12-known-issues-and-gotchas)
13. [Milestone History](#13-milestone-history)
14. [What's Next](#14-whats-next)

---

## 1. Overview

**Bench** is a standalone local LLM and AI agent evaluation system built on [Inspect AI](https://inspect.ai). It runs evaluation tasks against models (via Inspect's `generate()` solver) or agents (via `inspect-swe` solvers) and scores results against custom scorers.

**Purpose:** Compare local LLMs on Rut's actual work — not benchmarks, but real code, real bugs, real patterns derived from actual failures.

**No external dependencies.** No PAI, no cloud services, no proprietary APIs. Everything runs locally.

**Current state:** M002 complete. 16 eval tasks organized by cognitive tier, verify_sh scorer working, pivot-table comparison working. Awaiting re-run with configured model to get real scores.

---

## 2. Architecture

```
bench/                        # Python package (pip install -e .)
│
├── bench_cli/                # User-facing CLI
│   ├── __main__.py           # entry_point: bench run | bench compare
│   ├── main.py               # Click root + shared config
│   ├── run.py                # bench run: task discovery + eval invocation
│   └── compare.py            # bench compare: EvalLog parsing + pivot table
│
├── scorers/                  # Custom Inspect AI scorers
│   ├── verify_sh.py           # verify.sh runner + call-stack task-dir resolution
│   ├── fixtures.py            # fixtures_dir(), load_fixture(), load_fixture_bytes()
│   ├── composite.py          # (correctness×0.67 + efficiency×0.33) × safety
│   ├── efficiency.py         # Token count + latency from EvalLog
│   ├── safety.py             # Safety gate scorer
│   ├── exec_scorer.py        # Subprocess execution scorer
│   └── subproc.py            # Subprocess utilities
│
├── tasks/                    # Eval task definitions
│   ├── competence/            # Tier 1 (6 tasks)
│   ├── execution/             # Tier 2 (5 tasks)
│   ├── analysis/             # Tier 3 (5 tasks)
│   └── verification/          # Smoke tests (2 tasks)
│
├── templates/                # verify.sh reference scripts
│   ├── byte-identical.sh      # Byte-for-byte output comparison
│   ├── forbidden-string.sh    # Check output doesn't contain forbidden patterns
│   ├── json-parse.sh         # Validate output is valid JSON
│   ├── line-count-delta.sh   # Check output line count delta
│   └── README.md             # Reference documentation
│
├── logs/                     # EvalLog .eval files (binary ZIP)
│   └── *.eval
│
└── tests/                    # pytest test suite
    ├── test_cli.py           # Task discovery + tier config
    ├── test_compare.py        # Pivot table formatting
    ├── test_fixtures.py      # Fixture loading
    ├── test_integration.py   # End-to-end scorer wiring
    ├── test_scorers.py       # Scorer unit tests
    ├── test_verify_patterns.py # verify.sh pattern tests
    ├── test_verify_sh_scorer.py # verify_sh scorer tests
    ├── test_tier1_tasks.py   # Competence task tests
    └── test_tier2_tasks.py   # Execution task tests
```

### Inspect AI Integration

Inspect AI provides the core evaluation engine:

- **Task loading:** `@task` decorator + `json_dataset()`
- **Solver execution:** `generate()` for model eval, `claude_code()` for agent eval
- **EvalLog format:** Binary ZIP containing `header.json`, `samples/`, `_journal/`
- **Native adapters:** Anthropic, OpenAI, Google, Ollama (local models work)
- **Hooks:** 15 lifecycle events for monitoring

Inspect runs tasks in a sandbox environment (Docker/K8s/local). Phase 1 uses local execution.

### Model Access

Models are accessed via **LiteLLM proxy** at `smallbox:4000`:

```bash
OPENAI_BASE_URL=http://smallbox:4000/v1
OPENAI_API_KEY=sk-...  # LiteLLM proxy token
```

Inspect AI's OpenAI adapter routes all models through this proxy, providing a single configuration point for all local models.

---

## 3. CLI and Entry Points

### Bench Run

```bash
bench run --tier full --model openai/gemma-4-e2-local --max-tasks 5
```

**Implementation:** `bench_cli/run.py`

1. `_discover_tasks(tier)` — scans `tasks/[TIER_DIRS[tier]]/` for `task.py` files, returns sorted list of relative paths
2. `_build_eval_spec()` — constructs Inspect `EvalSpec` with task files + model config + execution limits
3. `inspect_ai.eval()` — runs the evaluation, writes results to `logs/*.eval`

**Tiers:**
```python
TIER_DIRS = {
    "quick": ["verification"],   # smoke, agent_smoke (2 tasks)
    "full": ["competence", "execution", "analysis"],  # 16 tasks
}
```

### Bench Compare

```bash
bench compare              # Pivot table
bench compare --json       # JSON output
bench compare --latest 1  # Most recent log per task
```

**Implementation:** `bench_cli/compare.py`

Reads all `logs/*.eval` files:
1. `load_compare_data(log_dir)` — parses EvalLog ZIPs, extracts scores and model_usage
2. `CompareData` dataclass — matrix of `PillarScores` per (task, model)
3. `format_all_tables()` — renders COMPOSITE/CORRECTNESS/TOKENS/TIME/SPEED sections
4. `format_json()` — machine-readable output

### Entry Point

`bench_cli/__main__.py` is the `console_scripts` entry point:

```python
# pyproject.toml
[project.scripts]
bench = "bench_cli.main:cli"
```

`main.py` uses Click to route `bench run` → `run.py` and `bench compare` → `compare.py`.

---

## 4. Task Format and Infrastructure

### Directory Structure

```
tasks/{tier}/{task-name}/
├── task.py          # Inspect @task definition (required)
├── dataset.json    # Samples: input, target, id (required)
├── verify.sh       # Scoring script (for verify_sh tasks)
└── fixtures/       # Helper files (optional)
    ├── file_1.py
    └── file_2.txt
```

### task.py

```python
from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec
from scorers.verify_sh import verify_sh

@task
def my_task():
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=verify_sh(),
    )
```

### dataset.json

```json
[
  {
    "id": "sample-1",
    "input": "The prompt...",
    "target": "The expected answer or behavior"
  },
  ...
]
```

### verify.sh Pattern

Each `verify.sh` receives model output on stdin and outputs `PASS N/M` or `FAIL`:

```bash
#!/usr/bin/env bash
set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

cat > "$WORK_DIR/response.txt"

TOTAL_CHECKS=3
PASSED=0

# Check 1
if grep -qEi "pattern" "$WORK_DIR/response.txt"; then
    PASSED=$((PASSED + 1))
fi

# Check 2 (sample-specific via SAMPLE_ID)
case "${SAMPLE_ID:-default}" in
    sample-1) PATTERN="..." ;;
    sample-2) PATTERN="..." ;;
esac
if grep -qEi "$PATTERN" "$WORK_DIR/response.txt"; then
    PASSED=$((PASSED + 1))
fi

# Check 3
if python3 -c "..."; then
    PASSED=$((PASSED + 1))
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
fi
```

### fixtures/ and load_fixture()

Tasks with helper files expose them via `scorers.fixtures`:

```python
from scorers import fixtures_dir, load_fixture

# In verify.sh or a custom scorer:
task_file = "tasks/competence/f20-scope-calibration/task.py"
fd = fixtures_dir(task_file)  # → tasks/competence/f20-scope-calibration/fixtures/
content = load_fixture(task_file, "index.html")  # → str content
bytes_data = load_fixture_bytes(task_file, "data.bin")  # → bytes
```

Tasks with fixtures: f1-multi-file-verify (12 files), f24-honey-trap (8 files), f20-scope-calibration (3 files), q1-verification-gate (3 files), q2-do-not-touch (3 files).

---

## 5. Scorers

### verify_sh() — Main Scorer

The primary scorer for M002 tasks. Runs `verify.sh` and parses results.

**Key implementation detail (fixed in 99adecd):**

The original implementation used `os.getcwd()` to resolve `verify.sh`, which always pointed to the project root. All tasks scored 0.0 with "script not found: /Users/rut/dev/bench/verify.sh".

The fix uses **call-stack introspection** to find the task module's directory:

```python
def _find_task_dir() -> str:
    """Walk call stack to find the task module's directory."""
    for frame_info in inspect.getouterframes(inspect.currentframe(), context=2):
        path = frame_info.filename
        if "/tasks/" in path or "\\tasks\\" in path:
            task_dir = os.path.dirname(path)
            if os.path.isdir(task_dir):
                return task_dir
    return os.getcwd()

@scorer(metrics=[mean()])
def verify_sh(script_name: str = DEFAULT_SCRIPT_NAME, timeout: int = DEFAULT_TIMEOUT):
    @lru_cache(maxsize=1)
    def _cached_task_dir() -> str:
        return _find_task_dir()

    async def score(state: TaskState, target: Target) -> Score:
        task_dir = _cached_task_dir()
        script_path = os.path.join(task_dir, script_name)
        # ... run script, parse PASS N/M ...
```

Cached because all samples in the same task share the same directory.

**Result parsing:**
- `PASS N/M` → score = N/M (e.g., `PASS 3/4` → 0.75)
- `PASS` (bare) → score = 1.0
- `FAIL` or anything else → score = 0.0

### composite()

Used by add-tests task. Implements `(correctness × 0.67 + efficiency × 0.33) × safety_gate`.

```python
# scorers/composite.py
@scorer(metrics=[mean()])
def composite():
    async def score(state: TaskState, target: Target) -> Score:
        # Run efficiency and safety scorers, combine
        eff = efficiency(state, target)
        safe = safety(state, target)
        composite = correctness * 0.67 + eff.value * 0.33
        return Score(value=composite * safe.value, ...)
```

### Other Scorers

| Scorer | Purpose |
|--------|---------|
| `efficiency()` | Token count + latency from EvalLog |
| `safety()` | Safety gate (blocks dangerous tool calls) |
| `exec_scorer()` | Run subprocess and score output |

---

## 6. Eval Task Inventory

### Competence (Tier 1) — Foundational Skills

| Task | Description | Scorer | Samples |
|------|-------------|--------|---------|
| q1-verification-gate | Parse pytest output, report failures | verify_sh | 3 |
| q2-do-not-touch | Identify and don't modify flagged sections | verify_sh | 3 |
| f7-format-compliance | Enforce output format requirements | verify_sh | 4 |
| f12-surgical-fix | Fix exactly one buggy line | verify_sh | 4 |
| f20-scope-calibration | Make changes only in specified scope | verify_sh | 3 |
| add-tests | Write unit tests for existing code | composite | 5 |

### Execution (Tier 2) — Reliable Execution

| Task | Description | Scorer | Samples |
|------|-------------|--------|---------|
| f6-partial-impl | Complete partially-implemented functions | verify_sh | 4 |
| f8-negative-constraint | Avoid prohibited patterns | verify_sh | 4 |
| f11-intermittent-bug | Find non-deterministic failures | verify_sh | 4 |
| f14-insert-dont-replace | Insert without modifying existing code | verify_sh | 4 |
| q4-root-cause | Debug and fix root cause | verify_sh | 4 |

### Analysis (Tier 3) — Deep Reasoning

| Task | Description | Scorer | Samples |
|------|-------------|--------|---------|
| f1-multi-file-verify | Cross-reference multiple files against claims | verify_sh | 4 |
| f9-cascading-failure | Trace failure chains | verify_sh | 4 |
| f10-env-mismatch | Detect environment-specific bugs | verify_sh | 4 |
| f23-ghost-constraint | Respect constraints from early turns | verify_sh | 4 |
| f24-honey-trap | Avoid security/antipattern traps | verify_sh | 4 |

### Verification (Smoke Tests)

| Task | Description | Scorer | Samples |
|------|-------------|--------|---------|
| smoke | Basic model eval smoke test | includes | 1 |
| agent_smoke | Agent eval smoke test (requires inspect_swe) | includes | 1 |

**Total: 16 eval tasks + 2 smoke tests = 18 discoverable tasks**

---

## 7. Bench Compare — Pivot Table

### Data Model

```python
@dataclass
class PillarScores:
    correctness: float          # Primary metric (0.0–1.0 or NaN)
    composite: float            # Combined score
    avg_time: float             # Avg wall-clock seconds per sample
    avg_tokens: float           # Avg tokens per sample
    avg_tokens_per_sec: float   # Tokens/second
    samples: int                # Number of scored samples
    scorer: str                 # Scorer name used

@dataclass
class CompareData:
    tasks: list[str]                                    # Task names
    models: list[str]                                   # Model names
    matrix: dict[str, dict[str, PillarScores | None]]    # (task, model) → scores
```

### Formatting

Five pivot tables are rendered:

1. **COMPOSITE** — `(correctness × 0.67 + efficiency × 0.33) × safety`
2. **CORRECTNESS** — Did the model produce the right output?
3. **TOKENS** — Average token consumption
4. **TIME** — Average wall-clock time per sample
5. **TOKENS/SEC** — Throughput metric

### Display Format

- NaN/unavailable cells → `—`
- Composite/correctness: 2 decimal places
- Time: `12.3s` or `2m05s`
- Tokens: `1.2k` or `450`

### JSON Output

`bench compare --json` outputs machine-readable format:

```json
[
  {
    "task": "add_tests",
    "model": "openai/gemma-4-26-local",
    "scorer": "composite",
    "composite": 0.76,
    "correctness": 1.0,
    "avg_time": 24.0,
    "avg_tokens": 1200.0,
    "tokens_per_sec": 50.0,
    "samples": 5
  }
]
```

---

## 8. File Layout

### Key Source Files

```
bench_cli/run.py          # 168 lines. _discover_tasks(), _build_eval_spec(), run_eval()
bench_cli/compare.py      # 419 lines. CompareData, PillarScores, load/format functions
bench_cli/main.py         # 19 lines. Click CLI root + @click.group()

scorers/verify_sh.py      # 123 lines. verify_sh() scorer + _find_task_dir() stack introspection
scorers/fixtures.py        # 86 lines. fixtures_dir(), load_fixture(), load_fixture_bytes() (with lru_cache)
scorers/composite.py      # 64 lines. composite() scorer
scorers/efficiency.py     # 24 lines. efficiency() scorer
scorers/safety.py         # 52 lines. safety() scorer
scorers/__init__.py       # Exports verify_sh, fixtures_dir, load_fixture, etc.
```

### Key GSD Artifacts

```
.gsd/REQUIREMENTS.md    # R001–R017 active requirements
.gsd/DECISIONS.md      # D001–D021 decisions register
.gsd/KNOWLEDGE.md      # Project-specific gotchas and patterns
.gsd/PROJECT.md        # Living project description
.gsd/CODEBASE.md       # Auto-generated file map
.gsd/ROADMAP.md        # Milestone roadmap
.gsd/milestones/       # Per-milestone artifacts (M001, M002)
```

### Template Reference Scripts

```
templates/byte-identical.sh   # Compare output byte-for-byte against expected
templates/forbidden-string.sh # Fail if output contains forbidden patterns
templates/json-parse.sh        # Validate JSON + check expected fields
templates/line-count-delta.sh # Check output line count matches expected delta
templates/README.md            # Pattern documentation (129 lines)
```

---

## 9. Scoring Design

### Formula

```
composite = (correctness × 0.67 + efficiency × 0.33) × safety_gate
```

Where:
- **correctness**: Primary scorer metric (e.g., verify_sh score, accuracy)
- **efficiency**: Token usage + latency relative to reference (lower tokens + faster = higher score)
- **safety_gate**: 1.0 (Phase 1, no unsafe tool calls expected) or 0.0 (blocked dangerous operation)

### verify_sh Scoring

```
value = N / M  (PASS N/M from verify.sh)
```

- `PASS 3/3` → 1.0
- `PASS 2/4` → 0.5
- `FAIL` or anything else → 0.0
- Bare `PASS` → 1.0
- Timeout or error → 0.0 with diagnostic explanation

### composite Scoring

Used by add-tests (and future code-gen tasks):

- correctness: from `includes()` or custom scorer
- efficiency: `tokens_used / reference_tokens × time_weight`
- safety: from safety() scorer

---

## 10. Key Decisions

| D | Decision | Rationale |
|---|----------|-----------|
| D001 | LiteLLM proxy at smallbox:4000 | Single config point, no per-provider keys |
| D002 | Tasks as `@task` Python files | Direct Inspect integration, no custom registry |
| D003 | Agent eval via inspect-swe | Production-ready, Inspect captures all tokens/calls |
| D004 | Phase 1 includes both model and agent eval | Both are core capabilities |
| D005 | Pin Inspect AI version | Prevent breakage from near-daily releases |
| D006 | Scoring: (correct × 0.67 + eff × 0.33) × safety | PRD-specified formula |
| D019 | Task format: task.py + dataset.json + verify.sh + fixtures/ | Existing pattern works, no new framework needed |
| D020 | F23 single-prompt approach | Inspect generate() is single-turn, custom solver overkill |
| D021 | Remove 4 synthetic tasks, keep add-tests only | Removed tasks are weaker EVAL-TASK versions; add-tests is unique |

### M002 Scope Decisions

**Removed tasks:** write-function, fix-bug, edit-file, find-replace (4 synthetic M001 tasks, D021)

**Kept:** add-tests only from original code_gen/

**Rationale:** The 4 removed tasks are weaker versions of the EVAL-TASK derived tasks. add-tests tests a unique skill (writing unit tests) not covered by any EVAL-TASK.

**Directory reorganization:**
- `code_gen/` → merged into `competence/` (add-tests moved)
- `basic/` → split into `competence/`, `execution/`, `analysis/`
- `file_ops/` → deleted (contained removed synthetic tasks)

---

## 11. Test Suite

```bash
python3 -m pytest tests/              # All tests
python3 -m pytest tests/test_cli.py   # CLI tests only
python3 -m pytest tests/test_verify_patterns.py -v  # verify.sh pattern tests
```

### Test Coverage

| Test file | What it tests |
|-----------|---------------|
| test_cli.py | Task discovery, tier config, max-tasks |
| test_compare.py | CompareData, PillarScores, pivot table formatting, JSON output |
| test_fixtures.py | fixtures_dir(), load_fixture() |
| test_integration.py | Scorer wiring per task, dataset validity |
| test_scorers.py | Unit tests for efficiency, safety, composite |
| test_verify_patterns.py | 4 template verify.sh scripts (25 test cases) |
| test_verify_sh_scorer.py | verify_sh scorer: PASS/FAIL parsing, timeout, missing script |
| test_tier1_tasks.py | Competence task tests |
| test_tier2_tasks.py | Execution task tests |

**Current: 181 passing, 1 expected failure** (agent_smoke: inspect_swe not installed).

---

## 12. Known Issues and Gotchas

### verify.sh Must Be Executable

```bash
chmod +x tasks/*/verify.sh tasks/*/*/verify.sh
```

The scorer checks `os.access(script_path, os.X_OK)` before running.

### POSIX Regex Only in verify.sh

Use `grep -E` instead of `grep -P`. Use `[[:space:]]` instead of `\s` for macOS compatibility.

### SAMPLE_ID Environment Variable

`verify.sh` receives `SAMPLE_ID` in its environment. Use it to branch on per-sample patterns:

```bash
case "${SAMPLE_ID:-default}" in
    sample-1) PATTERN="..." ;;
    sample-2) PATTERN="..." ;;
esac
```

### Inspect EvalLog Is Binary ZIP

Decode with `zipfile`, not `json.loads()` directly:

```python
import zipfile, json
with zipfile.ZipFile("logs/foo.eval") as z:
    header = json.loads(z.read("header.json"))
    sample = json.loads(z.read("samples/foo_epoch_1.json"))
```

### Model Routing via LiteLLM

```bash
OPENAI_BASE_URL=http://smallbox:4000/v1
OPENAI_API_KEY=sk-...  # LiteLLM proxy token
```

### Stack Introspection for Task Dir

`_find_task_dir()` in `scorers/verify_sh.py` uses `inspect.getouterframes()` to walk the call stack and find `/tasks/` in frame paths. This is the correct approach — Inspect AI provides no API for task directory access.

---

## 13. Milestone History

### M001 — Phase 1 MVP (14f0641)

**Status:** Complete

**Scope:**
- Project scaffolding (pyproject.toml, bench package)
- Task format (task.py + dataset.json)
- 4 synthetic tasks (write-function, fix-bug, edit-file, find-replace) + add-tests
- Custom scorers (composite, efficiency, safety)
- `bench run` CLI (Click-based)
- `bench compare` (per-task breakdown)
- LiteLLM integration

**Key files added:**
- `bench_cli/run.py`, `bench_cli/compare.py`, `bench_cli/main.py`
- `scorers/composite.py`, `scorers/efficiency.py`, `scorers/safety.py`
- `tasks/code_gen/add-tests/`, `tasks/file_ops/` (4 tasks)

### M002 — Real Tasks from Real Failures (d09102d)

**Status:** Complete

**Scope:**
- 15 eval tasks derived from actual work/failures
- verify_sh scorer with fixtures infrastructure
- 4 verify.sh reference templates
- Tasks organized by cognitive tier (competence/execution/analysis)
- Removed 4 synthetic M001 tasks
- 181 passing tests

**Key files added:**
- `scorers/verify_sh.py`, `scorers/fixtures.py`
- All 15 tasks in `tasks/{competence,execution,analysis}/`
- `templates/` directory with verify.sh patterns

**Post-M002 fixes:**
- 99adecd: verify_sh task-dir fix (call-stack introspection)
- cf33838: test_compare.py rewrite for new pivot-table API
- fcbfeee: M001 task removal, directory reorganization
- 9b06028: cognitive tier naming
- b2694a2: log cleanup

---

## 14. What's Next

### Immediate (Pre-Phase-2)

1. **Re-run eval with configured model** — verify_sh fix (99adecd) deployed, re-run all 16 tasks to get real scores
2. **Verify benchmark comparison** — `bench compare` should show meaningful scores for competence/execution/analysis tasks

### Phase 2

1. **LLM Judge** — Calibrate LLM-as-judge with Cohen's Kappa >= 0.61 on 30+ tasks before deploying
2. **Statistics** — Bootstrap CI + Cohen's d for comparing model pairs (requires 30+ tasks)
3. **Real task derivation** — Mine actual work sessions for new tasks

### Future

- **Agent eval** — inspect-swe integration (requires `pip install inspect-swe` and Docker)
- **Docker sandbox** — Phase 2+ sandbox for agent eval isolation
- **Approval system** — Real-time blocking of dangerous tool calls
- **inspect view** — Interactive EvalLog inspection at localhost:7575

---

*Last updated: 2026-04-12*
*Authors: GSD agent, co-authored with human*
