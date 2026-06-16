# Bench

Standalone personal LLM/agent eval harness. Python + Inspect AI + inspect-swe. 36 tasks, 4-pillar scoring (correctness, token-eff, latency, cost), discriminative analysis layer.

## Source of truth → Second Brain

**The Second Brain project `bench` is authoritative and the sketchpad for this project.**
Read it before any substantive work:

```bash
brain-ctl context bench          # Read First, Current Handoff, Operating Rules, Decisions, Gotchas, System Contracts
brain-ctl tasks:list bench       # roadmap / in-flight work
```

Deep context, rationale, task format, full CLI reference, architecture details, gotchas,
decisions, and next steps all live there — not here. This file is deliberately minimal.

## Environment (non-negotiable)

- **Use the project `.venv`:** `.venv/bin/python` and `.venv/bin/pytest`. No system python.
- **Models route through a LiteLLM proxy** as `openai/<alias>`. Credentials in `.env` (gitignored, auto-loaded). Never direct API calls.

## Essential commands

```bash
.venv/bin/python -m bench_cli run --tier full --model openai/<alias>   # run an eval
.venv/bin/python -m bench_cli compare                                   # pivot table of results
.venv/bin/pytest                                                        # test suite
```

## Footguns (see SB Gotchas for the full list)

- Scorers live in `scorers/` at repo root — `from scorers import ...`. **`bench_cli/scorers/` does not exist.**
- `verify.sh` must be executable; POSIX regex only (`grep -E`, `[[:space:]]` not `\s`).
- Inspect `.eval` logs are binary ZIP — decode with `zipfile`, not `json.loads`.
