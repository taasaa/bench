# NVIDIA NIM Route Viability — 2026-06-19

**Method:** direct probe through the LiteLLM proxy (`http://smallbox:4000/v1`), 2
representative prompts per route (short competence + longer execution, sourced
from real bench task `dataset.json` inputs), cache-busted with a unique nonce.
Borderline models got a 3× q3 recheck for consistency. Total wall-clock:
~4 minutes for all 10 routes. Retries: 3 on 429/5xx/timeout, fail-fast on
other errors.

**Goal:** rank the 10 nvidia_nim routes in `~/dev/litellm/config.yaml` by
viability for full eval — speed + reliability, not quality. No `logs/` corpus
pollution, no `results/` card writes.

**Reproducibility:**
- Scripts: `scripts/probe_nim_routes.py`, `scripts/report_viability.py`
- Raw data: `logs/_nim-viability/cachebust.json` (gitignored)
- Per-alias: `logs/_nim-viability/<alias>.json` (gitignored)

## Verdicts

| alias | verdict | short total | long total | vis tok/s (long) | key signal |
|---|---|---:|---:|---:|---|
| **deepseek-v4-flash** | usable | 1.05s | 1.04s | 51 | fast, clean |
| **mistral-large-3-675b** | usable | 0.42s | 1.32s | 52 | fastest overall |
| **deepseek-v4-pro** | usable | 1.77s | 2.49s | 21 | solid mid-tier |
| **qwen3.5-397b** | usable | 4.16s | 12.68s | 4 | reliable but slow on long |
| **glm-5.1** | usable | 7.23s | 16.36s | 3 | was 429-blocked (SB `09015782`) — **passes now** |
| **diffusiongemma-26b-a4b** | usable | 0.49s | 0.38s | 134 | unusual (diffusion-LLM) but works |
| **minimax-m3** | slow | 8.02s | 147.69s | 4 | huge variance; cold-start tax |
| **nemotron-ultra-550b** | slow | 6.33s | 86.88s | 0.5 | 550B → predictably heavy |
| **kimi-2.6** | flaky | 7.46s | 28.41s | 2 | 4 calls: 1 gibberish, 3 reasoning-preamble leaking into output — never a clean answer |
| **nemotron-nano-omni-30b** | broken | 1.35s | 12.60s | 0 | reasoning-only: 3/3 retries emit 256 reasoning tokens, **0 visible chars** |

**Totals:** 6 usable, 2 slow, 1 flaky, 1 broken. No 429/500 errors observed
on any route during the probe (all retries were unused).

## Recommendation: which routes to full-eval

| Tier | Models | Rationale |
|---|---|---|
| **Run full eval** | `deepseek-v4-flash`, `mistral-large-3-675b`, `deepseek-v4-pro` | Fast + reliable; the only routes I'd confidently commit to a multi-hour run |
| **Maybe full eval** | `diffusiongemma-26b-a4b`, `qwen3.5-397b`, `glm-5.1` | Unusual arch / interesting data points; slower but functional |
| **Skip** | `minimax-m3`, `nemotron-ultra-550b`, `kimi-2.6` | Variance / cost / flakiness make full eval wasteful |
| **Don't bother** | `nemotron-nano-omni-30b` | Reasoning model without visible-output config — likely needs a `--thinking` / system-prompt config change; not a bench-side issue |

## Methodology gotchas (worth knowing for future probes)

### 1. Proxy Redis cache masks reality

The proxy has `cache: true` (Redis) in `~/dev/litellm/config.yaml`. First
probe runs will return cached responses — including stale bad output — that
look fast and clean but aren't real generation. **Always bust cache for
viability probes** (append a unique nonce to each prompt). This is what made
kimi-2.6 initially look "broken with gibberish": the cache had a stale
response from a prior bad run.

### 2. Cold-start tax

First call to a route is much slower than subsequent calls (vllm/KV-cache
warmup, model load). Production timing should warm before measuring.
Observed cold-start penalties:

| Route | First-call short | Subsequent short |
|---|---:|---:|
| `minimax-m3` | 36s | 1.3s |
| `deepseek-v4-pro` | 23s | 1.8s |
| `glm-5.1` | 7.5s | 6.8s |
| `nemotron-ultra-550b` | 38s | 7.6s |

### 3. Reasoning-model content accounting

Several NIM models have `supports_reasoning: true` (kimi-2.6, nemotron-nano-omni-30b, qwen3.5-397b, glm-5.1). They emit reasoning tokens into `usage.completion_tokens` that don't reach the user-visible content. Always judge by visible text (`text_len`), not by usage — otherwise models with heavy reasoning look "fast" but produce nothing usable. `nemotron-nano-omni-30b` is the worst case: 256 reasoning tokens / 0 visible chars on every q3 attempt.

### 4. Multimodal gibberish heuristic

For English-instruction prompts, coherence is reasonably detected by checking for domain markers (`the`, `class`, `venv`, `step`, etc.). For reasoning-model outputs that begin with preamble like "The user is asking...", a stricter check is needed (`_is_actual_answer` in `report_viability.py`) that excludes preamble-style openings.

## Prior-knowledge wins vs losses

**Wins:**
- `glm-5.1` is **no longer 429-blocked** (was blocked per SB task `09015782`). Now usable but slow.
- `minimax-m3` NIM route **did not 500** this run (was known flaky per handoff residuals). Still SLOW due to 147s long-task variance.

**Losses:**
- `kimi-2.6` is genuinely **flaky**, not just slow — it produces reasoning-preamble mixed with answer, never a clean standalone answer. The NIM route is not production-viable for bench use.

## Out of scope

- **Quality assessment** (correctness / capability): explicitly excluded per user ("not interested in quality for now").
- **Cost pillar analysis:** prices are already known from the proxy config; not measured here.
- **Cache freshness for production eval:** cache should be **disabled** for actual bench runs (or at least, ensure each prompt gets a fresh response) — otherwise eval results will be polluted by prior runs.

## Next steps

- Run full eval (`bench run --tier full --model openai/<alias>`) for the 3 "Run full eval" routes (`deepseek-v4-flash`, `mistral-large-3-675b`, `deepseek-v4-pro`).
- Optional: full eval for the 3 "Maybe full eval" routes if data points are desired.
- Skip the 4 broken/slow/flaky routes (no full eval).
- The capability `bench probe routes [...]` (SB task `913ca216`) will fold this workflow into a first-class bench subcommand for future model additions.