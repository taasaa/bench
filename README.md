# Bench

Standalone local LLM and AI agent evaluation system. Run eval tasks against models or agents, compare scores across a 4-pillar rubric.

## Quick Reference

```bash
# Model eval
python -m bench_cli run --tier full --model openai/qwen-local
python -m bench_cli run --concurrency 4 --tier full
python -m bench_cli run --tier viability --model openai/<new-model>  # 4-task diagnostic pass
python -m bench_cli run --model openai/thinking --as nemotron-ultra-550b  # route via moniker, record recognizable name

# Resume note: re-running an existing model now records its OpenRouter id (e.g.
# 'z-ai/glm-5.2') instead of the old alias, so resume treats it as a new model
# and re-runs. To continue an old run in its old identity, pass
# --as openai/<old-alias>.

# Compare scores
python -m bench_cli compare

# Discriminative profiles
python -m bench_cli recommend --model openai/qwen-local
python -m bench_cli compare-profiles openai/qwen-local openai/gemma-4-26-local

# Model cards and pricing
python -m bench_cli results generate
# Note: after a --as / OR-id run, `bench results generate --model <alias>` won't
# match rewritten logs (they store the recorded name). Query by the recorded
# OpenRouter id or omit --model to regenerate all cards.
python -m bench_cli prices refresh
python -m bench_cli prices list

# Agent eval (requires agent CLI installed: claude, codex, or gemini)
python -m bench_cli run --agent claude --agent-mode local --tier full

# Tests
pytest
```

## Documentation

| Document | Description |
|----------|-------------|
| [EVAL-GUIDE.md](docs/EVAL-GUIDE.md) | Every task, what it tests, how the scoring works |
| [BENCH-VERIFICATION-RUNBOOK.md](docs/BENCH-VERIFICATION-RUNBOOK.md) | Runbook for verification and sanity checks |
| [AGENTS.md](AGENTS.md) | Minimal agent-context file (deep context lives in the Second Brain project `bench`)|

## Architecture

- **Core:** Python + Inspect AI + inspect-swe
- **Model eval:** `generate()` solver — prompt in, answer out
- **Agent eval:** `--agent <name> --agent-mode <mode>` — 3 agents × 4 modes
- **Scoring:** 4 independent pillars per task — correctness, token efficiency, latency, cost
- **Judge model:** `openai/judge` → GLM-5.1 for qualitative tasks
- **Storage:** Inspect EvalLog binary `.eval` format + SQLite index
- **Model routing:** All models via `openai/<model-alias>` format through a LiteLLM proxy. Set `OPENAI_BASE_URL` and `OPENAI_API_KEY` in `.env`.
