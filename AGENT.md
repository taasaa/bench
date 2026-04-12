# Bench — Agent Context

> This file is the authoritative project reference for AI coding agents working on Bench.
> Read this before touching any code. Update it when the project changes.

## What Bench Is

**Standalone local LLM and AI agent evaluation system.** No PAI or external dependencies. Run eval tasks against models or agents, compare scores in a pivot table.

**Core problem it solves:** You have several local LLMs (gemma, qwen, your own fine-tunes) and want to know which one actually performs better on your real work — not on benchmarks, but on your actual code, your actual bugs, your actual patterns.

## Architecture

```
bench/                      # Python package
├── bench_cli/              # CLI entry points
│   ├── __main__.py         # bench run, bench compare (via __main__)
│   ├── main.py             # Click CLI root + shared config
│   ├── run.py              # bench run implementation
│   └── compare.py          # bench compare pivot-table formatter
├── scorers/                # Custom Inspect AI scorers
│   ├── verify_sh.py         # Runs verify.sh per sample → PASS N/M or FAIL
│   ├── fixtures.py          # load_fixture(), fixtures_dir() helpers
│   ├── composite.py        # (correctness * 0.67 + efficiency * 0.33) * safety_gate
│   ├── efficiency.py       # Score from EvalLog model_usage data
│   ├── safety.py            # Safety gate scorer
│   └── subproc.py           # Subprocess execution scorer
├── tasks/                  # Eval task definitions
│   ├── competence/         # Tier 1: found correct, write tests, format check, surgical fix
│   ├── execution/          # Tier 2: partial impl, negative constraint, intermittent bug, etc.
│   ├── analysis/           # Tier 3: multi-file verify, cascading failure, env mismatch, etc.
│   └── verification/       # Smoke tests (smoke, agent_smoke)
├── templates/              # verify.sh reference scripts
│   ├── byte-identical.sh    # Byte-for-byte output comparison
│   ├── forbidden-string.sh  # Check output doesn't contain forbidden patterns
│   ├── json-parse.sh        # Validate output is valid JSON with expected fields
│   └── line-count-delta.sh  # Check output line count matches expected delta
├── logs/                   # EvalLog .eval files (binary ZIP format)
│   └── *.eval              # One per task run, contains scores + model output
└── tests/                  # pytest test suite
    ├── test_cli.py          # Task discovery, tier config
    ├── test_compare.py       # Pivot table formatting
    ├── test_fixtures.py     # Fixture loading
    ├── test_integration.py  # End-to-end scorer wiring
    ├── test_scorers.py      # Scorer unit tests
    ├── test_verify_patterns.py # verify.sh script tests
    ├── test_verify_sh_scorer.py # verify_sh scorer tests
    ├── test_tier1_tasks.py   # Competence task tests
    └── test_tier2_tasks.py   # Execution task tests
```

## How It Works

### Bench Run

```bash
bench run --tier full --model openai/gemma-4-e2-local
```

1. `_discover_tasks(tier)` scans `tasks/[TIER_DIRS[tier]]/` for `task.py` files
2. `_build_eval_spec()` creates an Inspect `EvalSpec` with task + model + scorer
3. Inspect runs each task's `dataset.json` samples through the solver
4. For each sample, the scorer receives `TaskState` (model output + sample metadata)
5. Results written to `logs/*.eval` (binary ZIP, 8x smaller than JSON)

### Task Format

Each task is a directory with:
- `task.py` — Inspect `@task` decorated function
- `dataset.json` — samples with `input`, `target`, `id` fields
- `verify.sh` — scoring script (for verify_sh tasks)
- `fixtures/` — optional helper files (loaded via `scorers.fixtures`)

```python
# task.py example
from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec
from scorers.verify_sh import verify_sh

@task
def my_task():
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=verify_sh(),
    )
```

### verify.sh Scorer

The `verify_sh` scorer is the workhorse for most tasks. It:

1. Receives model output on stdin
2. Resolves `verify.sh` via **call-stack introspection** (walks frames to find `/tasks/` in path)
3. Runs `verify.sh` with `SAMPLE_ID` in environment
4. Parses `PASS N/M` or `FAIL` from stdout
5. Returns `Score(value=N/M, explanation=stdout)`

**Critical:** `verify.sh` must be **executable** (`chmod +x`).

### Bench Compare

```bash
bench compare
```

Reads all `logs/*.eval` files, builds a `CompareData` matrix:
- Rows: tasks
- Columns: models
- Cells: `PillarScores` (composite, correctness, avg_time, avg_tokens, tokens/sec)

Output format:
```
━━━ COMPOSITE  (correctness×0.67 + efficiency×0.33) × safety ━━━
                         gemma-4-26-local  gemma-4-e2-local     qwen-local   
───────────────────────────────────────────────────────────────────────────────
add_tests                      0.76              0.73              0.82      
...
MEAN                           0.76              0.04              0.82      
```

Also supports `--json` for programmatic access.

## Task Tiers

```python
TIER_DIRS = {
    "quick": ["verification"],   # 2 tasks: smoke, agent_smoke
    "full": ["competence", "execution", "analysis"],  # 16 tasks
}
```

| Tier | Directory | Count | Description |
|------|----------|-------|-------------|
| Competence | `tasks/competence/` | 6 | Foundational skills: QA, test-writing, format compliance, surgical fixes |
| Execution | `tasks/execution/` | 5 | Reliable execution: partial impl, negative constraint, root cause |
| Analysis | `tasks/analysis/` | 5 | Deep analysis: multi-file verify, cascading failure, honey trap |
| Verification | `tasks/verification/` | 2 | Smoke tests |

## The verify_sh Bug (Fixed in 99adecd)

**Problem:** `verify_sh()` looked up `verify.sh` at `os.getcwd()` (project root) instead of the task's directory. All 15 tasks scored 0.0 with "script not found: /Users/rut/dev/bench/verify.sh".

**Fix:** `_find_task_dir()` walks the call stack (via `inspect.getouterframes()`) looking for a frame whose filename contains `/tasks/`. Caches result per scorer instance since all samples in the same task share the same directory.

```python
def _find_task_dir() -> str:
    for frame_info in inspect.getouterframes(...):
        if "/tasks/" in path:
            return os.path.dirname(path)
    return os.getcwd()
```

## Scorer Package

```python
from scorers import verify_sh, fixtures_dir, load_fixture, load_fixture_bytes
from scorers.composite import composite
from scorers.efficiency import efficiency
from scorers.safety import safety
```

| Scorer | Used by | What it measures |
|--------|---------|-----------------|
| `verify_sh()` | Most tasks | Custom scoring via `verify.sh` script |
| `composite()` | add-tests | correctness×0.67 + efficiency×0.33, with safety gate |
| `efficiency()` | Internal | Token count + latency from EvalLog |
| `safety()` | Internal | Safety gate |

## Key Files

| File | Purpose |
|------|---------|
| `bench_cli/run.py` | Task discovery, Inspect eval invocation |
| `bench_cli/compare.py` | Pivot table: load, format, display EvalLogs |
| `bench_cli/main.py` | CLI root + entry point |
| `scorers/verify_sh.py` | Main verify_sh scorer + call-stack task-dir resolution |
| `scorers/fixtures.py` | `fixtures_dir()`, `load_fixture()` helpers |
| `tasks/*/task.py` | Task definitions (one per directory) |
| `tasks/*/dataset.json` | Sample definitions per task |
| `tasks/*/verify.sh` | Per-task scoring logic |
| `templates/*.sh` | Reusable verify.sh patterns |

## CLI Commands

```bash
bench run --help          # Discover and run tasks
bench run --tier full --max-tasks 5  # Cap to 5 tasks
bench run --model openai/gemma-4-e2-local
bench run --agent claude  # Agent eval via inspect-swe

bench compare --help      # Compare eval results
bench compare            # Pivot table
bench compare --json    # JSON output
bench compare --latest 1 # Only most recent log per task
```

## Testing

```bash
python3 -m pytest tests/ -v           # All tests
python3 -m pytest tests/test_cli.py -v # CLI tests
python3 -m pytest tests/test_verify_patterns.py -v # verify.sh pattern tests
```

Current: **181 passing, 1 expected failure** (agent_smoke: inspect_swe not installed).

## Dependencies

```
inspect_ai>=0.3.205
click>=8
rich>=13
```

## Common Gotchas

1. **`verify.sh` must be executable** — scorer checks `os.access(script_path, os.X_OK)`
2. **`SAMPLE_ID` env var** — verify.sh uses it to branch on per-sample patterns. Pass via `env["SAMPLE_ID"]`.
3. **POSIX regex only in verify.sh** — use `grep -E`, not `grep -P`. Use `[[:space:]]` not `\s`.
4. **Inspect EvalLog is binary ZIP** — decode with `zipfile`, not `json.loads()` directly. Contains `header.json`, `samples/`, `_journal/`.
5. **Model routing via LiteLLM** — models route through `OPENAI_BASE_URL=http://smallbox:4000/v1` with `OPENAI_API_KEY`.
6. **Stack introspection for task dir** — `_find_task_dir()` uses `inspect.getouterframes()` to find `/tasks/` in frame paths.

## Milestones

- **M001 (feat/Phase-1-MVP):** Core infrastructure — task format, CLI, scorers, composite scoring, LiteLLM integration
- **M002 (feat/M002-Real-Tasks):** 15 real eval tasks derived from actual work/failures, verify_sh scorer, fixtures infrastructure, organized by cognitive tier

## What's Next

- Re-run eval with configured model after verify_sh fix
- LLM judge (Phase 2, requires Cohen's Kappa >= 0.61 calibration first)
- Bootstrap CI + Cohen's d statistics (Phase 2+, requires 30+ tasks)
- Real task derivation from actual work sessions
