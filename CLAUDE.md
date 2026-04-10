# Bench

## Project Type
Python — Inspect AI framework

## Purpose
Standalone local LLM and AI agent evaluation system. No PAI dependencies.

## Current Focus
PRD v4 (post-review) complete. Ready for Phase 1 implementation.

## Architecture
- **Core:** Python + Inspect AI (task/solver/scorer/logging engine)
- **Model eval:** Inspect AI native — prompt in, answer out, tests your tasks not MMLU
- **Agent eval:** `claude -p --output-format json` protocol — workspace setup, run, capture, verify.sh
- **CLI:** `bench run`, `bench compare`, `bench history`
- **Storage:** Inspect EvalLog JSON + SQLite index
- **Models:** Inspect AI native adapters (Anthropic, OpenAI, Google, Ollama) — no LiteLLM dependency
- **Tiers:** quick (5 tasks, <30s, deterministic) + full (15-20 tasks, all scoring)
- **Scoring:** `(correctness * 0.67 + efficiency * 0.33) * safety_gate`
- **Task format:** Directory with task.toml + prompt.md + fixtures/ + verify.sh

## Key Decisions
- Standalone project — no connection to PAI
- Inspect AI does NOT use LiteLLM — native multi-provider support
- Phase 1 includes BOTH model eval and agent eval
- Agent eval via `claude -p` programmatic interface
- Phase 1: deterministic scoring only, raw score comparison (no CI)
- LLM judge: Phase 2, with calibration prerequisite (Cohen's Kappa >= 0.61)
- Statistics (bootstrap CI, Cohen's d): Phase 2+ when 30+ tasks exist

## Next Steps
- Derive tasks from actual work/failures/sessions (pending)
- Install Inspect AI, configure Anthropic + Ollama
- Write first 15-20 deterministic tasks
- Implement agent eval protocol + `bench run` CLI
