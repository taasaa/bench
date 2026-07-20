# Bench

Standalone local LLM and AI agent evaluation system. Run evaluation tasks against models or agents, compare scores across a 4-pillar rubric, and perform Bayesian capability estimation.

## Quick Reference

```bash
# Model evaluation
python -m bench_cli run --tier full --model openai/qwen-local
python -m bench_cli run --concurrency 4 --tier full
python -m bench_cli run --tier viability --model openai/<new-model>  # 4-task diagnostic pass
python -m bench_cli run --model openai/thinking --as nemotron-ultra-550b  # route via moniker, record recognizable name

# Compare scores (classical averages)
python -m bench_cli compare

# Bayesian Capability Estimation (IRT)
python -m bench_cli irt fit                # fit Bayesian 2PL model, output θ and 95% CIs
python -m bench_cli irt item-analysis       # evaluate task difficulties and discrimination bands

# Preset Model Recommendations & Pareto Frontiers
python -m bench_cli recommend-preset --preset best             # rank by capability (θ if IRT enabled, else raw correctness)
python -m bench_cli recommend-preset --preset balanced         # output Pareto-optimal models (★)
python -m bench_cli recommend-preset --preset cheap-fast       # filter cost and rank by speed
python -m bench_cli recommend-preset --preset best --fully-evaluated  # fair apples-to-apples cohort comparison

# Discriminative profiles
python -m bench_cli recommend --model openai/qwen-local
python -m bench_cli compare-profiles openai/qwen-local openai/gemma-4-26-local

# Model cards and pricing
python -m bench_cli results generate
python -m bench_cli prices refresh
python -m bench_cli prices list

# Agent evaluation (requires agent CLI installed: claude, codex, or gemini)
python -m bench_cli run --agent claude --agent-mode local --tier full

# Tests
pytest
```

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Technical architecture, sandboxing, model routing, and pipeline design |
| [STATISTICAL-SCORING-AND-IRT.md](docs/STATISTICAL-SCORING-AND-IRT.md) | Mathematical formulation of Bayesian 2PL IRT fitting and Pareto optimization |
| [EVAL-GUIDE.md](docs/EVAL-GUIDE.md) | Comprehensive description of all 36 tasks, correctness scorers, and failure classes |
| [BENCH-VERIFICATION-RUNBOOK.md](docs/BENCH-VERIFICATION-RUNBOOK.md) | Runbook for verification, health checks, and sanity runs |

## Architecture & Features

- **Sandboxed Execution**: Python + Inspect AI + inspect-swe orchestration. Run evaluations in secure Docker environments or local subshells.
- **4-Pillar Scoring**: Calculates four independent metrics per evaluation run—Correctness, Token Efficiency, Latency, and Cost—avoiding opaque composite scores.
- **Bayesian IRT Capability Estimation**: Fits a 2-Parameter Logistic (2PL) model using PyMC MCMC sampling to estimate model latent capability ($\theta$) while accounting for individual task difficulties and discrimination power.
- **Multi-Objective Preset Router**: Computes the multi-objective Pareto frontier across capability, speed, and cost, filtering out dominated models and highlighting Pareto-optimal ones.
- **Model Routing**: Integrates with a local LiteLLM proxy (`~/dev/litellm/config.yaml`) for rate-limiting, retries, and dynamic mapping of moniker tiers.
- **Storage**: Standardized on Inspect's binary `.eval` format for evaluation run history.
