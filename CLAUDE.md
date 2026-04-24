# Bench

## Project Type
Python — Inspect AI + inspect-swe

## Purpose
Standalone local LLM and AI agent evaluation system. No PAI dependencies.

## Environment

All commands run from the project `.venv`. No system python dependency.
- **Python:** `.venv/bin/python` — activate with `source .venv/bin/activate` or prefix commands with `.venv/bin/`
- **inspect-ai:** 0.3.210 (installed in .venv, no site-packages patches needed)
- **inspect-swe:** 0.2.47 (installed in .venv — provides Docker agent solvers: `claude_code`, `codex_cli`, `gemini_cli`)
- **pytest:** `.venv/bin/pytest` or `pytest` (if venv activated)

## CLI Usage

```bash
# All commands use .venv python (no env vars needed — .env auto-loads):
python -m bench_cli run --tier full --model openai/qwen-local
python -m bench_cli run --tier quick --model openai/gemma-4-e2-local
python -m bench_cli run --list-tasks --tier full
python -m bench_cli run --concurrency 4 --tier full           # limit parallel tasks
python -m bench_cli run --sequential --tier full               # one task at a time

Retry: LiteLLM proxy (`~/dev/litellm/config.yaml`) handles 429/5xx retry with
exponential backoff. rpm limits per model prevent queue saturation.
python -m bench_cli baseline record --model openai/qwen-local --tier full
python -m bench_cli baseline list
python -m bench_cli compare
python -m bench_cli inspect stats --model <alias>       # per-task pillar averages
python -m bench_cli inspect compare --model <alias>       # new vs old delta comparison
python -m bench_cli inspect deep-check --model <alias>    # full QA report
python -m bench_cli results generate    # regenerate all model cards from eval logs
python -m bench_cli prices refresh      # fetch prices from OpenRouter API
python -m bench_cli prices list         # show cached prices for LiteLLM models
python -m bench_cli prices add MODEL --input PRICE --output PRICE  # inject manual price
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
  OPENROUTER_API_KEY=<openrouter-key>
  ```
- **Available models** (check with `curl -s http://smallbox:4000/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"`): qwen-local, gemma-4-e2-local, gemma-4-26-local, glm-local, qwen3-coder-plus, qwen3-max, opus, pro, and more
- **Default model:** `openai/default` (maps to whatever LiteLLM configures as default)
- **LiteLLM proxy config:** `~/dev/litellm/config.yaml` — edit this to add/remove models, set RPM limits (`rpm:` per deployment), or change `enforce_model_rate_limits`. This path is required constantly.

## Current Focus
Multi-dimensional discriminative evaluation: per-cluster profiles, safety gates, Pareto frontier, correlation matrix, harness regression. 4-pillar scoring: correctness + token efficiency + latency + cost. Multi-shot solver with hybrid scoring (verify_sh + llm_judge) for qualitative tasks. Discriminative eval commands: `bench recommend`, `bench compare-profiles`, `bench compare-matrix`, `bench task-correlations`.

## Architecture
- **Core:** Python + Inspect AI + inspect-swe
- **Model eval:** Inspect `generate()` solver — prompt in, answer out
- **Agent eval:** Agent-agnostic `--agent <name> --agent-mode <mode>` CLI. 3 agents (claude, codex, gemini) x 4 modes (local, bare, docker, harness)
- **Agent config registry:** `bench_cli/agents.py` — per-agent CLI settings, output parsers, Docker solver mapping
- **Agent solvers:** `bench_cli/solvers/local_agent.py` (subprocess) and `docker_agent.py` (inspect-swe wrapper)
- **Agent bridge:** `sandbox_agent_bridge()` proxies CLI agent API calls, captures every token/tool call
- **Sandboxing:** Inspect native — Docker, K8s, local.
- **CLI:** `bench run`, `bench compare`, `bench baseline record/list`, `bench prices refresh` — each command is a Python package (`bench_cli/{run,compare,inspect,results}/`) with `cli.py` (Click adapters) + `core.py` (business logic)
- **Storage:** Inspect EvalLog binary `.eval` format (8x smaller than JSON) + SQLite index
- **Models:** LiteLLM proxy at `smallbox:4000` — all models via `openai/<alias>` format
- **Tiers:** quick (verification: smoke + agent_smoke) + full (all tasks: competence + execution + analysis + universal)
- **Scoring:** 4 independent pillars per task — correctness (verify_sh, llm_judge, or hybrid) + token_ratio_scorer (efficiency) + time_ratio_scorer (latency) + price_ratio_scorer (cost)
- **Correctness:** verify_sh for deterministic tasks, llm_judge for open-ended tasks, hybrid_scorer for tasks benefiting from both (verify_sh 0.7 + llm_judge 0.3 weighted); judge model: `openai/judge` → GLM-5.1
- **Task format:** Directory with task.py + dataset.json + verify.sh or judge.md + fixtures/ (optional, for multi-shot tasks)
- **Viewer:** `inspect view` (localhost:7575) for interactive log inspection
- **Comparison:** `bench compare` — single pillar table with CORRECT/TOK_RATIO/TIME_RATIO/TOKENS/TIME/COST_RATIO/AVG COST columns, multi-model side-by-side, geometric mean for ratio aggregates
- **Model cards:** `results/` — auto-generated markdown cards per model (OpenRouter slug naming), with overview, 4-pillar scores, per-task table, LLM summary; auto-updated after each eval run

## Cost Scoring (4th Pillar)

**Benchmark reference:** minimax m2.7 (2026-04-17 eval). All 36 tasks have `reference_cost_usd` in `scorers/task_budgets.py`.

**How it works:**
- `price_ratio_scorer` reads `state.output.usage` tokens, resolves model alias → OpenRouter price via `MODEL_ALIAS_MAP`
- `price_ratio = reference_cost_usd / actual_cost_usd` — >1 means cheaper than benchmark, <1 means more expensive
- Free models return `inf`; cache misses return `NaN` (soft stop, run continues)

**Price sources:**
- **OpenRouter API** — cached at `logs/pricing/openrouter-models.json` (3-day TTL). Refresh with `python -m bench_cli prices refresh`
- **Built-in table** in `bench_cli/pricing/__init__.py` for local/proxy models (qwen-local, gemma, etc.)
- **`MODEL_ALIAS_MAP`** in `bench_cli/pricing/model_aliases.py`: maps bench alias (`openai/<name>`) → OpenRouter model ID (`provider/model-slug`)

**Adding a new model:**
1. Add OpenRouter price to cache with `python -m bench_cli prices add` or built-in table
2. Add alias mapping to `MODEL_ALIAS_MAP` if needed
3. Add `reference_cost_usd` to `scorers/task_budgets.py` for all 36 tasks (copy from minimax column after running new model)

## Key Decisions
- Standalone project — no connection to PAI
- Agent is a parameter, not the architecture — `AgentConfig` registry makes all agents interchangeable
- inspect-swe handles Docker agent eval — local agents run as subprocesses via `local_agent` solver
- Inspect captures tokens, latency, tool calls, event transcripts natively for both modes
- Same EvalLog format for model eval and agent eval
- Use `.eval` binary format by default, caching enabled, execution limits configured

## Next Steps
- Storage rework — separate eval logs from baseline JSONs (logs/ vs baselines/)
- ~~F2, F13, U9, U10 — REDUNDANT, not building~~
- More model baselines for ratio scoring
- LLM judge calibration (Cohen's Kappa ≥ 0.61)
- Agent evals across all combinations (agent x mode)
