# Bench — Agent Context

> This file is the authoritative project reference for AI coding agents working on Bench.
> Read this before touching any code. Update it when the project changes.

## What Bench Is

**Standalone local LLM and AI agent evaluation system.** No PAI or external dependencies. Run eval tasks against models or agents, compare scores across a 4-pillar rubric (correctness, token efficiency, latency, cost).

**Core problem it solves:** You have several local LLMs and want to know which one actually performs better on your real work — not on benchmarks, but on your actual code, bugs, and patterns.

## Architecture

```
bench/                      # Project root
├── bench_cli/             # CLI entry points
│   ├── main.py           # Click CLI root
│   ├── run/               # bench run (package: cli.py + core.py)
│   ├── compare/           # bench compare pivot table
│   ├── inspect/           # bench inspect stats/compare/deep-check
│   ├── results/           # bench results generate (model cards)
│   ├── prices.py          # bench prices refresh/list/add
│   ├── discriminative/     # bench recommend, compare-profiles, compare-matrix
│   ├── agents.py          # AgentConfig registry (claude, codex, gemini)
│   ├── solvers/           # Agent solvers: local_agent.py, docker_agent.py
│   └── pricing/           # OpenRouter cache, LiteLLM config parser
├── scorers/               # Custom Inspect AI scorers
│   ├── verify_sh.py       # Runs verify.sh per sample → PASS N/M or FAIL
│   ├── llm_judge.py       # LLM judge with per-task rubric from judge.md
│   ├── hybrid.py          # Weighted combo: verify_sh (0.7) + llm_judge (0.3)
│   ├── token_ratio.py     # Token efficiency pillar
│   ├── time_ratio.py      # Latency pillar
│   ├── price_ratio.py     # Cost pillar
│   ├── task_budgets.py    # Reference costs per task
│   └── fixtures.py        # load_fixture(), fixtures_dir() helpers
├── tasks/                 # Eval task definitions
│   ├── verification/      # Smoke tests (smoke, agent_smoke)
│   ├── competence/       # Foundational skills
│   ├── execution/         # Reliable execution under constraints
│   ├── analysis/          # Deep reasoning and diagnosis
│   └── universal/         # Agent failure modes
└── tests/                 # pytest suite
```

## CLI Commands

```bash
# Run eval
bench run --tier full --model openai/qwen-local
bench run --tier quick --model openai/qwen-local
bench run --concurrency 4 --tier full
bench run --sequential --tier full

# Compare
bench compare

# Discriminative profiles
bench recommend --model openai/qwen-local
bench compare-profiles openai/qwen-local openai/gemma-4-26-local
bench compare-matrix openai/qwen-local openai/nvidia-mistral-small4
bench task-correlations --model openai/qwen-local

# Model cards and pricing
bench results generate
bench prices refresh
bench prices list
bench prices add MODEL --input 0.0001 --output 0.0003

# Agent eval
bench run --agent claude --agent-mode local --tier full
bench run --agent claude --agent-mode bare --tier full
bench run --agent codex --agent-mode docker --tier full
```

## How It Works

### Bench Run

1. `_discover_tasks(tier)` scans `tasks/[tier]/` for `task.py` files
2. `_build_eval_spec()` creates an Inspect `EvalSpec` with task + model + scorer
3. Inspect runs each task's `dataset.json` samples through the solver
4. For each sample, the scorer receives `TaskState` (model output + sample metadata)
5. Results written to `logs/*.eval` (binary ZIP)

### Task Format

Each task is a directory with:
- `task.py` — Inspect `@task` decorated function
- `dataset.json` — samples with `input`, `target`, `id` fields
- `verify.sh` — scoring script (for verify_sh tasks)
- `judge.md` — rubric for llm_judge tasks
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

## The Four Scoring Pillars

Every task produces four independent scores. No composite formula.

| Pillar | Scorer | What it measures |
|--------|--------|-----------------|
| **Correctness** | `verify_sh`, `llm_judge`, or `hybrid` | Did the model produce the right answer? |
| **Token Efficiency** | `token_ratio_scorer` | `reference_tokens / actual_tokens` — higher = fewer tokens |
| **Latency** | `time_ratio_scorer` | `reference_seconds / actual_seconds` — higher = faster |
| **Cost** | `price_ratio_scorer` | `reference_cost / actual_cost` — higher = cheaper |

### Correctness Scorers

| Scorer | When used |
|--------|-----------|
| `verify_sh` | Deterministic tasks with scriptable checks |
| `llm_judge` | Qualitative tasks requiring reasoning evaluation |
| `hybrid_scorer` | Tasks benefiting from both (verify_sh 0.7 + llm_judge 0.3) |

**Judge scale:** Discrete 5-point (0, 2.5, 5, 7.5, 10), normalized to 0-1. Reduces judge variance from ±0.15 on continuous scales.

## Agent Eval

**Agent config registry:** `bench_cli/agents.py` — `AgentConfig` dataclass per agent.

**4 agent modes:**
- `local` — full harness on host
- `bare` — no hooks/CLAUDE.md
- `docker` — pristine container via inspect-swe
- `harness` — Docker + injected CLAUDE.md

**3 agents:** claude, codex, gemini.

**Local solver:** `bench_cli/solvers/local_agent.py` — async subprocess, agent-specific output parsing.
**Docker solver:** `bench_cli/solvers/docker_agent.py` — wraps inspect-swe solvers with optional harness injection.

**--cc-model flag:** Passes CCR-style model names to Claude Code's `--model` flag. Only for local/bare modes.

## Key Files

| File | Purpose |
|------|---------|
| `bench_cli/run/core.py` | Task discovery, Inspect eval invocation |
| `bench_cli/compare/core.py` | Pivot table: load, format, display EvalLogs |
| `bench_cli/discriminative/pipeline.py` | Discriminative eval: diagnostics → profiles → gates |
| `bench_cli/discriminative/profiles.py` | Per-cluster scores, strengths/weaknesses |
| `scorers/verify_sh.py` | verify_sh scorer + call-stack task-dir resolution |
| `scorers/llm_judge.py` | LLM judge scorer + rubric caching |
| `scorers/hybrid.py` | hybrid_scorer (verify_sh + llm_judge weighted) |
| `scorers/fixtures.py` | `fixtures_dir()`, `load_fixture()` helpers |
| `tasks/*/task.py` | Task definitions |
| `tasks/*/dataset.json` | Sample definitions per task |
| `tasks/*/verify.sh` | Per-task scoring logic (verify_sh tasks) |
| `tasks/*/judge.md` | Per-task rubric (llm_judge tasks) |

## Common Gotchas

1. **`verify.sh` must be executable** — scorer checks `os.access(script_path, os.X_OK)`
2. **`SAMPLE_ID` env var** — verify.sh uses it to branch on per-sample patterns. Pass via `env["SAMPLE_ID"]`.
3. **POSIX regex only in verify.sh** — use `grep -E`, not `grep -P`. Use `[[:space:]]` not `\s`.
4. **Inspect EvalLog is binary ZIP** — decode with `zipfile`, not `json.loads()`. Contains `header.json`, `samples/`, `_journal/`.
5. **Model routing via LiteLLM** — models route through `OPENAI_BASE_URL=http://smallbox:4000/v1`.
6. **Stack introspection for task dir** — `_find_task_dir()` uses `inspect.getouterframes()` to find `/tasks/` in frame paths.
7. **`sample.model_usage` is a dict** keyed by model name, not an object — use `isinstance(x, dict)` before accessing.
8. **`bench_cli/run/` is a package** — `from bench_cli.run.core import _discover_tasks`. Not `from bench_cli.run import ...`
9. **`bench_cli/scorers/` does not exist** — scorers are in `scorers/` at project root, imported as `from scorers import ...`
