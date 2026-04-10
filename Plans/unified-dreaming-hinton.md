# Plan: Update PRD with Inspect AI Feature Audit Findings

## Context

After completing PRD v5 (inspect-swe integration), we audited Inspect AI's full capabilities via 3 parallel research agents. They found ~20 significant features the PRD doesn't mention or underutilizes. The PRD is correct in what it says, but incomplete — it's missing capabilities that would simplify implementation, reduce custom code, and enable future features.

This is NOT a rewrite. It's surgical additions to bring the PRD up to full coverage of what Inspect provides.

## File to modify

`/Users/rut/dev/bench/PRD-DRAFT.md`

## Changes

### 1. Section 3 (Architecture) — Add Inspect capabilities table

**After "What Bench adds on top" subsection, add a new subsection:**

### "Inspect capabilities Bench should leverage"

A table of Inspect features the PRD hasn't explicitly mentioned, organized by phase:

**Phase 1 (use now):**
- `inspect view` — built-in web log viewer on localhost:7575. Use as primary inspection tool. No need to build a viewer.
- Execution limits — `time_limit`, `token_limit`, `message_limit`, `cost_limit`. Critical for agent eval safety. Configure in bench.toml.
- Caching — automatic model response caching with 1-week expiry. Saves cost on development re-runs.
- Tags & metadata — `--tags` and `--metadata` on eval calls for organizing runs.
- `.eval` binary log format — 8x smaller than JSON. Default since v0.3.46.
- `read_eval_log_sample_summaries()` — fast result reads without loading full samples.

**Phase 2 (infrastructure):**
- Dataframe API — `evals_df()`, `samples_df()`, `messages_df()`, `events_df()` return Pandas DataFrames. This IS the comparison engine. No custom log parsing needed.
- DuckDB integration — register DataFrames as DuckDB tables for fast cross-run analysis.
- Hooks system — 15 lifecycle events (`on_run_start/end`, `on_sample_start/end`, `on_model_usage`, etc.) for real-time monitoring and cost tracking.
- Eval Sets (`eval_set()`) — batch multi-task execution with automatic resume. Maps to tier execution.
- Score editing with provenance — `edit_score()` with audit trail for manual corrections.
- Post-hoc scoring — `inspect score` to re-score without re-running.
- Epochs & reducers — variance measurement with `pass_at_k`, `at_least_k`, majority vote.
- Approval system — maps directly to safety_gate. Custom `@approver` can block unsafe tool calls.
- Grouped metrics — `grouped()` for per-category breakdowns natively.

**Future:**
- Batch mode — 50% cost savings via provider batch APIs. For model eval only (not agent).
- `inspect-viz` — interactive score visualizations (heatmaps, radar charts, timelines).
- Human agent (`human_agent()`) — human baselines for comparison.
- Compaction — context management for long agent runs. Built into agent bridge.
- Remote log storage — S3, Azure Blob, GCS for log archival.
- Structured output — `ResponseSchema` for enforcing JSON schemas on model responses.
- Multi-agent system — `handoff()`, `run()`, `as_tool()` for evaluating multi-agent setups.
- Early stopping — adaptive testing that skips clearly passing/failing samples.

### 2. Section 3 (Architecture) — Update "Component breakdown" D. Runner

**Add to Runner subsection:**
- Use `eval_set()` for tier execution (batch run with resume)
- Use execution limits: `time_limit`, `token_limit`, `message_limit` per task
- Use caching: enable for development iterations
- Use tags: auto-tag runs with tier, model, timestamp

### 3. Section 6 (Scoring) — Add Inspect-native scoring capabilities

**After "Cost and efficiency reporting" subsection, add:**

### "Inspect-native scoring tools"

- **Post-hoc scoring:** `inspect score log_file.eval --scorer model_graded_qa` — score evaluations after they run, without re-running. Useful for adding new scorers to existing results.
- **Epochs & reducers:** Run each task N times and reduce with `pass_at_k` (probability of success in k attempts), `at_least_k` (partial credit), or majority vote. Essential for variance measurement in Phase 2+.
- **Grouped metrics:** `grouped(accuracy(), "category")` — automatic per-category breakdowns. No custom grouping code needed.
- **Score editing:** `edit_score()` with provenance tracking. Correct mis-scored samples while preserving audit trail.
- **Approval system for safety gate:** Custom `@approver` can inspect tool calls during execution and block unsafe ones. Maps directly to `safety_gate` — instead of post-hoc checking, reject dangerous tool calls in real-time.

### 4. Section 7 (Result Schema) — Update log format

**Change:** PRD says "EvalLog JSON" in multiple places. Update to clarify Inspect uses binary `.eval` format by default (8x smaller). JSON format available but not default.

**Add to schema section:**
- Log reading API: `read_eval_log()`, `read_eval_log_sample_summaries()`, `read_eval_log_samples()`
- Dataframe API: `evals_df()`, `samples_df()`, `messages_df()`, `events_df()` — these are the primary way to build `bench compare`
- `inspect view` for interactive exploration

### 5. Section 8 (CLI) — Add `bench view` command

**Add after `bench leaderboard`:**
```bash
bench view                                        # launch inspect view (localhost:7575)
bench score --run run-id --scorer model_graded_qa  # post-hoc scoring
```

### 6. Section 9 (Tech Stack) — Add to dependencies, update config

**Dependencies — add:**
- **duckdb** — fast analysis over EvalLog DataFrames (Phase 2)
- **inspect-viz** — interactive result visualizations (Phase 3)

**bench.toml — add execution limits:**
```toml
[runner]
timeout_seconds = 300        # time_limit per sample
max_tokens = 100000          # token_limit per sample
max_messages = 50            # message_limit per sample
cost_limit_usd = 1.00        # cost_limit per sample
cache = true                 # enable model response caching
log_format = "eval"          # binary format (8x smaller than json)
```

### 7. Section 9 (Tech Stack) — Update "External tools" table

**Add to external tools table:**

| Tool | Integration Point |
|------|-------------------|
| **inspect-viz** | Phase 3: interactive score visualizations, heatmaps, radar charts |
| **inspect-scout** | Phase 3: transcript analysis for agent eval debugging |

### 8. Section 9 (Tech Stack) — Update directory structure

**Add `bench view` command and hooks:**
```
bench/
├── bench/
│   ├── ...
│   ├── hooks.py            # Inspect hooks for monitoring/cost tracking
│   └── ...
```

### 9. Section 11 (Implementation Phases) — Enrich Phase 1 & 2

**Phase 1 additions:**
- Use execution limits (`time_limit`, `token_limit`) for agent eval safety
- Enable caching for development iterations
- Use `.eval` binary log format
- Tag runs with tier/model/timestamp via `--tags`

**Phase 2 additions:**
- Hooks system for real-time monitoring and cost tracking
- Dataframe API + DuckDB for comparison engine
- Eval Sets for batch tier execution with resume
- Approval system as safety gate implementation
- Epochs & reducers for variance measurement
- Post-hoc scoring for adding scorers without re-running
- `inspect view` integration (`bench view`)

### 10. Section 14 (Research Appendix) — Add new subsection

**Add 14.J: Inspect AI Feature Audit (2026-04-10)**

Comprehensive audit of Inspect AI capabilities via 3 parallel research agents. Key findings:

- **`inspect view`**: Built-in web log viewer (localhost:7575). Use as primary inspection tool.
- **Dataframe API**: `evals_df()`, `samples_df()`, `messages_df()`, `events_df()` + DuckDB. Primary comparison mechanism.
- **Hooks**: 15 lifecycle events for real-time monitoring, cost tracking, notifications.
- **Eval Sets**: `eval_set()` for batch multi-task execution with resume and retry.
- **Caching**: Automatic model response caching, 1-week default, provider-side caching for Anthropic/OpenAI.
- **Execution Limits**: `time_limit`, `token_limit`, `message_limit`, `cost_limit` per sample.
- **Epochs**: `epochs=N` with reducers: `mean`, `median`, `mode`, `pass_at_k`, `at_least_k`.
- **Approval System**: Custom `@approver` for gating tool calls. Maps to safety_gate.
- **Post-hoc Scoring**: `inspect score` to add scorers without re-running evaluations.
- **Batch Mode**: 50% cost savings via provider batch APIs. Model eval only.
- **`inspect-viz`**: Interactive visualizations (heatmaps, radar charts, timelines).
- **Human Agent**: `human_agent()` for human baselines with session recording.
- **Compaction**: Automatic context management for long agent runs.
- **Structured Output**: `ResponseSchema` for enforcing JSON schemas.
- **Multi-Agent**: `handoff()`, `run()`, `as_tool()` for multi-agent eval.
- **Remote Storage**: S3, Azure Blob, GCS for log archival.
- **Binary Log Format**: `.eval` format is 8x smaller than JSON, default since v0.3.46.
- **Grouped Metrics**: `grouped()` for per-category breakdowns.
- **Score Editing**: `edit_score()` with provenance tracking and audit trail.

Sources: inspect.aisi.org.uk docs (15+ pages), GitHub source (hooks system), PyPI (v0.3.205), inspect_evals GitHub.

### 11. Update header
- Status: "Draft v6 — post Inspect AI feature audit"
- Date: 2026-04-10

## What NOT to change

- Core architecture (Inspect + inspect-swe) — correct
- Scoring formula — correct
- Phase structure (MVP → Depth → Intelligence) — correct, just enrich
- Task format (task.toml + prompt.md + verify.sh) — correct
- CLI commands — correct, just add `bench view` and `bench score`
- All previously fixed issues (LiteLLM, CALM, safety formula, etc.) — leave as-is

## Verification

- Every Inspect feature from 3 research agents accounted for
- No false claims — all features verified against official docs
- Phase assignments make sense (Phase 1 = use now, Phase 2 = infrastructure, Future = nice-to-have)
- PRD doesn't over-promise — future features are noted but not committed
