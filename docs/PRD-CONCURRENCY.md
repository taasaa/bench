# PRD: Native Concurrency Control & Per-Model RPM Limits

**Status:** complete
**Completed:** 2026-04-17
**Project:** Bench
**Owner:** Michael Mazyar
**Scope:** feature
**Tier:** standard

## Problem Statement

Bench currently runs all Inspect tasks concurrently with no way to limit in-flight requests. The LiteLLM proxy serves multiple model deployments with rate limits, and without bench-level concurrency control, tasks can burst past RPM limits causing 429 errors that fail evals, even though LiteLLM's `enforce_model_rate_limits: true` would otherwise queue requests gracefully if we didn't oversaturate the proxy connection pool. Additionally, retry logic on HTTP errors is absent, causing flaky eval runs with no visibility into retry attempts.

## Success Criteria

1. `--concurrency N` limits Inspect to N tasks in-flight at any time — verify by: `bench run --tier quick --concurrency 1 --model openai/qwen-local` produces sequential log timestamps ~N× task duration apart, no concurrent overlap
2. `--sequential` short flag is accepted and equivalent to `--concurrency 1` — verify by: `bench run --tier quick --sequential --model openai/qwen-local` produces the same sequential timing as `--concurrency 1`
3. 429 from LiteLLM triggers bench-level exponential backoff retry — verify by: `grep retry_attempt scorer metadata` in eval log output shows retry_attempt=N for retried tasks; task completes successfully rather than failing
4. Connection errors (reset, timeout) trigger the same retry path — verify by: manually induce a transient error or confirm retry logic fires on httpx.ConnectError and httpx.ReadTimeout
5. `retry_attempt=N` is written to scorer metadata for every retried task — verify by: `inspect view` → task log → scorer metadata shows retry_attempt field
6. LiteLLM proxy applies rpm=120 to minimax and rpm=60 to NVIDIA models — verify by: LiteLLM proxy config has per-model rpm set, `enforce_model_rate_limits: true` set; 60 concurrent bench requests to a NVIDIA model are queued, not errored, within the proxy
7. `bench compare` output is unchanged — verify by: compare output format and scores identical before/after for same baseline run
8. `--help` documents `--concurrency/-j` and `--sequential` — verify by: `bench run --help` | grep concurrency shows the flag and description

## Implementation Approach

### Phase 1: Concurrency limiter (`bench_cli/concurrency.py`)

- `ConcurrencyLimiter` class: holds `asyncio.Semaphore(limit)`, exposes `acquire()` async context manager
- Python 3.11+ context manager protocol via `__aenter__`/`__aexit__`
- Default limit = `None` (unbounded) when flag absent
- Stateless — no shared state between tasks, just semaphore gating

### Phase 2: Retry wrapper (`bench_cli/retry.py`)

- `retry_with_backoff(fn, max_attempts=3, base_delay=1.0, max_delay=30.0)`
- Decorator/wrapper catching: `httpx.HTTPStatusError` (429, 500, 502, 503), `httpx.ConnectError`, `httpx.ReadTimeout`
- Exponential backoff: delay = min(base_delay × 2^(attempt-1), max_delay)
- On final failure: re-raise original exception
- Logs `retry_attempt=N` to scorer metadata dict argument (mutated in place)
- Exposed as `retry_with_backoff` utility, not wired into any call site yet

### Phase 3: CLI flags (`bench_cli/run.py`)

- `--concurrency` / `-j` Arg that takes an int (default: none, unbounded)
- `--sequential` flag that sets concurrency=1
- If `--concurrency 0` or negative: error and exit with usage message
- Pass limit to `ConcurrencyLimiter`, wrap `inspect_eval` call

### Phase 4: LiteLLM proxy config

- Path: `~/dev/litellm/config.yaml` (this is the LiteLLM proxy config — always needed when changing model aliases or rate limits)
- Per model: `rpm: 20` for minimax deployment, `rpm: 20` for each NVIDIA model
- Top-level: `enforce_model_rate_limits: true`
- No routing logic — bench model aliases map 1:1 to deployments; rpm limits are provider-side queue bounds

### Phase 5: CLAUDE.md update

- Document `--concurrency/-j N` and `--sequential` in CLI usage and Architecture sections

## Edge Cases & Gotchas

- `--concurrency 1` with inspect-swe agent eval: agent subprocess is I/O bound but waits on LiteLLM; semaphore still gates task dispatch, no other effect — this is correct
- Missing `--concurrency` default (None/unbounded): no Semaphore created, inspect_eval runs as today — verify this path has no overhead
- LiteLLM proxy not reachable: retry fires on ConnectError → logs retry_attempt=N → eventually raises; task scored as failure — correct behavior, no silent pass
- `--concurrency 0` or negative: exit 1 with message, no partial state
- `--concurrency` and `--sequential` both passed: `--sequential` wins, concurrency set to 1; document the precedence
- `retry_attempt` metadata for tasks that never retry: field absent (not `retry_attempt: 0`); scorer handles missing key gracefully

## Anti-Patterns to Avoid

- Don't create a global semaphore in module scope because inspect_eval may be called multiple times in-process; the limiter must be instantiated per-run and passed explicitly
- Don't retry on all httpx errors (e.g., 400 Bad Request) because those indicate a malformed request that will never succeed — only retry on 429, 5xx, and connection errors
- Don't set `retry_attempt` in retry.py by returning it from the wrapper (dropping the actual result) — mutate a metadata dict passed as an `out` parameter so the wrapper stays transparent
- Don't modify LiteLLM config to add routing logic — the rpm limits are hard provider-side blocks, not load balancing; no routing is the invariant

## Acceptance Checklist

- [ ] `--concurrency 1` produces sequential task execution — verify by: log timestamps and task overlap analysis
- [ ] `--sequential` works as alias for `--concurrency 1` — verify by: identical timing behavior
- [ ] 429 triggers exponential backoff retry with scorer metadata logged — verify by: eval log + `inspect view`
- [ ] Connection errors trigger same retry path — verify by: error injection or code review
- [ ] Per-model RPM limits configured on LiteLLM proxy — verify by: proxy config review
- [ ] `enforce_model_rate_limits: true` set on proxy — verify by: proxy config review
- [ ] `bench compare` unchanged for same baseline — verify by: before/after output diff
- [ ] `--help` documents both flags — verify by: `bench run --help`
- [ ] Missing concurrency flag defaults to unbounded (no semaphore) — verify by: code review of None path

## Open Questions

- What is the exact path to the LiteLLM proxy config? → Configure in your `~/dev/litellm/config.yaml`
- Should `--concurrency` validate against the proxy's rpm limits (e.g., warn if N > rpm)? → Not in v1; the proxy queues requests, so the only cost is latency. Add a warning if use case emerges.
- Is there an existing `httpx` retry pattern in the codebase I should integrate with rather than duplicate? → No known precedent from review; retry.py is new. Confirm no shared retry utility exists before finalizing.