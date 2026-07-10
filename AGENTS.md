# Bench

Standalone LLM/agent eval harness — Python + Inspect AI + inspect-swe, 36 tasks, 4-pillar scoring.

This project is tracked in the Second Brain as `[[bench]]`.

## Before working

1. Load the **`second-brain`** skill. Use `brain-ctl --help` / `brain-ctl <command> --help` for command syntax and response shapes.
2. Start a session and load context: `brain-ctl sessions:start bench --agent <name> --goal "<goal>"`. The response is a full brief — `project.current_state`, `current_handoff`, `read_first`, `operating_rules`, `decisions`, `gotchas`, active/blocked/backlog tasks, and `last_session`. Capture the returned `id`. Goal not known yet? Start without `--goal`; set it via `sessions:append bench <id> --goal "..."` once clear.
3. Or, for a quick context read without starting a session: `brain-ctl projects:context bench`.

## Operating rules (anti-corruption, inline)

Restated so they hold even if an agent skips the `second-brain` skill:

- All vault writes go through `brain-ctl` → REST → daemon → vault. Never edit `~/SecondBrain/` directly.
- Don't re-read to verify a brain-ctl write — the response carries the trust signal (`handoff_written`, `sections_updated`, `updated`, `meta.sanitized`).
- Tasks are atomic: open one, close it done/cancelled — don't edit task text as work evolves. Reasoning and history go in `sessions:append`. Tasks are not a scratchpad or changelog.
- `Current Handoff` is the authoritative current-state snapshot, rewritten at session end: keep what's still relevant, drop what's superseded — the session timeline preserves history.
- No staleable numbers in vault prose — write structural outcomes (`pytest` green, `ruff` clean), not counts. Run commands live when counts are needed.

## Repo-mechanical

### Environment (non-negotiable)

- **Use the project `.venv`:** `.venv/bin/python` and `.venv/bin/pytest`. No system python.
- **Models route through a LiteLLM proxy** as `openai/<alias>`. Credentials in `.env` (gitignored, auto-loaded). Never direct API calls.

### Essential commands

```bash
.venv/bin/python -m bench_cli run --tier full --model openai/<alias>   # run an eval
.venv/bin/python -m bench_cli compare                                   # pivot table of results
.venv/bin/pytest                                                        # test suite
```

### Verification

```bash
.venv/bin/pytest -q
.venv/bin/pytest --co -q
.venv/bin/python -m bench_cli run --tier viability --list-tasks
brain-ctl health
git -C ~/dev/bench status
```

## Pointer

Everything else — current handoff, decisions, gotchas, system contracts, task format, architecture details, recent sessions — lives in the Second Brain. Do not duplicate it here.
