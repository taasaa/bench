# Bench — Draft PRD

> **Status:** Draft v6 — post Inspect AI feature audit
> **Date:** 2026-04-10
> **Research Sources:** Inspect AI docs, inspect-swe package, TerminalBench/Harbor, SWE-bench, OSWorld, AgentBench, lm-evaluation-harness v0.4, Zheng et al. (2023) LLM-as-judge, Anthropic/OpenAI/DeepMind eval practices, DeepEval, Promptfoo, Langfuse, 20+ papers and frameworks
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

Both modes use Inspect AI natively. The only difference is the solver: model eval uses Inspect's `generate()` solver, agent eval uses `inspect-swe` solvers (`claude_code()`, `codex_cli()`, `gemini_cli()`).

```
┌──────────────────────────────────────────────────────────────────┐
│                         BENCH CLI                                 │
│  bench run --model sonnet --tier quick                           │
│  bench run --agent claude --tier full                            │
│  bench run --agent claude --model opus --tier full               │
│  bench compare --baseline 2026-04-01                             │
└──────────────────────────────────────────────────────────────────┘
         │                    │                       │
    ┌────▼─────────┐   ┌─────▼───────────┐   ┌───────▼──────────┐
    │ Model Eval   │   │ Agent Eval       │   │ Comparison       │
    │ (Inspect AI  │   │ (inspect-swe)    │   │ Engine           │
    │  generate)   │   │                  │   │                  │
    │              │   │ claude_code()    │   │ per-task tables, │
    │ prompt →     │   │ codex_cli()      │   │ baselines,       │
    │ answer       │   │ gemini_cli()     │   │ trend tracking   │
    └──────────────┘   └──────────────────┘   └──────────────────┘
              │                │                        │
              └───────┬────────┘                        │
                 Inspect AI handles:               Bench builds:
                 • Task execution                  • Custom tasks
                 • Token counting                  • Custom scorers
                 • Latency measurement             • Baseline management
                 • EvalLog writing                 • Comparison engine
                 • Sandbox isolation               • CLI layer
                 • Full event transcripts          • Historical tracking
```

### Model eval — raw model quality on your tasks

- Uses Inspect AI's `generate()` solver via native provider adapters
- `bench run --model sonnet --tier quick`
- `bench run --model ollama/llama3 --tier quick` (free local testing)
- Tests your custom tasks — not MMLU generics
- Isolates: "which model handles the work I actually do?"
- Inspect handles: API calls, token counting, latency measurement, EvalLog writing

### Agent eval — test any coding agent as-is

Inspect AI's `inspect-swe` package provides first-class agent eval solvers:

- **`claude_code()`** — runs Claude Code CLI with your current setup (hooks, CLAUDE.md, everything)
- **`codex_cli()`** — runs Codex CLI
- **`gemini_cli()`** — runs Gemini CLI
- **`mini_swe_agent()`** — lightweight built-in agent for baselines

Usage:
```bash
bench run --agent claude --tier full                    # Claude Code with whatever's installed
bench run --agent claude --model opus --tier full       # same setup, specific model
bench run --agent codex --tier full                     # Codex CLI
bench run --agent gemini --tier full                    # Gemini CLI
```

**How it works:**

1. **`sandbox_agent_bridge()`** — Inspect starts a proxy server that routes the CLI agent's API calls back through Inspect's model provider. This means Inspect captures **every token, every tool call, every API interaction** — not just the final output.

2. **Workspace isolation** — Each task runs in its own sandboxed environment. Inspect supports Docker, Kubernetes, EC2, Modal, and local execution backends. For Phase 1: local (no Docker). For Phase 2+: Docker for full isolation.

3. **Full event transcripts** — Inspect captures the complete execution trace: model generations, tool calls, tool results, refusals, token usage per turn. This enables trajectory analysis without any custom code.

4. **Agent runs with whatever setup it has** — Bench doesn't modify the agent. Claude Code runs with your hooks, your CLAUDE.md, your frameworks. Just like the manual `claude -p` approach, but with Inspect managing the execution and data capture.

5. **Timeout and error handling** — Inspect's `sandbox().exec()` provides built-in timeouts (configurable), output limits (10MB), retry logic, and crash detection.

**Why this is better than our custom protocol:**

| Custom `claude -p` protocol | `inspect-swe` solvers |
|---|---|
| Bench manages subprocesses | Inspect manages everything |
| Token counts from JSON output (partial) | Every token captured via bridge proxy |
| Filesystem diff via manual snapshots | Sandbox isolation with built-in state management |
| Custom error/timeout handling | Built-in timeouts, retries, crash detection |
| Separate result format (Bench JSON) | Same EvalLog format as model eval |
| Agent-specific config in bench.toml | Solver selection via `--agent` flag |
| Trajectory analysis = custom code | Full event transcripts captured natively |

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
- **Agent eval solvers:** `inspect-swe` package with `claude_code()`, `codex_cli()`, `gemini_cli()` — production-ready
- **Agent bridge:** `sandbox_agent_bridge()` proxies CLI agent API calls through Inspect, capturing full token/tool data
- **Scoring:** Multiple scorer types (`exact()`, `includes()`, `match()`, `model_graded_qa()`, `model_graded_fact()`, custom) with built-in `@scorer` decorator
- **Logging:** EvalLog format — binary `.eval` (or `.json`) with full execution trace, tokens, event transcripts
- **Pre-built evals:** `inspect_evals` package with standard benchmarks (MMLU, HumanEval, GAIA, etc.)
- **Sandboxing:** Docker, Kubernetes, EC2, Modal, local — same infrastructure for model and agent eval
- **Model support:** Native adapters for Anthropic, OpenAI, Google, Ollama, and 15+ other providers

### What Bench adds on top

Inspect AI + inspect-swe provides 90% of the infrastructure. Bench adds the personal eval layer:

1. **CLI wrapper** (`bench`) — friendly interface over Inspect's `inspect eval` commands
2. **Custom tasks** — your personal eval tasks defined as Inspect datasets + verify scripts
3. **Custom scorers** — efficiency, safety gate, trajectory quality (things Inspect doesn't have)
4. **Baseline management** — manual named snapshots, comparison queries
5. **Comparison engine** — per-task breakdown tables, baseline diff, trend tracking
6. **Historical tracking** — SQLite index over EvalLogs, trend queries

### Inspect capabilities Bench should leverage

Beyond the core task/solver/scorer/agent-eval system, Inspect provides capabilities the PRD hasn't explicitly mapped:

**Phase 1 (use now):**

| Feature | What | Why |
|---------|------|-----|
| `inspect view` | Web log viewer on localhost:7575 | Primary inspection tool. No custom viewer needed. |
| Execution limits | `time_limit`, `token_limit`, `message_limit`, `cost_limit` | Prevent runaway agent evals. Configure in bench.toml. |
| Caching | Automatic model response caching (1-week expiry) | Save cost on development re-runs. |
| Tags & metadata | `--tags` and `--metadata` on eval calls | Organize runs by tier, model, variant. |
| `.eval` binary format | 8x smaller than JSON (default since v0.3.46) | Efficient log storage. |
| Sample summaries | `read_eval_log_sample_summaries()` | Fast result reads without loading full samples. |

**Phase 2 (infrastructure):**

| Feature | What | Why |
|---------|------|-----|
| Dataframe API | `evals_df()`, `samples_df()`, `messages_df()`, `events_df()` | IS the comparison engine. Returns Pandas DataFrames. No custom log parsing. |
| DuckDB integration | Register DataFrames as DuckDB tables | Fast cross-run analysis for `bench compare`. |
| Hooks system | 15 lifecycle events (`on_run_start/end`, `on_sample_start/end`, `on_model_usage`, ...) | Real-time monitoring, cost tracking, notifications. |
| Eval Sets | `eval_set()` with automatic resume | Batch tier execution with retry and resume. |
| Post-hoc scoring | `inspect score` without re-running | Add new scorers to existing results. |
| Epochs & reducers | `epochs=N` with `pass_at_k`, `at_least_k`, majority vote | Variance measurement. Essential for statistical rigor. |
| Approval system | Custom `@approver` for gating tool calls | Maps to safety_gate — block unsafe tool calls in real-time, not just post-hoc. |
| Score editing | `edit_score()` with provenance tracking | Manual score corrections with audit trail. |
| Grouped metrics | `grouped(accuracy(), "category")` | Per-category breakdowns natively. |

**Future (Phase 3+):**

| Feature | What | Why |
|---------|------|-----|
| Batch mode | 50% cost savings via provider batch APIs | Model eval only (not agent). Significant savings. |
| `inspect-viz` | Interactive heatmaps, radar charts, timelines | Visual exploration of eval results. |
| Human agent | `human_agent()` with session recording | Human baselines for comparison. |
| Compaction | Context management for long agent runs | Built into agent bridge. Prevents context window overflow. |
| Remote log storage | S3, Azure Blob, GCS | Persistent log archival. |
| Structured output | `ResponseSchema` for JSON schemas | Enforce structured model responses. |
| Multi-agent eval | `handoff()`, `run()`, `as_tool()` | Evaluate multi-agent setups. |
| Early stopping | Skip clearly passing/failing samples | Adaptive testing, faster runs. |

### Component breakdown

**A. Task Registry** — Custom tasks with fixtures and verification
- Each task is a directory: `tasks/{category}/{task_name}/`
  - `task.toml` — metadata (tier, category, difficulty, description, scoring_method)
  - `prompt.md` — the task prompt sent to the model/agent
  - `fixtures/` — input files copied into sandbox (for agent eval). Empty for text-only tasks.
  - `verify.sh` or `verify.py` — verification script, exit 0 = pass. Receives workspace path as $1.
  - `expected/` — expected output files (for diff-based scoring). Optional.
  - `score.py` — optional custom Inspect scorer. If absent, Bench uses `exact()` or `includes()`.
- **Single task definition serves both modes:**
  - **Model eval:** Bench generates an Inspect `@task` with `generate()` solver — reads `prompt.md`, uses `expected/` or `score.py` for scoring. Fixtures ignored (text-only).
  - **Agent eval:** Bench generates an Inspect `@task` with `claude_code()` (or other agent) solver — Inspect handles workspace setup, agent execution, result capture. `verify.sh` runs in sandbox after agent completes.
- Optionally imports from `inspect_evals` for pre-built benchmarks

**B. Scorer Engine** — Inspect scorers + Bench custom scorers
- Uses Inspect's built-in scorers where possible: `exact()`, `includes()`, `match()`, `model_graded_qa()`
- Script verification: `verify.sh`/`verify.py` runs inside sandbox, exit 0/non-zero
- Custom scorers via `@scorer` decorator for:
  - **efficiency** — token count and latency scoring, extracted from Inspect's native event data
  - **safety** — binary gate checking for destructive actions, using event transcript analysis
  - **composite** — weighted combination of multiple scorers with `(correctness * 0.67 + efficiency * 0.33) * safety_gate`
  - **trajectory** — analyze tool call sequences from Inspect's native event transcripts
- LLM-as-judge uses Inspect's `model_graded_qa()` with custom rubric templates
- **Judge design rules:**
  - Cross-family model recommended; same-family with temperature=0 is acceptable
  - Temperature = 0, structured output
  - Chain-of-thought reasoning before score
  - 3-5 descriptive categories, not 1-10 scales

**C. Result Store** — Inspect's EvalLog (for both modes) + SQLite index
- Both model eval and agent eval write the same Inspect EvalLog format
- EvalLog contains: full execution trace, token counts per turn, tool calls, scores, event transcripts
- Bench adds a SQLite index over EvalLogs for fast queries (history, baselines, comparisons)
- Baselines are named tags on past runs: "baseline-2026-04-01", "pre-refactor", "opus-4.6"

**D. Runner** — Inspect handles both modes
- **Model eval:** `inspect eval task.py --solver generate --model anthropic/claude-sonnet-4-6`
- **Agent eval:** `inspect eval task.py --solver inspect_swe/claude_code --model anthropic/claude-sonnet-4-6`
- Bench CLI translates friendly commands into Inspect invocations
- Inspect handles: parallel execution, timeouts, sandbox management, data capture
- **Eval Sets:** `eval_set()` for batch tier execution with automatic resume and retry
- **Execution limits:** `time_limit`, `token_limit`, `message_limit`, `cost_limit` per sample
- **Caching:** automatic model response caching for development iterations
- **Tags:** auto-tag runs with tier, model, timestamp via `--tags`

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

### Inspect-native scoring tools

Beyond the custom scorers Bench builds, Inspect provides scoring capabilities the PRD should explicitly leverage:

- **Post-hoc scoring:** `inspect score log_file.eval --scorer model_graded_qa` — score evaluations after they run, without re-running. Useful for adding new scorers to existing results.
- **Epochs & reducers:** Run each task N times and reduce with `pass_at_k` (probability of success in k attempts), `at_least_k` (partial credit), or majority vote. Essential for variance measurement in Phase 2+.
- **Grouped metrics:** `grouped(accuracy(), "category")` — automatic per-category breakdowns. No custom grouping code needed.
- **Score editing:** `edit_score()` with provenance tracking. Correct mis-scored samples while preserving audit trail.
- **Approval system for safety gate:** Custom `@approver` can inspect tool calls during execution and block unsafe ones. Maps directly to `safety_gate` — instead of post-hoc checking, reject dangerous tool calls in real-time.

---

## 7. Result Schema

Both model eval and agent eval write Inspect AI EvalLog natively. Same format. Bench reads these for comparison.

**Log format:** Inspect defaults to binary `.eval` format (zstd compressed, ~8x smaller than JSON) since v0.3.46. JSON format available via `INSPECT_LOG_FORMAT=json`. Bench uses `.eval` by default.

**Log reading API (how Bench accesses results):**
- `read_eval_log()` — read full log or header only
- `read_eval_log_sample_summaries()` — fast summary read without loading full samples
- `read_eval_log_samples()` — stream samples via generator (memory-efficient)
- `inspect view` — interactive web viewer on localhost:7575

**Dataframe API (how Bench builds comparisons):**
- `evals_df("logs")` — one row per eval run
- `samples_df("logs")` — one row per sample
- `messages_df("logs")` — one row per message
- `events_df("logs")` — one row per event (tool calls, model calls, etc.)
- All return Pandas DataFrames. Register with DuckDB for fast SQL queries.

```json
{
  "run_id": "uuid",
  "timestamp": "2026-04-10T17:00:00Z",
  "config": {
    "tier": "full",
    "solver": "inspect_swe/claude_code",
    "model": "anthropic/claude-sonnet-4-6",
    "judge_model": "openai/gpt-4o-mini",
    "baseline_name": "baseline-2026-04-01"
  },
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

Inspect EvalLog also contains per-sample details: full event transcripts (tool calls, model outputs, token usage per turn), which Bench's custom scorers and comparison engine consume.

---

## 8. CLI Interface Design

```bash
# Run evaluations
bench run --tier quick                          # quick check (default model)
bench run --tier full --model sonnet            # model eval
bench run --tier full --agent claude            # agent eval (Claude Code)
bench run --tier full --agent claude --model opus  # combo eval
bench run --tier full --agent codex             # agent eval (Codex)
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

# Inspection
bench view                                      # launch inspect view (localhost:7575)
bench score --run run-id --scorer model_graded_qa  # post-hoc scoring
```

---

## 9. Tech Stack

### Core: Python + Inspect AI + inspect-swe

```
bench/
├── pyproject.toml          # Python project config
├── bench.toml              # Bench configuration (defaults, judge model, scoring)
├── bench/                  # CLI + comparison engine
│   ├── cli.py              # bench commands (click/typer)
│   ├── runner.py           # translates bench CLI → inspect eval commands
│   ├── compare.py          # per-task tables, baseline diff
│   ├── baselines.py        # baseline create/list/diff
│   ├── history.py          # SQLite queries over EvalLogs
│   ├── hooks.py            # Inspect hooks for monitoring/cost tracking (Phase 2)
│   └── report.py           # markdown/JSON report generation
├── tasks/                  # custom eval tasks
│   ├── file_ops/
│   │   └── edit-file/
│   │       ├── task.toml   # metadata
│   │       ├── prompt.md   # task prompt
│   │       ├── fixtures/   # input files (for agent eval)
│   │       ├── expected/   # expected output
│   │       └── verify.sh   # verification script
│   ├── code_gen/
│   ├── terminal/
│   ├── research/
│   └── safety/
├── scorers/                # custom Bench scorers
│   ├── efficiency.py       # token/latency scoring from EvalLog data
│   ├── safety.py           # safety gate scorer
│   └── composite.py        # weighted multi-scorer
└── results/                # Inspect EvalLog storage + SQLite index
    ├── evals/              # Inspect EvalLog files (.eval binary format, both modes)
    └── bench.db            # SQLite index for queries
```

### Dependencies
- **inspect-ai** — eval framework, model calls, scoring, logging, sandboxing
- **inspect-swe** — agent eval solvers (`claude_code()`, `codex_cli()`, `gemini_cli()`, `sandbox_agent_bridge()`)
- **click** or **typer** — CLI
- **sqlite3** (stdlib) — result indexing
- **rich** — terminal output formatting
- **duckdb** (Phase 2) — fast analysis over EvalLog DataFrames
- **scipy** (Phase 2+) — bootstrap CI, statistical tests
- **inspect-viz** (Phase 3) — interactive result visualizations

### Configuration: `bench.toml`

```toml
[defaults]
tier = "full"
model = "anthropic/claude-sonnet-4-6"
judge_model = "openai/gpt-4o-mini"

[scoring]
safety_weight = "gate"      # "gate" (multiplicative) or "additive"
default_weights = [0.67, 0.33]  # [correctness, efficiency]

[runner]
timeout_seconds = 300
max_tokens = 100000          # token_limit per sample (prevents runaway agent evals)
max_messages = 50            # message_limit per sample
cost_limit_usd = 1.00        # cost_limit per sample
concurrency = 1              # parallel tasks (1 = sequential)
sandbox = "local"            # "local" (Phase 1) or "docker" (Phase 2+)
cache = true                 # enable model response caching (saves cost on re-runs)
log_format = "eval"          # binary format (8x smaller than json)
```

Agent selection is via CLI flags (`--agent claude`, `--agent codex`), not config — Inspect's `inspect-swe` solvers handle the invocation.

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
| **inspect-viz** | Phase 3: interactive score visualizations, heatmaps, radar charts |
| **inspect-scout** | Phase 3: transcript analysis for agent eval debugging |
| **Langfuse** | Phase 3: experiment tracking with UI |

---

## 10. Features Checklist

### Must-have (Phase 1)
- [x] Multiple evaluation tiers (quick/full)
- [x] Custom tasks tied to your workflows
- [x] Automated scoring (exact, contains, verify.sh)
- [x] Token and latency measurement per task (native via Inspect)
- [x] Model eval (via Inspect AI generate solver)
- [x] Agent eval (via inspect-swe solvers)

### Must-have (Phase 2)
- [ ] LLM-as-judge scoring (with calibration protocol)
- [ ] Historical scoring with baseline comparison
- [ ] Per-task breakdown tables
- [ ] Bootstrap CI (when 30+ tasks)
- [ ] SQLite index for fast queries
- [ ] 30-50 tasks across all 5 categories
- [ ] Docker sandboxing for agent eval

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

- Install Inspect AI + inspect-swe, configure 2 providers (Anthropic + Ollama)
- Create `bench.toml` with defaults (including execution limits, caching, binary log format)
- Define task schema: `task.toml` + `prompt.md` + `fixtures/` + `verify.sh`
- Write 15-20 tasks across 3 categories (file ops, code gen, safety) — all with deterministic verification
- Model eval via Inspect `generate()` solver
- Agent eval via `inspect-swe` `claude_code()` solver (local sandbox, no Docker)
- Custom scorers: efficiency (from EvalLog token data), safety gate
- CLI: `bench run` and `bench compare`
- Results: Inspect EvalLogs (binary `.eval` format) + per-task comparison table
- **Execution limits:** `time_limit=300`, `token_limit=100000` per sample for agent eval safety
- **Caching:** enable for development iterations (saves cost on re-runs)
- **Tags:** auto-tag runs with tier, model, timestamp
- **`inspect view`** for interactive log inspection
- **Duration:** A few sessions
- **Outcome:** `bench run --agent claude --tier full` → table of pass/fail per task. Compare two runs. Know which is better.

### Phase 2: Depth
**Goal:** Full regression detection with baselines.

- Docker sandboxing for agent eval (via Inspect's built-in sandbox system)
- LLM-as-judge scoring with calibration (manually grade 20-30 outputs first)
- Additional scorer types (composite, trajectory from event transcripts)
- Baseline management (`bench baseline create/list/diff`)
- Historical trend analysis (`bench history`)
- SQLite index over EvalLogs
- Import pre-built evals from `inspect_evals`
- 30-50 tasks across all 5 categories
- Bootstrap CI for comparison (now have enough data)
- **Hooks system:** real-time monitoring, cost tracking, notifications via Inspect's lifecycle events
- **Dataframe API + DuckDB:** comparison engine using `evals_df()`/`samples_df()` with SQL queries
- **Eval Sets:** batch tier execution with `eval_set()` — automatic resume and retry
- **Approval system:** safety gate via custom `@approver` — block unsafe tool calls in real-time
- **Epochs & reducers:** variance measurement with `pass_at_k`, `at_least_k`
- **Post-hoc scoring:** add scorers to existing results without re-running
- **`bench view`:** launch `inspect view` for interactive exploration
- **Outcome:** Can detect regressions from any change, with historical context

### Phase 3: Intelligence
**Goal:** System tells you which model to use for which task.

- Per-category model recommendations
- Model drift detection (weekly full eval, alert on score change)
- External benchmark integration (inspect_evals, SWE-bench, TerminalBench)
- Leaderboard mode
- Langfuse or MLflow integration for experiment tracking UI
- `inspect-viz` for interactive score visualizations (heatmaps, radar charts, timelines)
- `inspect-scout` for transcript analysis and agent eval debugging
- Batch mode for 50% cost savings on model eval runs
- Human baselines via `human_agent()` with session recording
- 50-100+ tasks with organic growth
- **Outcome:** Data-driven model selection per task category

---

## 12. Open Questions

### Resolved
1. ~~Tech stack~~ → **Python + Inspect AI + inspect-swe** — provides task/solver/scorer/logging/agent-eval natively
2. ~~Judge model~~ → **Cross-family recommended; same-family with temp=0 acceptable.** Configurable.
3. ~~Scoring granularity~~ → **3-5 descriptive categories per dimension.** Composite uses 0-1 normalized.
4. ~~Task isolation~~ → **Local sandbox in Phase 1.** Docker via Inspect's built-in sandbox system in Phase 2+.
5. ~~Task categories~~ → **Derived from actual work/failures** (pending — will analyze PAI memory, session history, failure patterns)
6. ~~Baseline cadence~~ → **Manual only.** `bench baseline create <name>` when you want one.
7. ~~Reporting format~~ → **All three:** terminal tables (interactive), JSON (piping), markdown (reports).
8. ~~Model scope~~ → **Any model via Inspect AI native providers** — Anthropic, OpenAI, Google, Ollama, all interchangeable.
9. ~~Eval scope~~ → **Both model eval AND agent eval in Phase 1.** Model eval tests your tasks. Agent eval tests your setup. Combo eval tests model+setup together.
10. ~~Agent eval protocol~~ → **`inspect-swe` package** — first-class solvers for Claude Code, Codex, Gemini. No custom subprocess management needed.

### All questions resolved — PRD ready for task research and implementation.

### Next Steps (from Inspect AI feature audit)
These features don't change the PRD's architecture but represent future improvements to track:

1. **Remote log storage** (S3/Azure/GCS) — when logs outgrow local disk, Inspect supports fsspec backends natively
2. **Structured output** (`ResponseSchema`) — enforce JSON schemas on model eval responses for cleaner scoring
3. **Multi-agent evaluation** (`handoff()`, `run()`, `as_tool()`) — evaluate multi-agent setups when Bench's user starts using them
4. **Early stopping** — skip clearly passing/failing samples for faster runs on large task suites
5. **Score editing workflow** — formal process for manual corrections with provenance audit trail
6. **Inspect AI version pinning** — near-daily releases (v0.3.x), pin version in requirements.txt
7. **`inspect view` bundle** — package logs as standalone HTML for sharing results

---

## 13. What This System Is NOT

- Not a replacement for academic benchmarks (but can import them via `inspect_evals`)
- Not a CI/CD pipeline (though it could integrate with one later)
- Not a model training/finetuning tool
- Not trying to be Inspect AI — it **uses** Inspect AI as its engine

The differentiation: **Bench is a personal eval layer on top of Inspect AI.** Inspect + inspect-swe handles all the infrastructure (task execution, agent running, token capture, sandboxing, logging). Bench adds custom tasks, custom scorers, baseline management, comparison analytics, and a CLI designed for one person asking "is this better?"

---

## 14. Research Findings Appendix

Key findings from parallel research and review agents.

### A. Inspect AI (UK AISI)
- Open-source eval framework: dataset → solver → scorer pipeline
- **Agent eval via `inspect-swe`:** Production-ready solvers for `claude_code()`, `codex_cli()`, `gemini_cli()`, `mini_swe_agent()`
- **`sandbox_agent_bridge()`:** Proxies CLI agent API calls through Inspect's model provider — captures every token, every tool call
- **`agent_bridge()`:** For Python-based agents (monkey-patches OpenAI/Anthropic/Google SDKs)
- **Sandboxing:** Docker, Kubernetes, EC2, Modal, Daytona, Proxmox, Podman, Vagrant — per-sample isolated environments
- **Subprocess management:** `sandbox().exec()` with async execution, timeouts, retries, output limits (10MB), environment variable injection
- **Event transcripts:** Full execution trace — model generations, tool calls, results, refusals, token usage per turn
- EvalLog format: binary `.eval` (zstd compressed, 8x smaller than JSON, default since v0.3.46) or `.json` (text). Full trace, tokens, scores.
- `inspect_evals` package: pre-built benchmarks (MMLU, HumanEval, GAIA, SWE-bench)
- **Native multi-provider support:** Anthropic, OpenAI, Google, Ollama, and 15+ more — all via built-in adapters
- Custom scorers via `@scorer` decorator
- Built-in scorers: `exact()`, `includes()`, `match()`, `model_graded_qa()`, `model_graded_fact()`
- **Verdict:** Inspect AI + inspect-swe provides ~90% of Bench's infrastructure natively. Bench adds tasks, custom scorers, baselines, comparison, CLI.

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
- **For Bench:** Inspect captures tokens natively for both model and agent eval. Report as independent metrics.

### J. Inspect AI Feature Audit (2026-04-10)

Comprehensive audit of Inspect AI capabilities via 3 parallel research agents. Verified against official docs (inspect.aisi.org.uk, 15+ pages), GitHub source (hooks system), PyPI (v0.3.205), and inspect_evals GitHub.

**Features the PRD wasn't explicitly leveraging:**

| Feature | Description | Phase |
|---------|-------------|-------|
| `inspect view` | Web log viewer on localhost:7575. VS Code extension available. | Phase 1 |
| Execution limits | `time_limit`, `token_limit`, `message_limit`, `cost_limit` per sample | Phase 1 |
| Caching | Automatic model response caching (1-week default). Provider-side for Anthropic/OpenAI. | Phase 1 |
| `.eval` binary format | 8x smaller than JSON. Default since v0.3.46. zstd compressed. | Phase 1 |
| Tags & metadata | `--tags` and `--metadata` for organizing runs. Post-hoc editing with provenance. | Phase 1 |
| Sample summaries | `read_eval_log_sample_summaries()` for fast reads without full sample load | Phase 1 |
| Dataframe API | `evals_df()`, `samples_df()`, `messages_df()`, `events_df()` → Pandas DataFrames | Phase 2 |
| DuckDB integration | Register DataFrames as DuckDB tables for fast SQL queries across runs | Phase 2 |
| Hooks system | 15 lifecycle events (`on_run_start/end`, `on_sample_start/end`, `on_model_usage`, ...) | Phase 2 |
| Eval Sets | `eval_set()` for batch multi-task execution with automatic resume and retry | Phase 2 |
| Post-hoc scoring | `inspect score` to add scorers without re-running evaluations | Phase 2 |
| Epochs & reducers | `epochs=N` with `pass_at_k`, `at_least_k`, majority vote, custom reducers | Phase 2 |
| Approval system | Custom `@approver` for gating tool calls in real-time. Maps to safety_gate. | Phase 2 |
| Score editing | `edit_score()` with provenance tracking and audit trail | Phase 2 |
| Grouped metrics | `grouped(accuracy(), "category")` for per-category breakdowns | Phase 2 |
| Batch mode | 50% cost savings via provider batch APIs. Model eval only. | Phase 3 |
| `inspect-viz` | Interactive visualizations: heatmaps, radar charts, timelines. Jupyter/Quarto. | Phase 3 |
| Human agent | `human_agent()` for human baselines with session recording | Phase 3 |
| Compaction | Context management for long agent runs. Built into agent bridge. | Phase 3 |
| Remote storage | S3, Azure Blob, GCS for log archival via fsspec | Future |
| Structured output | `ResponseSchema` for enforcing JSON schemas on model responses | Future |
| Multi-agent eval | `handoff()`, `run()`, `as_tool()` for evaluating multi-agent setups | Future |
| Early stopping | Adaptive testing that skips clearly passing/failing samples | Future |
| `inspect-scout` | Transcript analysis tool for agent eval debugging | Phase 3 |

**Key implication:** Inspect provides significantly more infrastructure than the PRD assumed. Bench's custom code is limited to: task definitions, custom scorers (efficiency, safety, trajectory), baseline management, comparison engine (using Dataframe API), and CLI. Everything else — viewer, caching, execution limits, monitoring, batch execution — comes free.
