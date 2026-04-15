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

# Agent eval (requires agent CLI installed: claude, codex, or gemini):
python -m bench_cli run --agent claude --agent-mode local --tier quick --task smoke
python -m bench_cli run --agent claude --agent-mode bare --tier full
python -m bench_cli run --agent codex --agent-mode local --tier full
python -m bench_cli run --agent gemini --agent-mode docker --tier full
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
Phase 1B complete. 16 tasks scored, dual correctness scoring (10 verify_sh + 6 llm_judge), baselines recorded for qwen-local and gemma-4-26-local. Agent eval infrastructure complete: 3 agents x 4 modes. 254 tests passing.

## Architecture
- **Core:** Python + Inspect AI + inspect-swe
- **Model eval:** Inspect `generate()` solver — prompt in, answer out
- **Agent eval:** Agent-agnostic `--agent <name> --agent-mode <mode>` CLI. 3 agents (claude, codex, gemini) x 4 modes (local, bare, docker, harness)
- **Agent config registry:** `bench_cli/agents.py` — per-agent CLI settings, output parsers, Docker solver mapping
- **Agent solvers:** `bench_cli/solvers/local_agent.py` (subprocess) and `docker_agent.py` (inspect-swe wrapper)
- **Agent bridge:** `sandbox_agent_bridge()` proxies CLI agent API calls, captures every token/tool call
- **Sandboxing:** Inspect native — Docker, K8s, local. Phase 1: local. Phase 2+: Docker.
- **CLI:** `bench run`, `bench compare`, `bench baseline record/list`
- **Storage:** Inspect EvalLog binary `.eval` format (8x smaller than JSON) + SQLite index
- **Models:** LiteLLM proxy at `smallbox:4000` — all models via `openai/<alias>` format
- **Tiers:** quick (verification tasks) + full (competence/execution/analysis — 16 tasks)
- **Scoring:** 3 independent scorers per task — verify_sh or llm_judge (correctness) + token_ratio_scorer (efficiency) + time_ratio_scorer (latency)
- **Correctness:** verify_sh for 10 deterministic tasks, llm_judge for 6 open-ended tasks (judge model: `openai/judge` → GLM-5.1)
- **Task format:** Directory with task.py + dataset.json + verify.sh or judge.md + fixtures/
- **Viewer:** `inspect view` (localhost:7575) for interactive log inspection
- **Comparison:** `bench compare` — single pillar table with CORRECT/TOK_RATIO/TIME_RATIO/TOKENS/TIME columns, multi-model side-by-side, geometric mean for ratio aggregates

## Key Decisions
- Standalone project — no connection to PAI
- Agent is a parameter, not the architecture — `AgentConfig` registry makes all agents interchangeable
- inspect-swe handles Docker agent eval — local agents run as subprocesses via `local_agent` solver
- Inspect captures tokens, latency, tool calls, event transcripts natively for both modes
- Same EvalLog format for model eval and agent eval
- Phase 1: local sandbox (no Docker), deterministic scoring, raw score comparison
- Use `.eval` binary format by default, caching enabled, execution limits configured

## Next Steps
- Run agent evals across all combinations (agent x mode) and compare results via `bench compare`
- Phase 1C: more model baselines, calibrate per-task budgets from multi-model data
- Phase 2: LLM judge calibration (Cohen's Kappa), statistics, Docker sandboxing
