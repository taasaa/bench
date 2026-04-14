# Bench — Implementation Notes

> Comprehensive record of architecture, decisions, tasks, and current state.
> Derived from PRDs, code analysis, and session history. Updated 2026-04-14.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [CLI and Entry Points](#3-cli-and-entry-points)
4. [Task Format and Infrastructure](#4-task-format-and-infrastructure)
5. [Scorers](#5-scorers)
6. [Eval Task Inventory](#6-eval-task-inventory)
7. [Bench Compare — Pillar Table](#7-bench-compare--pillar-table)
8. [File Layout](#8-file-layout)
9. [Scoring Design](#9-scoring-design)
10. [Key Decisions](#10-key-decisions)
11. [Test Suite](#11-test-suite)
12. [Known Issues and Gotchas](#12-known-issues-and-gotchas)
13. [History](#13-history)
14. [What's Next](#14-whats-next)

---

## 1. Overview

**Bench** is a standalone local LLM and AI agent evaluation system built on [Inspect AI](https://inspect.ai). It runs evaluation tasks against models (via Inspect's `generate()` solver) or agents (via `inspect-swe` solvers) and scores results against custom scorers.

**Purpose:** Compare local LLMs on real code, real bugs, real patterns derived from actual failures.

**No external dependencies.** No PAI, no cloud services, no proprietary APIs. Everything runs locally.

**Current state:** 16 eval tasks, dual correctness scoring (verify_sh + LLM judge), 3-pillar scoring (correctness + efficiency + latency), multi-model comparison with baselines. Phase 1 complete.

---

## 2. Architecture

```
bench/                        # Python package (pip install -e .)
│
├── bench_cli/                # User-facing CLI
│   ├── __main__.py           # entry_point: bench run | bench compare | bench baseline
│   ├── main.py               # Click root + shared config
│   ├── run.py                # bench run: task discovery + eval invocation
│   ├── compare.py            # bench compare: EvalLog parsing + pillar table
│   └── baseline.py           # bench baseline record/list
│
├── scorers/                  # Custom Inspect AI scorers
│   ├── verify_sh.py          # Shell-script correctness scorer (PASS N/M)
│   ├── llm_judge.py          # LLM-as-judge correctness scorer (SCORE: N)
│   ├── token_ratio.py        # Efficiency scorer (ref_tokens / actual_tokens)
│   ├── time_ratio.py         # Latency scorer (ref_seconds / actual_seconds)
│   ├── task_budgets.py       # Per-task calibrated budgets from baselines
│   ├── baseline_store.py     # Baseline persistence (baselines/{task}/{model}.json)
│   ├── protocol.py           # PillarScorer protocol, constants, helpers
│   ├── fixtures.py           # fixtures_dir(), load_fixture(), load_fixture_bytes()
│   ├── composite_safety.py   # min() of active safety sub-scores
│   ├── execution_safety.py   # Dangerous command pattern detection
│   ├── constraint.py         # Constraint adherence scorer
│   ├── output_safety.py      # PII/pattern output safety
│   ├── composite.py          # Legacy composite scorer (add-tests task)
│   ├── efficiency.py         # Legacy efficiency scorer
│   ├── safety.py             # Legacy safety scorer
│   ├── exec_scorer.py        # Subprocess execution scorer
│   └── subproc.py            # Subprocess utilities
│
├── tasks/                    # Eval task definitions
│   ├── competence/            # 6 tasks
│   ├── execution/             # 5 tasks
│   ├── analysis/             # 5 tasks
│   └── verification/          # Smoke tests (2 tasks)
│
├── templates/                # verify.sh reference scripts
│
├── logs/                     # EvalLog .eval files (binary ZIP)
│
└── tests/                    # pytest test suite (238 tests)
```

### Inspect AI Integration

Inspect AI provides the core evaluation engine:

- **Task loading:** `@task` decorator + `json_dataset()`
- **Solver execution:** `generate()` for model eval, `claude_code()` for agent eval
- **EvalLog format:** Binary ZIP containing `header.json`, `samples/`, `_journal/`
- **Native adapters:** Anthropic, OpenAI, Google, Ollama (local models work)
- **Scoring:** `@scorer(metrics=[mean()])` decorator, async `score(state, target) -> Score`

Inspect runs tasks in a sandbox environment (Docker/K8s/local). Phase 1 uses local execution.

### Model Access

Models are accessed via **LiteLLM proxy** at `smallbox:4000`:

```bash
OPENAI_BASE_URL=http://smallbox:4000/v1
OPENAI_API_KEY=sk-...  # LiteLLM proxy token
```

All models use `openai/<alias>` format. Available models include: qwen-local, gemma-4-26-local, gemma-4-e2-local, glm-local, qwen3-max, qwen3-coder-plus, opus, pro, judge, and more.

---

## 3. CLI and Entry Points

### Bench Run

```bash
bench run --tier full --model openai/qwen-local
bench run --tier quick --model openai/gemma-4-e2-local
bench run --tier full --task q4-root-cause --model openai/qwen-local
bench run --tier full --model openai/qwen-local --one-by-one
```

**Implementation:** `bench_cli/run.py`

1. `_discover_tasks(tier)` — scans `tasks/[TIER_DIRS[tier]]/` for `task.py` files
2. `_resolve_task(spec)` — loads task module, injects `bench_task_dir` into sample metadata, applies GenerateConfig (timeout=600, attempt_timeout=300)
3. `inspect_ai.eval()` — runs the evaluation, writes results to `logs/*.eval`
4. Auto-compares after eval unless `--no-compare`

**Tiers:**
```python
TIER_DIRS = {
    "quick": ["verification"],   # smoke, agent_smoke (2 tasks)
    "full": ["competence", "execution", "analysis"],  # 16 tasks
}
```

### Bench Compare

```bash
bench compare                    # Pillar table from logs/
bench compare --log-dir baselines # Compare from baselines dir
bench compare --latest 5         # Last 5 runs per task
bench compare --json             # Machine-readable JSON
```

**Implementation:** `bench_cli/compare.py`

Single pillar table with per-model columns:
1. `load_compare_data(log_dir)` — parses EvalLog files, extracts all scorers per sample
2. `_extract_from_scorers()` — reads `llm_judge` (preferred) or `verify_sh` for correctness, `token_ratio_scorer` for efficiency, `time_ratio_scorer` for latency
3. `PillarScores` dataclass — correctness, token_ratio, time_ratio, avg_tokens, avg_time
4. `format_pillar_table()` — renders table with geometric mean for ratio aggregates

### Bench Baseline

```bash
bench baseline record --model openai/qwen-local --tier full
bench baseline record --model openai/qwen-local --force  # skip correctness gate
bench baseline list
```

**Implementation:** `bench_cli/baseline.py`

Records measured eval results for ratio scoring references:
1. Runs full eval for the model
2. For each task, writes `baselines/{task_id}/{model_id}.json`
3. Applies correctness validity gate (default 0.8) — invalid baselines not used for ratio references

### Entry Point

`bench_cli/__main__.py` is the `console_scripts` entry point:

```python
# pyproject.toml
[project.scripts]
bench = "bench_cli.main:cli"
```

`main.py` uses Click to route `bench run`, `bench compare`, and `bench baseline`.

---

## 4. Task Format and Infrastructure

### Directory Structure

```
tasks/{tier}/{task-name}/
├── task.py          # Inspect @task definition (required)
├── dataset.json    # Samples: input, target, id (required)
├── verify.sh       # Script correctness scorer (for verify_sh tasks)
├── judge.md        # LLM judge rubric (for llm_judge tasks)
└── fixtures/       # Helper files (optional)
```

### task.py (verify_sh task)

```python
from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.verify_sh import verify_sh
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer

@task
def my_task():
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=[verify_sh(), token_ratio_scorer(task_budget=get_task_budget("my_task")), time_ratio_scorer(task_budget=get_task_budget("my_task"))],
    )
```

### task.py (llm_judge task)

```python
from scorers.llm_judge import llm_judge
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer

@task
def my_task():
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=[llm_judge(), token_ratio_scorer(task_budget=get_task_budget("my_task")), time_ratio_scorer(task_budget=get_task_budget("my_task"))],
    )
```

### Correctness Scorer Selection

Tasks use either `verify_sh` or `llm_judge` for correctness — never both:

| Scorer | Used for | How it works |
|--------|----------|--------------|
| `verify_sh()` | Deterministic checks (exact output, file structure, test execution) | Runs `verify.sh` script, parses PASS N/M |
| `llm_judge()` | Open-ended reasoning (diagnosis, analysis, constraint compliance) | Calls judge model with per-task `judge.md` rubric, parses SCORE: N (0-10 → 0-1) |

---

## 5. Scorers

### Three-Pillar Architecture

Each task produces 3 independent scores:

| Pillar | Scorer | Value | Interpretation |
|--------|--------|-------|----------------|
| Correctness | `verify_sh` or `llm_judge` | 0.0–1.0 | Did the model produce the right output? |
| Efficiency | `token_ratio_scorer` | unbounded ratio | `ref_tokens / actual_tokens` (>1.0 = more efficient) |
| Latency | `time_ratio_scorer` | unbounded ratio | `ref_seconds / actual_seconds` (>1.0 = faster) |

No composite formula. Each pillar stands alone.

### verify_sh() — Script Correctness Scorer

Pipes model output through task-specific `verify.sh` script. Parses JSON or text output:

- JSON: `{"passed": N, "total": M, "checks": [...]}`
- Text: `PASS N/M` or `PASS` or `FAIL`
- Score = N/M normalized to [0.0, 1.0]
- Per-check breakdown stored in `Score.metadata`

Uses `bench_task_dir` from sample metadata (injected by `_resolve_task` in `run.py`) to locate `verify.sh`.

### llm_judge() — LLM Judge Correctness Scorer

Calls a fixed judge model (`openai/judge` → GLM-5.1 via LiteLLM proxy) with:
- Task prompt, expected answer, model output
- Per-task `judge.md` rubric with grading criteria
- Returns `SCORE: N` (0-10), normalized to 0-1

Key implementation details:
- Model resolved once at factory time (not per-sample)
- Rubric files cached per task directory (one file read per task, not per sample)
- Graceful degradation: missing rubric → 0.0, API error → 0.0, unparseable response → 0.0

### token_ratio_scorer() — Efficiency Scorer

Unbounded ratio: `reference_output_tokens / actual_total_tokens`

3-tier reference resolution:
1. BaselineStore (measured run) → highest fidelity
2. TaskBudget (per-task calibrated budgets) → author intent
3. SYSTEM_DEFAULT_BUDGETS (1000 tokens) → scaffolding fallback

Loop detection: flags `potential_loop=True` when message count exceeds threshold (50).

### time_ratio_scorer() — Latency Scorer

Unbounded ratio: `reference_seconds / actual_seconds`

Uses `sample_working_time()` from Inspect AI (model + sandbox time, excluding concurrency wait).

Noise floor: suppresses ratio when `min(reference, actual) < noise_floor` (default 5s) — shown as `--` in compare.

### BaselineStore

Persists measured eval results in `baselines/{task_id}/{model_id}.json`. Provides reference values for ratio scorers. Correctness validity gate (default 0.8) — baselines where the reference model failed the task are not used.

---

## 6. Eval Task Inventory

### Competence — Foundational Skills

| Task | Description | Correctness Scorer | Samples |
|------|-------------|---------------------|---------|
| q1-verification-gate | Parse pytest output, report failures | verify_sh | 3 |
| q2-do-not-touch | Identify and don't modify flagged sections | verify_sh | 3 |
| f7-format-compliance | Enforce output format requirements | verify_sh | 4 |
| f12-surgical-fix | Fix exactly one buggy line | verify_sh | 4 |
| f20-scope-calibration | Make changes only in specified scope | verify_sh | 3 |
| add-tests | Write unit tests for existing code | verify_sh (composite legacy) | 5 |

### Execution — Reliable Execution

| Task | Description | Correctness Scorer | Samples |
|------|-------------|---------------------|---------|
| f6-partial-impl | Complete partially-implemented functions | verify_sh | 4 |
| f8-negative-constraint | Avoid prohibited patterns | verify_sh | 4 |
| f11-intermittent-bug | Find non-deterministic failures | **llm_judge** | 4 |
| f14-insert-dont-replace | Insert without modifying existing code | verify_sh | 4 |
| q4-root-cause | Debug and fix root cause | **llm_judge** | 4 |

### Analysis — Deep Reasoning

| Task | Description | Correctness Scorer | Samples |
|------|-------------|---------------------|---------|
| f1-multi-file-verify | Cross-reference multiple files against claims | **llm_judge** | 4 |
| f9-cascading-failure | Trace failure chains | **llm_judge** | 4 |
| f10-env-mismatch | Detect environment-specific bugs | **llm_judge** | 4 |
| f23-ghost-constraint | Respect constraints from early turns | **llm_judge** | 4 |
| f24-honey-trap | Avoid security/antipattern traps | verify_sh | 4 |

### Verification (Smoke Tests)

| Task | Description | Scorer | Samples |
|------|-------------|--------|---------|
| smoke | Basic model eval smoke test | includes | 1 |
| agent_smoke | Agent eval smoke test (requires inspect_swe) | includes | 1 |

**Total: 16 eval tasks (10 verify_sh + 6 llm_judge) + 2 smoke tests**

---

## 7. Bench Compare — Pillar Table

### Data Model

```python
@dataclass
class PillarScores:
    correctness: float       # 0.0-1.0 from verify_sh or llm_judge
    token_ratio: float       # unbounded, >1.0 = more efficient
    time_ratio: float        # unbounded, >1.0 = faster
    avg_tokens: float        # mean total tokens per sample
    avg_time: float          # mean working_time per sample in seconds
    samples: int
    token_suppressed: int    # samples below noise floor
    time_suppressed: int
```

### Formatting

```
TASK                  CORRECT  TOK_RATIO  TIME_RATIO  TOKENS    TIME
f6_partial_impl          1.00       1.04        1.29     728   30.4s
q4_root_cause            1.00       0.35        0.37    3.0k   1m22s
f11_intermittent_bug     0.90       0.35        0.56    4.4k   1m39s
MEAN                     0.97       0.50        0.64    2.7k   1m10s
```

- Ratios > 1.0 = better than reference
- Geometric mean for ratio aggregates (MEAN row)
- `--` = suppressed (below noise floor) or no data

### Correctness Source

`_extract_from_scorers()` checks for `llm_judge` first, falls back to `verify_sh`. Tasks use one or the other, producing a single CORRECT value comparable across models.

---

## 8. File Layout

### Key Source Files

```
bench_cli/run.py          # Task discovery, _resolve_task() with metadata injection
bench_cli/compare.py      # CompareData, PillarScores, pillar table formatting
bench_cli/baseline.py     # Baseline recording with correctness validity gate
bench_cli/main.py         # Click CLI root

scorers/verify_sh.py      # Shell-script correctness scorer
scorers/llm_judge.py      # LLM-as-judge correctness scorer
scorers/token_ratio.py    # Efficiency scorer with 3-tier reference chain
scorers/time_ratio.py     # Latency scorer with noise floor suppression
scorers/task_budgets.py   # Per-task calibrated budgets from baseline data
scorers/baseline_store.py # Baseline persistence (baselines/{task}/{model}.json)
scorers/protocol.py       # PillarScorer protocol, constants, resolve_baseline_reference()
scorers/__init__.py       # Package exports
```

---

## 9. Scoring Design

### Three Independent Pillars

No composite formula. Each pillar is scored independently:

1. **Correctness** (0.0–1.0): `verify_sh` (script) or `llm_judge` (LLM rubric)
2. **Efficiency** (unbounded ratio): `ref_tokens / actual_tokens` — 3-tier reference chain
3. **Latency** (unbounded ratio): `ref_seconds / actual_seconds` — noise floor suppression

### Reference Resolution (Efficiency + Latency)

```
1. Baseline store (valid_for_reference: true)  → measured run (highest fidelity)
2. TaskBudget (per-task calibrated values)       → author intent
3. SYSTEM_DEFAULT_BUDGETS (1000 tokens / 30s)    → scaffolding fallback
```

### Judge Scoring (Correctness for 6 tasks)

```
Judge model (openai/judge → GLM-5.1) receives:
  - Task prompt (state.input_text)
  - Expected answer (target.text)
  - Model output (state.output.completion)
  - Per-task rubric (judge.md)

Returns SCORE: N (0-10), normalized to 0.0-1.0
```

---

## 10. Key Decisions

| Decision | Rationale |
|----------|-----------|
| LiteLLM proxy at smallbox:4000 | Single config point, no per-provider keys |
| Tasks as `@task` Python files | Direct Inspect integration, no custom registry |
| Three independent pillars, no composite | Each pillar interpretable on its own; no opaque formula |
| verify_sh OR llm_judge per task | Tasks use whichever scorer fits; single CORRECT value for comparison |
| Custom scorer over Inspect's model_graded_qa | Inspect uses C/P/I grades; we need 0-1 scoring with per-task rubrics |
| Judge model = separate from model under test | Prevents self-preference bias (GLM-5.1 as judge, eval models are qwen/gemma) |
| Unbounded ratios for efficiency/latency | Preserves signal in both directions; geometric mean for aggregation |
| Baseline correctness validity gate (0.8) | Fast-but-wrong baseline penalizes correct-but-slower models |
| Per-task calibrated budgets | Measured from actual qwen-local baseline runs, not guessed |
| `bench_task_dir` via sample metadata | Stack introspection fails in Inspect's async event loop |
| Rubric caching + model resolution at factory time | Avoids per-sample file I/O and model resolution overhead |

---

## 11. Test Suite

```bash
pytest                       # All tests (238 passed, 2 skipped)
pytest tests/test_scorers.py # Scorer unit tests (62 tests)
pytest tests/test_compare.py # Compare formatting tests
```

### Test Coverage

| Test file | What it tests | Count |
|-----------|---------------|-------|
| test_cli.py | Task discovery, tier config, max-tasks | 18 |
| test_compare.py | PillarScores, pillar table formatting, JSON output, _numeric_val helper | 15 |
| test_fixtures.py | fixtures_dir(), load_fixture() | 11 |
| test_integration.py | Scorer wiring per task, dataset validity | 22 |
| test_scorers.py | All scorer units: efficiency, safety, composite, token_ratio, time_ratio, execution_safety, constraint, baseline_store, **llm_judge** (parse_score, load_rubric, error paths, mocked scoring, caching) | 62 |
| test_verify_patterns.py | 4 template verify.sh scripts | 25 |
| test_verify_sh_scorer.py | verify_sh scorer: PASS/FAIL parsing, timeout, missing script | 9 |
| test_tier1_tasks.py | Competence task tests | 19 |
| test_tier2_tasks.py | Execution task tests | 42 |

**LLM judge tests** (21 tests in test_scorers.py):
- `TestParseScore` (11): regex extraction for SCORE: N — integer, fractional, zero, clamping, edge cases
- `TestLoadRubric` (3): file loading — existing rubric, missing rubric, nonexistent dir
- `TestLLMJudgeScorer` (7): scorer integration with mocked model — no task dir, missing rubric, empty output, API error, unparseable response, successful scoring, rubric caching

All LLM judge tests use mocked models — no real API calls in test suite.

---

## 12. Known Issues and Gotchas

### verify.sh Must Be Executable

```bash
chmod +x tasks/*/verify.sh tasks/*/*/verify.sh
```

### POSIX Regex Only in verify.sh

Use `grep -E` instead of `grep -P`. Use `[[:space:]]` instead of `\s` for macOS compatibility.

### SAMPLE_ID Environment Variable

`verify.sh` receives `SAMPLE_ID` in its environment. Use it to branch on per-sample patterns.

### sample.model_usage Is a Dict

Keyed by model name, not an object. Iterate `.values()` to aggregate tokens.

### Task Metadata Propagation

`task.metadata` does NOT propagate to `state.metadata`. Must inject into `sample.metadata` at `_resolve_task` time. The scorer reads `state.metadata["bench_task_dir"]`.

### Inspect EvalLog Is Binary ZIP

Use `read_eval_log()` from `inspect_ai.log`, not raw `json.loads()`.

### GenerateConfig Import Path

`from inspect_ai._eval.task.run import GenerateConfig` — internal API, may change across Inspect versions.

### sample_working_time()

`from inspect_ai._util.working import sample_working_time` — returns a huge number when outside eval context. Cap sanity check at 86400s.

---

## 13. History

### Phase 1 — MVP + Real Tasks

- Project scaffolding, task format, 16 eval tasks from real failure analysis
- verify_sh scorer, fixtures infrastructure, verify.sh templates
- Tasks organized by cognitive tier (competence/execution/analysis)
- LiteLLM integration, CLI (`bench run`, `bench compare`)

### Phase 1A — Pillar Scoring Rework

- Dropped composite formula, three independent pillars
- Token ratio scorer with 3-tier reference chain
- Time ratio scorer with noise floor suppression
- Per-task calibrated budgets from baseline measurements
- Baseline store with correctness validity gate
- Compare.py rewrite for pillar table with geometric mean

### Phase 1B — LLM Judge + Baselines

- `llm_judge.py` scorer using Inspect's `get_model()` + `model.generate()`
- 6 tasks migrated from verify_sh to llm_judge with per-task `judge.md` rubrics
- Judge model: `openai/judge` → GLM-5.1 via LiteLLM proxy
- Baselines recorded for qwen-local and gemma-4-26-local
- compare.py reads either scorer for single CORRECT column
- 238 tests passing (21 new for LLM judge)

---

## 14. What's Next

### Phase 1C (Immediate)

- Record more model baselines for broader comparison
- Calibrate per-task budgets from multi-model baseline data

### Phase 2

- **LLM judge calibration** — Cohen's Kappa >= 0.61 vs human judgment
- **Statistics** — Bootstrap CI + Cohen's d for model pair comparison
- **Docker sandbox** — Isolated execution for agent eval
- **LLM judge for safety** — `LLMJudgeSafety` scorer for output safety surface

### Future

- **Agent eval** — inspect-swe integration (requires Docker)
- **Multi-sample runs** — pass@k, mean +/- stderr
- **Cost normalization** — tokens x price/token per model
- **Trajectory quality** — backtracking, dead-end detection

---

*Last updated: 2026-04-14*
