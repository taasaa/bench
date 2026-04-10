# Bench

## Project Type
Python — Inspect AI + inspect-swe

## Purpose
Standalone local LLM and AI agent evaluation system. No PAI dependencies.

## Current Focus
PRD v6 complete (post Inspect AI feature audit). Ready for Phase 1 implementation.

## Architecture
- **Core:** Python + Inspect AI + inspect-swe
- **Model eval:** Inspect `generate()` solver — prompt in, answer out
- **Agent eval:** `inspect-swe` solvers — `claude_code()`, `codex_cli()`, `gemini_cli()`
- **Agent bridge:** `sandbox_agent_bridge()` proxies CLI agent API calls, captures every token/tool call
- **Sandboxing:** Inspect native — Docker, K8s, local. Phase 1: local. Phase 2+: Docker.
- **CLI:** `bench run`, `bench compare`, `bench history`, `bench view`
- **Storage:** Inspect EvalLog binary `.eval` format (8x smaller than JSON) + SQLite index
- **Models:** Inspect AI native adapters (Anthropic, OpenAI, Google, Ollama)
- **Tiers:** quick (5 tasks, <30s, deterministic) + full (15-20 tasks, all scoring)
- **Scoring:** `(correctness * 0.67 + efficiency * 0.33) * safety_gate`
- **Task format:** Directory with task.toml + prompt.md + fixtures/ + verify.sh
- **Viewer:** `inspect view` (localhost:7575) for interactive log inspection
- **Comparison:** Dataframe API (`evals_df()`, `samples_df()`) + DuckDB
- **Monitoring:** Inspect hooks system (15 lifecycle events)
- **Execution limits:** `time_limit`, `token_limit`, `message_limit`, `cost_limit` per sample

## Key Decisions
- Standalone project — no connection to PAI
- inspect-swe handles agent eval — no custom subprocess management
- Inspect captures tokens, latency, tool calls, event transcripts natively for both modes
- Same EvalLog format for model eval and agent eval
- Phase 1: local sandbox (no Docker), deterministic scoring, raw score comparison
- LLM judge: Phase 2, with calibration prerequisite (Cohen's Kappa >= 0.61)
- Statistics (bootstrap CI, Cohen's d): Phase 2+ when 30+ tasks exist
- Approval system maps to safety_gate: block unsafe tool calls in real-time (Phase 2)
- Use `.eval` binary format by default, caching enabled, execution limits configured

## Next Steps
- Derive tasks from actual work/failures/sessions (pending)
- Install Inspect AI + inspect-swe, configure Anthropic + Ollama
- Write first 15-20 deterministic tasks
- Implement custom scorers + `bench run` CLI
