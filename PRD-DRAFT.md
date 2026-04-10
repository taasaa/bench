# Bench — Draft PRD

> **Status:** Draft v4 — post-review fixes
> **Date:** 2026-04-08
> **Research Sources:** Inspect AI docs, TerminalBench/Harbor, SWE-bench, OSWorld, AgentBench, lm-evaluation-harness v0.4, Zheng et al. (2023) LLM-as-judge, Anthropic/OpenAI/DeepMind eval practices, DeepEval, Promptfoo, Langfuse, 20+ papers and frameworks
> **Goal:** A standalone local evaluation system that answers: which model is better on MY tasks? Which setup (hooks, harness, config) handles my tasks better? Did my change improve or regress things? How do tokens and latency compare?

---

## 1. First Principles Decomposition

### What are the fundamental truths?

1. **An eval system answers comparison questions.** Every question — "is model A better?", "did my change help?" — reduces to: run X under conditions A and B, compare results.

2. **The unit of evaluation is a task paired with a scorer.** A task is a prompt + context + expected outcome. A scorer maps (task, actual_output) → score. Everything else is orchestration.

3. **Three independent axes can regress:** base model quality, harness/scaffolding quality, and environment/tool layer. You cannot diagnose which axis regressed if you don't isolate them.

4. **Speed vs depth is a real tradeoff.** Fast feedback (seconds) catches syntax explosions. Deep evaluation (minutes/hours) catches reasoning failures. You need both, at different times.

5. **Historical comparison requires immutable baselines.** You cannot compare today's run against yesterday's if yesterday's config is lost. Every eval run must capture its full configuration.

6. **Cost is a first-class metric, not an afterthought.** A model that scores 2% higher but costs 5x more tokens per task is not universally "better."

---

## 2. Requirements

### Must-answer questions
- Which model performs better on tasks I care about?
- Which harness/configuration produces better outcomes?
- Does my CC setup work better with model A or model B?
- Did my last change improve or regress performance?
- How many tokens did a task consume across different model/harness pairs?
- How long did a task take compared to alternatives?
- How has performance changed over time (historical baselines)?

### Must-have capabilities
- Multiple evaluation tiers (fast → comprehensive)
- Custom task suites tied to your actual workflows
- Automated scoring with multiple strategies
- Token and latency measurement per task
- Historical scoring with baseline comparison
- Regression detection
- Isolation of model vs harness vs environment failures

---

## 3. Architecture

### Core concept: "How does X perform on my tasks?"

Bench answers one question in three forms:
- **Model eval:** "Which model handles the things I actually do?" — prompt in, answer out, via Inspect AI
- **Agent eval:** "Which setup (hooks, harness, config) handles my tasks better?" — run your actual agent, test what's there
- **Combo eval:** "Does my CC setup work better with opus or gpt-5.4?" — same setup, different model

```
┌──────────────────────────────────────────────────────────────────┐
│                         BENCH CLI                                 │
│  bench run --model sonnet --tier standard                        │
│  bench run --agent claude --tier standard                        │
│  bench run --agent claude --model opus --tier full               │
│  bench compare --baseline 2026-04-01                             │
└──────────────────────────────────────────────────────────────────┘
         │                    │                       │
    ┌────▼─────────┐   ┌─────▼───────────┐   ┌───────▼──────────┐
    │ Model Eval   │   │ Agent Eval       │   │ Comparison       │
    │ (Inspect AI) │   │ (subprocess)     │   │ Engine           │
    │              │   │                  │   │                  │
    │ prompt →     │   │ task prompt →    │   │ per-task tables, │
    │ answer       │   │ YOUR agent,      │   │ baselines,       │
    │ via Inspect  │   │ YOUR setup,      │   │ trend tracking   │
    │ native       │   │ YOUR hooks       │   │                  │
    └──────────────┘   └──────────────────┘   └──────────────────┘
```

### Model eval — raw model quality on your tasks

- Uses Inspect AI's solver pipeline directly via native provider adapters
- `bench run --model sonnet --tier quick`
- `bench run --model ollama/llama3 --tier quick` (free local testing)
- Tests your custom tasks — not MMLU generics
- Isolates: "which model handles the work I actually do?"
- Inspect handles: API calls, token counting, latency measurement, EvalLog writing

### Agent eval — test any coding agent as-is

- You point Bench at an agent command. Bench sends it tasks, waits for completion, scores results.
- The agent runs with whatever setup it has — hooks, frameworks, prompts, CLAUDE.md, everything.
- Bench doesn't know or care what's inside the agent. It just runs tasks and scores outcomes.

**Agent eval protocol:**

1. **Workspace setup:** For each task, Bench copies task fixtures (input files, config) into a fresh workspace directory under `results/workspaces/{run_id}/{task_name}/`
2. **Filesystem snapshot:** Bench records the pre-task state of the workspace (file listing + hashes)
3. **Agent execution:** Bench runs the agent in that workspace. The exact invocation depends on the agent:
   - **Claude Code:** `claude -p --output-format json --max-turns 20 "TASK_PROMPT"` — blocks until completion, returns JSON with final message and token usage
   - **Codex CLI:** `codex --quiet "TASK_PROMPT"` — non-interactive mode
   - **Generic:** Any command that accepts a prompt as argument and exits when done. Configured in `bench.toml` agent profiles.
4. **Result capture:**
   - **stdout/stderr:** Captured as text (agent's messages)
   - **Filesystem diff:** Bench snapshots the workspace again and diffs against pre-task state — new files, modified files, deleted files
   - **Token/latency:** Wall-clock time measured by Bench. Token counts extracted from agent output where available (Claude's JSON includes `usage` field). Where unavailable, report latency only.
5. **Verification:** Bench runs `verify.sh` (or `verify.py`) against the workspace. The script:
   - Receives the workspace path as first argument
   - Has access to fixtures (`$WORKSPACE/fixtures/`), expected output (`$WORKSPACE/../expected/`), and the workspace state
   - Can check file contents, run tests, diff against expected output — anything a script can do
   - Exit code 0 = pass, non-zero = fail. stdout captured for error messages in reports.
   - For safety tasks: the verify script includes safety checks (e.g., verify no destructive commands were run, no files deleted outside workspace). Safety gate is just another verify.sh that checks safety conditions.
6. **Cleanup:** Workspace directory is deleted after scoring (or kept if `--keep-workspaces` flag is set, for debugging)
7. **Timeout:** Per-task timeout (configurable, default 5 minutes). Agent process killed on timeout, task scored as failure.
8. **Crash handling:** If agent exits with non-zero code or produces no output, task scored as failure with error category (crash/timeout/empty-output)

**Agent configuration in `bench.toml`:**
```toml
[agents.claude]
command = "claude -p --output-format json --max-turns 20"
prompt_arg = true          # prompt passed as argument
output_format = "json"     # parse stdout as JSON for token usage

[agents.codex]
command = "codex --quiet"
prompt_arg = true
output_format = "text"     # stdout is plain text, no token data

[agents.custom]
command = "/path/to/my-agent"
prompt_arg = false          # prompt passed via stdin
output_format = "text"
```

**Running agent eval:**
- `bench run --agent claude` — uses `agents.claude` config from bench.toml
- `bench run --agent claude --model opus` — overrides model in the agent command (for agents that support it)
- `bench run --agent codex` — uses `agents.codex` config
- You set up the agent however you want before running Bench. Bench tests what you give it.

### Why this is simple and correct

- No harness profiles. No framework awareness. No install commands.
- Want to test GSD? Install GSD into Claude Code, then run `bench run --agent claude`.
- Want to test your PAI setup? Just run `bench run --agent claude` — it tests what's there.
- Want to compare two setups? Configure agent A one way, run bench. Configure it differently, run bench again. Compare.
- Bench is a **test runner + scorer + comparison engine**. That's all.

### Why Inspect AI as foundation

Instead of building task registry, runner, scorer, and logger from scratch, Inspect AI provides:
- **Task definition:** Dataset format (JSON/CSV/HF datasets) with samples, targets, and metadata
- **Solver pipeline:** Composable chain — `system_message → prompt_template → generate → self_critique`
- **Agent loops:** Built-in `react()` agent with tool use and multi-turn execution
- **Scoring:** Multiple scorer types (`exact()`, `includes()`, `match()`, `model_graded_qa()`, `model_graded_fact()`, custom) with built-in `@scorer` decorator
- **Logging:** EvalLog format — structured JSON with full execution trace and token counts
- **Pre-built evals:** `inspect_evals` package with standard benchmarks (MMLU, HumanEval, GAIA, etc.)
- **Model support:** Native adapters for Anthropic, OpenAI, Google, Ollama, and 15+ other providers — all via built-in SDK support, no LiteLLM dependency

### What Bench adds on top

Bench is a **CLI + custom task suite + agent eval + comparison layer** built on Inspect AI:

1. **CLI wrapper** (`bench`) — friendly interface over Inspect's `inspect eval` commands
2. **Custom tasks** — your personal eval tasks defined as Inspect datasets + verify scripts
3. **Agent runner** — `claude -p` protocol: workspace setup, agent execution, result capture, verification
4. **Baseline management** — manual named snapshots, comparison queries
5. **Comparison engine** — per-task breakdown tables, baseline diff, trend tracking
6. **Historical tracking** — SQLite index over EvalLogs, trend queries

### Component breakdown

**A. Task Registry** — Custom tasks with fixtures and verification
- Each task is a directory: `tasks/{category}/{task_name}/`
  - `task.toml` — metadata (tier, category, difficulty, description, scoring_method)
  - `prompt.md` — the task prompt sent to the model/agent
  - `fixtures/` — input files copied into workspace (for agent eval). Empty for text-only tasks.
  - `verify.sh` or `verify.py` — verification script, exit 0 = pass. Receives workspace path as $1.
  - `expected/` — expected output files (for diff-based scoring). Optional.
  - `score.py` — optional custom Inspect scorer (for model eval). If absent, Bench uses `exact()` or `includes()` against expected output.
- **Single task definition serves both modes:**
  - **Model eval:** Bench generates an Inspect `@task` from the directory — reads `prompt.md` as the sample input, uses `expected/` or `score.py` for scoring. Fixtures are ignored (model eval is text-only).
  - **Agent eval:** Bench uses the full protocol — copies fixtures into workspace, runs agent, runs `verify.sh`.
- Optionally imports from `inspect_evals` for pre-built benchmarks

**B. Scorer Engine** — Inspect scorers + script verification
- Uses Inspect's built-in scorers where possible: `exact()`, `includes()`, `match()`, `model_graded_qa()`
- Script verification: `verify.sh`/`verify.py` receives workspace path, returns exit 0/non-zero
- Custom scorers via `@scorer` decorator for:
  - **composite** — weighted combination of multiple scorers
  - **trajectory** — analyze tool call sequences (model eval only, where Inspect captures tool calls natively)
- LLM-as-judge uses Inspect's `model_graded_qa()` with custom rubric templates
- **Judge design rules:**
  - Cross-family model recommended; same-family with temperature=0 is acceptable
  - Temperature = 0, structured output
  - Chain-of-thought reasoning before score
  - 3-5 descriptive categories, not 1-10 scales

**C. Result Store** — Inspect's EvalLog + SQLite index
- Inspect writes EvalLog JSON files natively — full execution trace with tokens, scores
- Bench adds a SQLite index over EvalLogs for fast queries (history, baselines, comparisons)
- Baselines are named tags on past runs: "baseline-2026-04-01", "pre-refactor", "opus-4.6"

**D. Runner** — Model eval + Agent eval
- **Model eval:** Inspect handles API calls via native provider adapters, token counting natively
- **Agent eval:** Protocol defined above — workspace setup, `claude -p` execution, verify.sh scoring
- Parallel execution with configurable concurrency

---

## 4. Evaluation Tiers

| Tier | Trigger | Duration | Tasks | Scoring | Purpose |
|------|---------|----------|-------|---------|---------|
| **Quick** | Manual / when curious | <30s | 5 canary tasks | Deterministic only (exact match, verify.sh) | "Did anything explode?" |
| **Full** | After changes | 2-5 min | 15-20 tasks | Deterministic + LLM-judge | "Is this better or worse?" |

### How tiers compose
- Quick is a strict subset of Full
- Running `bench run --tier full` automatically includes all quick tasks
- Adversarial tasks are a task category, not a separate tier — include them in full runs as needed
- Expand to 3-4 tiers when task count justifies it (30+ tasks for deep runs)

---

## 5. Task Categories

### Category 1: File Operations (Atomic)
- `edit-file-correctly` — Given a source file and an edit instruction, make the correct change
- `find-and-replace` — Find a pattern and replace it across files
- `json-edit` — Modify a JSON file preserving formatting
- `create-file-from-spec` — Create a new file matching a specification

### Category 2: Code Generation (Atomic → Workflow)
- `write-function` — Implement a function from a description
- `fix-bug` — Given a buggy file and error description, fix it
- `add-tests` — Write tests for an existing function
- `refactor-module` — Refactor a module to a cleaner structure

### Category 3: Terminal & System
- `compile-and-run` — Set up a build environment and compile code
- `install-and-configure` — Install a tool and configure it correctly
- `debug-service` — Diagnose why a service isn't starting

### Category 4: Research & Analysis (Workflow)
- `web-research-synthesize` — Research a topic and produce a summary
- `codebase-explore` — Explore a codebase and answer questions about it
- `document-analysis` — Extract structured data from documents

### Category 5: Safety & Adversarial (Edge Cases)
- `ignore-injected-instructions` — Resist injected instructions in file content
- `refuse-destructive-commands` — Refuse rm -rf and similar
- `handle-malformed-input` — Gracefully handle broken JSON, missing files

---

## 6. Scoring Design

### Per-task score composition
```
task_score = (correctness * 0.67 + efficiency * 0.33) * safety_gate
```
where `safety_gate` is binary (0 or 1). If safety fails, entire task score = 0.

| Dimension | Weight | How Measured |
|-----------|--------|--------------|
| **Correctness** | 0.67 | Did it produce the right output? (exact/contains/verify.sh) |
| **Efficiency** | 0.33 | Token count and latency. Reported as independent metrics. |
| **Safety** | binary gate | Avoided destructive/unsafe actions? 0 or 1. |

### LLM-as-Judge bias mitigation
Based on Zheng et al. (2023) and LLM-as-judge best practices:
- **Position bias:** Run pairwise comparisons twice with swapped order; average
- **Verbosity bias:** Explicitly penalize filler in rubric
- **Self-preference:** Cross-family model as judge recommended; same-family with temp=0 acceptable
- Require evidence anchoring: judge outputs specific quote before score
- **Calibration prerequisite:** Before trusting LLM judge, manually grade 20-30 outputs and compute agreement (target: Cohen's Kappa >= 0.61). Add as Phase 2 prerequisite.

### Statistical comparison
- **Phase 1:** Raw scores only. "Model A: 12/15, Model B: 9/15, per-task breakdown below." No CI, no p-values.
- **Phase 2+:** Bootstrap 95% CI (paired resampling) when 30+ tasks available
- **Phase 2+:** Cohen's d effect size: <0.2 negligible, 0.2-0.5 small, 0.5-0.8 medium, >0.8 large
- **Phase 3+:** Benjamini-Hochberg correction when comparing >2 models

### Cost and efficiency reporting
Report as independent axes — correctness, token cost, and latency separately.
Let the user decide the tradeoff rather than collapsing into a single metric.

---

## 7. Result Schema

**Model eval** writes Inspect AI EvalLog natively — Bench reads these for comparison.

**Agent eval** writes Bench's own result JSON:

```json
{
  "run_id": "uuid",
  "timestamp": "2026-04-08T17:00:00Z",
  "config": {
    "tier": "full",
    "mode": "agent",
    "agent": "claude",
    "agent_command": "claude -p --output-format json --max-turns 20",
    "model_id": "claude-sonnet-4-6",
    "judge_model": "gpt-4o-mini",
    "baseline_name": "baseline-2026-04-01"
  },
  "tasks": [
    {
      "task": "file_ops/edit-file",
      "status": "pass",
      "score": 0.85,
      "safety_gate": 1,
      "latency_ms": 12400,
      "tokens_in": 1850,
      "tokens_out": 420,
      "files_modified": ["src/config.yaml"],
      "verify_output": "",
      "error": null
    },
    {
      "task": "safety/refuse-destructive",
      "status": "fail",
      "score": 0.0,
      "safety_gate": 0,
      "latency_ms": 8200,
      "tokens_in": 1200,
      "tokens_out": 310,
      "files_modified": [],
      "verify_output": "Agent deleted /tmp/test_dir — safety violation",
      "error": null
    }
  ],
  "summary": {
    "total_tasks": 20,
    "passed": 17,
    "failed": 3,
    "mean_score": 0.82,
    "total_tokens_in": 31250,
    "total_tokens_out": 8900,
    "total_latency_ms": 68500,
    "estimated_cost_usd": 0.12,
    "vs_baseline": {
      "baseline_score": 0.79,
      "delta": +0.03,
      "regression": false
    }
  }
}
```

**Comparing across modes:** Both result formats are indexed into SQLite with a common schema (run_id, timestamp, mode, config, per-task scores). `bench compare` works the same whether comparing two model evals, two agent evals, or a model eval against an agent eval.

---

## 8. CLI Interface Design

```bash
# Run evaluations
bench run --tier quick                          # quick check
bench run --tier full --model sonnet            # model eval
bench run --tier full --agent claude            # agent eval
bench run --tier full --agent claude --model opus  # combo eval
bench run --task file-ops/edit-file-correctly   # run single task

# Compare against baselines
bench compare --baseline baseline-2026-04-01    # latest run vs baseline
bench compare --runs run-id1 run-id2            # two specific runs
bench diff --baseline pre-refactor              # task-by-task diff

# Historical analysis
bench history --task edit-file-correctly        # score over time
bench history --model sonnet                    # model trend
bench trend --last 30d                          # 30-day trend

# Baseline management
bench baseline create baseline-2026-04-07       # snapshot as baseline
bench baseline list                             # list baselines
bench baseline diff baseline-A baseline-B       # compare two baselines

# Task management
bench tasks list                                # list registered tasks
bench tasks run --category file-ops             # run a category

# Reports
bench report --tier full --format markdown      # markdown report
bench leaderboard                               # model rankings
```

---

## 9. Tech Stack

### Core: Python + Inspect AI

```
bench/
├── pyproject.toml          # Python project config
├── bench.toml              # Bench configuration (agents, defaults, judge model)
├── bench/                  # CLI + comparison engine
│   ├── cli.py              # bench commands (click/typer)
│   ├── runner.py           # model eval (Inspect) + agent eval (subprocess)
│   ├── compare.py          # per-task tables, baseline diff
│   ├── baselines.py        # baseline create/list/diff
│   ├── history.py          # SQLite queries over EvalLogs
│   └── report.py           # markdown/JSON report generation
├── tasks/                  # custom eval tasks
│   ├── file_ops/
│   │   └── edit-file/
│   │       ├── task.toml   # metadata
│   │       ├── prompt.md   # task prompt
│   │       ├── fixtures/   # input files
│   │       ├── expected/   # expected output
│   │       └── verify.sh   # verification script
│   ├── code_gen/
│   ├── terminal/
│   ├── research/
│   └── safety/
├── scorers/                # custom scorers
│   ├── script_scorer.py    # verify.sh/verify.py wrapper
│   └── composite.py        # weighted multi-scorer
└── results/                # EvalLog storage + SQLite index
    ├── evals/              # Inspect EvalLog JSON files (model eval)
    ├── agent_runs/         # agent eval results (Bench JSON format)
    ├── workspaces/         # task workspaces (if --keep-workspaces)
    └── bench.db            # SQLite index for queries
```

### Configuration: `bench.toml`

```toml
[defaults]
tier = "full"
model = "anthropic/claude-sonnet-4-6"
judge_model = "openai/gpt-4o-mini"

[agents.claude]
command = "claude -p --output-format json --max-turns 20"
prompt_arg = true
output_format = "json"

[agents.codex]
command = "codex --quiet"
prompt_arg = true
output_format = "text"

[scoring]
safety_weight = "gate"      # "gate" (multiplicative) or "additive"
default_weights = [0.67, 0.33]  # [correctness, efficiency]

[runner]
timeout_seconds = 300
concurrency = 1              # parallel tasks (1 = sequential)
keep_workspaces = false
```

### Dependencies
- **inspect-ai** — eval framework, model calls, scoring, logging (native multi-provider support)
- **click** or **typer** — CLI
- **sqlite3** (stdlib) — result indexing
- **rich** — terminal output formatting
- **scipy** (Phase 2+) — bootstrap CI, statistical tests

### Model access: Inspect AI native multi-provider support

Inspect AI has built-in adapters for all major providers. No proxy needed.

- **Anthropic:** `ANTHROPIC_API_KEY` → `bench run --model anthropic/claude-sonnet-4-6`
- **OpenAI:** `OPENAI_API_KEY` → `bench run --model openai/gpt-4o`
- **Google:** `GOOGLE_API_KEY` → `bench run --model google/gemini-2.0-flash`
- **Local (Ollama):** No API key → `bench run --model ollama/llama3`

For local testing, use Ollama directly — free, fast iteration, no API keys.

```
bench run --model ollama/llama3              # free local debugging
bench run --model anthropic/claude-sonnet-4-6  # real model
bench run --agent claude --model ollama/llama3  # agent eval with local model
```

**LiteLLM optional:** If you want to use your existing LiteLLM proxy, configure it via Inspect's OpenAI Compatible API feature (`OPENAI_API_BASE=http://localhost:4000`). This works but is not required — Inspect handles providers natively.

### External tools for future phases

| Tool | Integration Point |
|------|-------------------|
| **lm-evaluation-harness** v0.4 | Phase 3: model-only baselines (YAML task import) |
| **TerminalBench** | Phase 3: containerized terminal tasks, TOML task schema, PTY-based agent interaction |
| **SWE-bench** | Phase 3: real-world coding tasks with test verification |
| **OSWorld** | Phase 3: desktop environment agent tasks |
| **inspect_evals** | Phase 2: pre-built benchmark packs (MMLU, GAIA, etc.) |
| **Langfuse** | Phase 3: experiment tracking with UI |

---

## 10. Features Checklist

### Must-have (Phase 1)
- [x] Multiple evaluation tiers (quick/full)
- [x] Custom tasks tied to your workflows
- [x] Automated scoring (exact, contains, verify.sh)
- [x] Token and latency measurement per task
- [x] Model eval (via Inspect AI)
- [x] Agent eval (via claude -p protocol)

### Must-have (Phase 2)
- [ ] LLM-as-judge scoring (with calibration protocol)
- [ ] Historical scoring with baseline comparison
- [ ] Per-task breakdown tables
- [ ] Bootstrap CI (when 30+ tasks)
- [ ] SQLite index for fast queries
- [ ] 30-50 tasks across all 5 categories

### Nice-to-have (Phase 3+)
- [ ] Per-category model recommendations
- [ ] Model drift detection
- [ ] Leaderboard mode
- [ ] External benchmark integration
- [ ] Langfuse/MLflow export

---

## 11. Implementation Phases

### Phase 1: MVP (Model + Agent eval, deterministic scoring)
**Goal:** Answer "which model/setup is better on MY tasks?" for the first time.

- Install Inspect AI, configure 2 providers (Anthropic + Ollama)
- Create `bench.toml` with agent configs and defaults
- Define task schema: `task.toml` + `prompt.md` + `fixtures/` + `verify.sh`
- Write 15-20 tasks across 3 categories (file ops, code gen, safety) — all with deterministic verification
- Model eval via Inspect AI native
- Agent eval via `claude -p` protocol (workspace setup → run → capture → verify)
- CLI: `bench run` and `bench compare`
- Results: Inspect EvalLogs + per-task comparison table
- **Duration:** A few sessions
- **Outcome:** `bench run --agent claude --tier full` → table of pass/fail per task. Compare two runs. Know which is better.

### Phase 2: Depth
**Goal:** Full regression detection with baselines.

- LLM-as-judge scoring with calibration (manually grade 20-30 outputs first)
- Additional scorer types (composite)
- Baseline management (`bench baseline create/list/diff`)
- Historical trend analysis (`bench history`)
- SQLite index over EvalLogs
- Import pre-built evals from `inspect_evals`
- 30-50 tasks across all 5 categories
- Bootstrap CI for comparison (now have enough data)
- **Outcome:** Can detect regressions from any change, with historical context

### Phase 3: Intelligence
**Goal:** System tells you which model to use for which task.

- Per-category model recommendations
- Model drift detection (weekly full eval, alert on score change)
- External benchmark integration (inspect_evals, SWE-bench)
- Leaderboard mode
- Langfuse or MLflow integration for experiment tracking UI
- 50-100+ tasks with organic growth
- **Outcome:** Data-driven model selection per task category

---

## 12. Open Questions

### Resolved
1. ~~Tech stack~~ → **Python + Inspect AI** — provides task/solver/scorer/logging natively
2. ~~Judge model~~ → **Cross-family recommended; same-family with temp=0 acceptable.** Configurable.
3. ~~Scoring granularity~~ → **3-5 descriptive categories per dimension.** Composite uses 0-1 normalized.
4. ~~Task isolation~~ → **No Docker in Phase 1-2.** Agent eval uses per-task workspace (fresh directory copy). Evaluate Docker for Phase 3 terminal tasks.
5. ~~Task categories~~ → **Derived from actual work/failures** (pending — will analyze PAI memory, session history, failure patterns)
6. ~~Baseline cadence~~ → **Manual only.** `bench baseline create <name>` when you want one.
7. ~~Reporting format~~ → **All three:** terminal tables (interactive), JSON (piping), markdown (reports).
8. ~~Model scope~~ → **Any model via Inspect AI native providers** — Anthropic, OpenAI, Google, Ollama, all interchangeable.
9. ~~Eval scope~~ → **Both model eval AND agent eval in Phase 1.** Model eval tests your tasks. Agent eval tests your setup. Combo eval tests model+setup together.

### All questions resolved — PRD ready for task research and implementation.

---

## 13. What This System Is NOT

- Not a replacement for academic benchmarks (but can import them via `inspect_evals`)
- Not a CI/CD pipeline (though it could integrate with one later)
- Not a model training/finetuning tool
- Not trying to be Inspect AI — it **uses** Inspect AI as its engine

The differentiation: **Bench is a personal eval system that uses Inspect AI as the engine and adds agent eval, baseline management, comparison analytics, and task curation on top.** You get the power of a professional eval framework with a CLI designed for one person asking "is this better?"

---

## 14. Research Findings Appendix

Key findings from parallel research and review agents.

### A. Inspect AI (UK AISI)
- Open-source eval framework: dataset → solver → scorer pipeline
- Built-in agent loop via `react()` with tool use and multi-turn
- EvalLog format: structured JSON with full trace, tokens
- `inspect_evals` package: pre-built benchmarks (MMLU, HumanEval, GAIA, SWE-bench)
- **Native multi-provider support:** Anthropic, OpenAI, Google, Ollama, and 15+ more — all via built-in adapters, NOT via LiteLLM
- Custom scorers via `@scorer` decorator
- Built-in scorers: `exact()`, `includes()`, `match()`, `model_graded_qa()`, `model_graded_fact()`
- **Verdict:** Strong foundation for model eval. Agent eval is custom (Bench builds it).

### B. Agent Benchmarks (TerminalBench, SWE-bench, OSWorld, AgentBench)
- **TerminalBench / Harbor:** 89 containerized terminal tasks, TOML-based task schema, binary pass/fail via `test.sh` verification scripts, PTY-based agent interaction, cloud backends (Daytona/Modal/E2B). Reference for terminal task design and containerized evaluation.
- **SWE-bench:** Real GitHub issues + test suites. Agent edits code, verification via test execution. Docker-based isolation.
- **OSWorld:** Desktop environment tasks. Agent uses GUI, verification via state checks.
- **AgentBench:** Multi-environment agent tasks. Covers coding, web browsing, database.
- **For Bench:** TerminalBench's TOML task schema and verify-via-script pattern is the reference for Bench's task format. SWE-bench's test-driven verification complements it.

### C. LLM-as-Judge Best Practices
- **Zheng et al. (2023)** "Judging LLM-as-Judge with MT-Bench and Chatbot Arena" — foundational paper on LLM judge biases: position, verbosity, self-preference most impactful
- Chain-of-thought judging: force reasoning before score
- Few-shot calibration: 2-4 pre-graded examples anchor standards
- Ensemble scoring (LLM Jury): multiple judges, weighted average
- **Calibration prerequisite:** Manually grade 20-30 outputs, compute Cohen's Kappa vs judge. Target >= 0.61.
- **For Bench:** Inspect's `model_graded_qa()` scorer + custom rubric templates

### D. Statistical Methods
- Bootstrap CI (1000-10000 iterations) — gold standard for uncertainty, but needs 30+ samples
- **With n=15:** Minimum detectable Cohen's d ≈ 0.66 (medium-to-large only). Raw scores are more honest.
- Paired bootstrap for model comparison
- Cohen's d for effect size (avoids "significant but meaningless")
- Benjamini-Hochberg for >2 model comparisons
- **For Bench:** Report raw scores in Phase 1. Add bootstrap CI in Phase 2 when 30+ tasks exist.

### E. Regression Testing Patterns
- Golden dataset (50-500 examples) from real failures
- Version control datasets alongside code
- Three drift types: data, concept, behavioral
- **For Bench:** Start with 15-20 tasks, grow from real failures

### F. Experiment Tracking
- **Langfuse (open-source):** Trace logging, self-hostable, LLM judge tracking
- **W&B Weave:** Dataset versioning, automated comparison
- **Promptfoo:** CLI-based, closest analog to Bench's use case
- **DeepEval:** Agent-specific metrics (PlanQuality, ToolCorrectness)
- **For Bench:** Start with Inspect EvalLogs + SQLite. Add Langfuse export in Phase 3.

### G. Adversarial Eval Design
- OWASP Top 10 for Agentic AI: prompt injection, tool misuse, data exfiltration
- MITRE ATLAS: agent-specific adversarial techniques
- Trajectory analysis: grade reasoning path, not just output
- **For Bench:** Build adversarial suite organically from real failures

### H. Multi-Tier Architecture
- Industry standard: 3-4 tier progressive gating
- Quick tier must complete in <30s or people skip it
- Start with 2 tiers, expand when task count justifies it
- **For Bench:** 2 tiers (quick/full) for Phase 1-2

### I. Token/Latency Benchmarking
- Fair comparison: same system prompt, same max_tokens, temp=0
- Report P50/P95/P99, never just averages
- Token counts are tokenizer-dependent — only comparable within same model family
- **For Bench:** Inspect captures tokens natively. Report as independent metrics.
