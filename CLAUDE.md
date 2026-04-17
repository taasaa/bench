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
python -m bench_cli run --concurrency 4 --tier full           # limit parallel tasks
python -m bench_cli run --sequential --tier full               # one task at a time
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
- **LiteLLM proxy config:** `~/dev/litellm/config.yaml` — edit this to add/remove models, set RPM limits (`rpm:` per deployment), or change `enforce_model_rate_limits`. This path is required constantly.

## Current Focus
Phase 1C complete. 32 tasks scored across 4 tiers (competence, execution, analysis, universal). 4-pillar scoring: correctness + token efficiency + latency + cost. minimax m2.7 is the cost benchmark reference. Agent eval: 3 agents x 4 modes. 309 tests passing.

## Architecture
- **Core:** Python + Inspect AI + inspect-swe
- **Model eval:** Inspect `generate()` solver — prompt in, answer out
- **Agent eval:** Agent-agnostic `--agent <name> --agent-mode <mode>` CLI. 3 agents (claude, codex, gemini) x 4 modes (local, bare, docker, harness)
- **Agent config registry:** `bench_cli/agents.py` — per-agent CLI settings, output parsers, Docker solver mapping
- **Agent solvers:** `bench_cli/solvers/local_agent.py` (subprocess) and `docker_agent.py` (inspect-swe wrapper)
- **Agent bridge:** `sandbox_agent_bridge()` proxies CLI agent API calls, captures every token/tool call
- **Sandboxing:** Inspect native — Docker, K8s, local. Phase 1: local. Phase 2+: Docker.
- **CLI:** `bench run`, `bench compare`, `bench baseline record/list`, `bench prices refresh`
- **Storage:** Inspect EvalLog binary `.eval` format (8x smaller than JSON) + SQLite index
- **Models:** LiteLLM proxy at `smallbox:4000` — all models via `openai/<alias>` format
- **Tiers:** quick (verification: smoke + agent_smoke) + full (32 tasks: competence/execution/analysis/universal)
- **Scoring:** 4 independent scorers per task — verify_sh or llm_judge (correctness) + token_ratio_scorer (efficiency) + time_ratio_scorer (latency) + price_ratio_scorer (cost)
- **Correctness:** verify_sh for deterministic tasks, llm_judge for open-ended tasks (judge model: `openai/judge` → GLM-5.1); `includes()`/`exact()` return 'C'/'I' strings handled by compare.py
- **Task format:** Directory with task.py + dataset.json + verify.sh or judge.md + fixtures/
- **Viewer:** `inspect view` (localhost:7575) for interactive log inspection
- **Comparison:** `bench compare` — single pillar table with CORRECT/TOK_RATIO/TIME_RATIO/TOKENS/TIME/COST_RATIO/AVG COST columns, multi-model side-by-side, geometric mean for ratio aggregates

## Cost Scoring (4th Pillar)

**Benchmark reference:** minimax m2.7 (2026-04-17 eval). All 32 tasks have `reference_cost_usd` set to the actual measured average cost per sample in `scorers/task_budgets.py`.

**How it works:**
- `price_ratio_scorer` reads actual usage from `state.output.usage` (input_tokens, output_tokens)
- Resolves model alias → KiloCode price via `MODEL_ALIAS_MAP` in `bench_cli/pricing/model_aliases.py`
- Computes `actual_cost = input_tokens × price_in + output_tokens × price_out`
- Computes `price_ratio = reference_cost_usd / actual_cost_usd`
- Free models (`is_free=True`) return `inf`; KiloCode cache misses return `NaN`

**Price sources:**
- **KiloCode API** (`https://api.kilo.ai/api/openrouter/models`) for OpenRouter model prices — cached at `logs/pricing/kilocode-models.json` (3-day TTL). Refresh with `python -m bench_cli prices refresh`
- **Built-in table** in `bench_cli/pricing/__init__.py` for known local/proxy models (qwen-local, gemma, etc.)
- **`MODEL_ALIAS_MAP`** in `bench_cli/pricing/model_aliases.py`: maps bench LiteLLM alias (`openai/<name>`) → KiloCode model ID (`provider/model-slug`)

**compare.py display:**
- `AVG COST`: arithmetic mean of actual cost per sample, 9 decimal places — no rounding
- `COST_RATIO`: `reference_cost / actual_cost` — ratio >1 means model is cheaper than benchmark, <1 means more expensive. "FREE" for `inf`, "--" for NaN
- When `reference_cost_usd` is `None` (smoke task, no budget): both columns show "--"

**Adding a new model:**
1. Add KiloCode price to `logs/pricing/kilocode-models.json` or built-in table
2. Add alias mapping to `MODEL_ALIAS_MAP` if needed
3. Add `reference_cost_usd` to `scorers/task_budgets.py` for all 32 tasks (copy from minimax column after running new model)

## Key Decisions
- Standalone project — no connection to PAI
- Agent is a parameter, not the architecture — `AgentConfig` registry makes all agents interchangeable
- inspect-swe handles Docker agent eval — local agents run as subprocesses via `local_agent` solver
- Inspect captures tokens, latency, tool calls, event transcripts natively for both modes
- Same EvalLog format for model eval and agent eval
- Phase 1: local sandbox (no Docker), deterministic scoring, raw score comparison
- Use `.eval` binary format by default, caching enabled, execution limits configured

## Next Steps
- Re-run eval to bake new minimax m2.7 cost references into eval logs (4 agents running 32 tasks in background — check back in ~15 min)
- Run agent evals across all combinations (agent x mode) and compare results via `bench compare`
- Phase 2: LLM judge calibration (Cohen's Kappa), statistics, Docker sandboxing
