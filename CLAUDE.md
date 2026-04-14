# Bench

## Project Type
Python — Inspect AI + inspect-swe

## Purpose
Standalone local LLM and AI agent evaluation system. No PAI dependencies.

## CLI Usage

```bash
# All commands work via either entry point (no env vars needed — .env auto-loads):
python -m bench_cli run --tier full --model openai/qwen-local
python -m bench_cli run --tier quick --model openai/gemma-4-e2-local
python -m bench_cli run --list-tasks --tier full
python -m bench_cli baseline record --model openai/qwen-local --tier full
python -m bench_cli baseline list
python -m bench_cli compare
pytest                    # run test suite
```

## Model Routing

All models route through a **LiteLLM proxy** at `smallbox:4000`. No direct API calls.

- **Format:** `openai/<model-alias>` — Inspect's OpenAI adapter sends everything to the proxy
- **Credentials:** Stored in project-root `.env` (gitignored). Auto-loaded by `bench_cli/main.py` via `python-dotenv` on import — no manual env exports needed
- **`.env` contents:**
  ```
  OPENAI_BASE_URL=http://smallbox:4000/v1
  OPENAI_API_KEY=<litellm-proxy-token>
  ```
- **Available models** (check with `curl -s http://smallbox:4000/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"`): qwen-local, gemma-4-e2-local, gemma-4-26-local, glm-local, qwen3-coder-plus, qwen3-max, opus, pro, and more
- **Default model:** `openai/default` (maps to whatever LiteLLM configures as default)

## Current Focus
PRD v6 complete (post Inspect AI feature audit). Phase 1 scorers implemented. Phase 1B: baseline data collection.

## Architecture
- **Core:** Python + Inspect AI + inspect-swe
- **Model eval:** Inspect `generate()` solver — prompt in, answer out
- **Agent eval:** `inspect-swe` solvers — `claude_code()`, `codex_cli()`, `gemini_cli()`
- **Agent bridge:** `sandbox_agent_bridge()` proxies CLI agent API calls, captures every token/tool call
- **Sandboxing:** Inspect native — Docker, K8s, local. Phase 1: local. Phase 2+: Docker.
- **CLI:** `bench run`, `bench compare`, `bench baseline record/list`
- **Storage:** Inspect EvalLog binary `.eval` format (8x smaller than JSON) + SQLite index
- **Models:** LiteLLM proxy at `smallbox:4000` — all models via `openai/<alias>` format
- **Tiers:** quick (verification tasks) + full (competence/execution/analysis — 16 tasks)
- **Scoring:** Pillar-based — verify_sh (correctness) + token_ratio + time_ratio + composite_safety per task
- **Task format:** Directory with task.py + dataset.json + verify.sh + fixtures/
- **Viewer:** `inspect view` (localhost:7575) for interactive log inspection
- **Comparison:** `bench compare` — two-tier pillar table with spanning headers, harmonic/geometric mean

## Key Decisions
- Standalone project — no connection to PAI
- inspect-swe handles agent eval — no custom subprocess management
- Inspect captures tokens, latency, tool calls, event transcripts natively for both modes
- Same EvalLog format for model eval and agent eval
- Phase 1: local sandbox (no Docker), deterministic scoring, raw score comparison
- Use `.eval` binary format by default, caching enabled, execution limits configured

## Next Steps
- Phase 1B: baseline data collection + calibration
- Phase 2: LLM judge, statistics, Docker sandboxing
