# Bench PRD — Technical Co-Founder Review

> **Date:** 2026-04-08
> **Reviewers:** 5 parallel agents (First Principles, Research Verification, Red Team, Scientific Rigor, Implementation Feasibility)
> **Document reviewed:** PRD-DRAFT.md (post-research v3)

---

## Executive Summary

The PRD has strong bones. The core insight — "Bench is a test runner + scorer + comparison engine, nothing more" — is correct. The two-mode architecture (model eval via Inspect AI, agent eval via subprocess) is sound in principle. The tiered evaluation concept is industry-standard.

But the PRD has **3 factual errors that invalidate architecture decisions**, **1 critical unspecified component** (agent eval protocol), and **a Phase 1 that is 2-3x over-scoped** for what it claims to deliver.

The good news: all of these are fixable without rethinking the core concept.

---

## CRITICAL — Must Fix Before Implementation

### 1. Inspect AI does NOT use LiteLLM natively

**Section affected:** 9 (Tech Stack, "Model access: local LiteLLM gateway")

**Finding:** Inspect AI has its own native provider adapters (OpenAI, Anthropic, Google, Ollama, etc.) with dedicated SDK dependencies. LiteLLM is NOT a dependency. The entire "zero-friction LiteLLM gateway" architecture is based on a false assumption.

**Impact:** The Phase 1/Phase 2 model access story is wrong. The "no code changes between phases, just LiteLLM config" promise is invalid.

**Fix:** Rewrite Section 9 to describe Inspect AI's actual native multi-provider support:
- Phase 1: Use Inspect's native providers with API keys (Anthropic, OpenAI, Ollama for local)
- Phase 2: Same native providers, just different model names
- LiteLLM proxy CAN be used via Inspect's "OpenAI Compatible API" feature (`OPENAI_API_BASE`), but this requires configuration, not "zero friction"
- For your local models: Inspect supports Ollama natively — no LiteLLM needed for Phase 1

---

### 2. Agent eval protocol is completely unspecified

**Section affected:** 3 (Architecture, Mode 2), 11 (Phase 1)

**Finding:** The PRD says "point Bench at an agent command, send tasks, wait for completion, score results" — but never defines HOW. This is the hardest problem in the system and it gets two sentences. Every real agent benchmark (SWE-bench, WebArena, OpenHands) has extensive infrastructure for:
- How tasks are delivered to the agent
- How workspace state is managed between tasks
- How agent completion is detected
- How results are extracted for scoring
- Timeout handling

**Impact:** Phase 1 cannot include agent eval without this specification. Attempting to build it without a design will result in days of thrashing.

**Fix:**
- **Claude Code has a programmatic interface the PRD doesn't mention:** `claude -p --output-format json --max-turns N --allowedTools ...` provides structured JSON output, turn limits, and tool restrictions. This IS the agent eval interface.
- Define the agent eval protocol:
  1. Bench creates a workspace directory per task (copy fixtures in)
  2. Bench runs `claude -p --output-format json --max-turns 20 "TASK_PROMPT"` in that workspace
  3. Bench captures stdout (JSON with final message) + filesystem diff
  4. Bench runs `verify.sh` against workspace state — exit 0 = pass
  5. Bench resets workspace for next task
- **Phase 1 should defer agent eval to Phase 2.** Model eval alone answers "is model A better?" — which IS the Phase 1 goal.

---

### 3. CALM framework (ICLR 2025) citation appears fabricated

**Section affected:** 6 (Scoring Design), 14.C (Research Appendix)

**Finding:** No paper titled or referring to a "CALM framework" from ICLR 2025 describing 12 LLM-as-judge bias types could be found. The biases themselves (position, verbosity, self-preference) are real and well-documented in Zheng et al. (2023) "Judging LLM-as-Judge with MT-Bench and Chatbot Arena." The "CALM (ICLR 2025)" attribution was likely hallucinated by a research agent.

**Impact:** Undermines credibility if someone checks the citation.

**Fix:** Replace "CALM framework (ICLR 2025)" with "Zheng et al. (2023) and the broader LLM-as-judge literature." The bias types and mitigation strategies are correct — just the citation is wrong.

---

## HIGH — Significant Problems That Will Cause Pain

### 4. Safety scoring formula is mathematically contradictory

**Section affected:** 6 (Scoring Design)

**Finding:** The PRD states:
```
task_score = correctness * 0.5 + efficiency * 0.25 + safety * 0.25
```
And also: "if safety = 0, entire task score = 0"

These contradict. In the additive formula, safety=0 gives `correctness * 0.5 + efficiency * 0.25`, not zero. The formula double-counts safety as both an additive weight and a multiplicative gate.

**Fix:** Pick one model:
```
# Option A: Multiplicative gate (recommended for safety emphasis)
task_score = (correctness * 0.67 + efficiency * 0.33) * safety_gate
# where safety_gate is binary (0 or 1)

# Option B: Additive with penalty
task_score = correctness * 0.5 + efficiency * 0.25 + safety * 0.25
# Remove the "safety = 0 zeroes everything" claim
```

### 5. Phase 1 is 2-3x over-scoped

**Section affected:** 11 (Implementation Phases)

**Finding:** Phase 1 as described includes: Inspect AI setup, 10-15 tasks across 3 categories, 3 scorer types (including LLM judge), CLI with run+compare, SQLite index, EvalLog parsing, AND implies agent eval is part of it. The research agents agree this is too much for "a few sessions."

**What Phase 1 should actually be:**
1. Install Inspect AI, configure API keys for 2 providers
2. Write 10-15 model-eval-only tasks with deterministic verification (exact match, script-based)
3. Run `inspect eval` directly — no CLI wrapper needed yet
4. A simple Python script to compare two runs' scores
5. Answer: "is model A better than model B?"

**No:** SQLite, CLI framework, LLM judge, baselines, historical tracking, agent eval.

**Fix:** Restructure phases:
- **Phase 1 (MVP):** Model eval only. Deterministic tasks. Direct Inspect AI usage. One comparison script. ~2-3 sessions.
- **Phase 2 (Agent eval):** Add agent eval with `claude -p` protocol, workspace isolation, verify.sh scoring. Custom CLI. ~3-5 sessions.
- **Phase 3 (Infrastructure):** SQLite, baselines, history, LLM judge, bootstrap CI. ~3-5 sessions.
- **Phase 4 (Intelligence):** Leaderboards, drift detection, value scores, external benchmarks.

### 6. 15-20 tasks is statistically insufficient for the claimed comparisons

**Section affected:** 4 (Tiers), 6 (Statistical comparison)

**Finding:** With n=15-20 tasks, the minimum detectable effect size is Cohen's d ≈ 0.66 (medium-to-large). Detecting a 5% improvement requires ~313 paired tasks. Bootstrap 95% CI with n=15 has poor coverage (88-92% for nominal 95%). The statistical apparatus (bootstrap CI, Cohen's d, Benjamini-Hochberg) is theater at this sample size.

**Impact:** Users will see "significant" differences that are noise, or "no significant difference" when real differences exist.

**Fix:**
- Phase 1-2: Report raw scores. "Model A: 12/15, Model B: 9/15, per-task breakdown below." No CI, no p-values. This is honest and actionable.
- Phase 3+: Add bootstrap CI only after reaching 30+ tasks. Statistical sophistication scales with data.
- Target 30 deterministic tasks for Phase 1 (not 15 mixed-scoring tasks). Deterministic scoring is free — the constraint is task writing effort, not API cost.

### 7. Docker decision is contradictory

**Section affected:** 12 (Open Questions, resolved #4), 11 (Phase 2)

**Finding:** Section 12 says "No Docker. Tasks run directly against real environment." Section 11 Phase 2 says "Docker sandboxing for terminal tasks." Both are presented as resolved decisions.

**Fix:** Decide once. Recommendation: no Docker in Phase 1-2. Phase 3 can add Docker for terminal tasks when you actually need isolation. Document the decision clearly.

---

## MEDIUM — Real Problems That Should Be Addressed

### 8. Task isolation for sequential agent eval

If agent eval runs tasks sequentially in the same environment (which it will, since "no Docker"), earlier tasks modify the filesystem and contaminate later tasks. The PRD addresses none of this.

**Fix:** Agent eval needs per-task workspace isolation — either `git checkout` between tasks, or fresh directory copies. Add to agent eval protocol specification.

### 9. No calibration protocol for LLM judge

The PRD describes LLM-as-judge bias mitigation but never asks: does the judge agree with humans? Without calibration, the judge's accuracy is unknown.

**Fix:** Before trusting LLM judge scores, manually grade 20-30 outputs and compute Cohen's Kappa between judge and human. Target: Kappa >= 0.61 (substantial agreement). Add as Phase 3 prerequisite.

### 10. model_graded() function name is wrong

**Section affected:** 3 (Component breakdown, Scorer Engine)

The actual Inspect AI functions are `model_graded_qa()` and `model_graded_fact()`, not `model_graded()`.

**Fix:** Update all references. Will cause import errors at implementation time if not caught.

### 11. TerminalBench/Harbor reference is unverifiable

**Section affected:** 14.B (Research Appendix)

Could not be found in any public source. May have been hallucinated by a research agent.

**Fix:** Replace with real containerized agent benchmarks: SWE-bench, OSWorld, AgentBench.

### 12. Judge model family rule contradicts itself

**Section affected:** 6 (Scoring), 12 (Open Questions)

Section 6: "Different model family than model under test."
Section 12: "Haiku for standard, Sonnet/Opus for deep."

Evaluating Claude Sonnet with Claude Haiku as judge = same family. Either enforce cross-family (GPT judges Claude) or relax the rule.

**Fix:** For a personal tool, same-family judge with temperature=0 and structured output is probably fine. Change rule to: "recommend cross-family where practical; same-family with temp=0 is acceptable."

### 13. Missing specifications

The following are mentioned but not defined well enough to implement:
- **Task schema:** What does a task actually look like? Prompt string? Prompt + files? Expected output format?
- **Script scorer interface:** What does verify.sh receive? What's the exit code convention?
- **Trajectory scorer:** Requires access to agent's tool call history — but agent eval treats the agent as a black box. Contradiction.
- **Composite scorer normalization:** How do you normalize exact match (0/1), LLM judge (1-5), and token efficiency (continuous) onto the same scale?
- **Config file format:** No mention of bench.toml or equivalent

**Fix:** Write concrete examples of one complete task, one scorer, and one agent eval run before starting implementation.

### 14. Value score formula is dimensionally broken

**Section affected:** 6 (Value Score)

`correctness / (token_cost_usd * latency_seconds)` divides a unitless score by (dollars × seconds). The result has no interpretable meaning. Also easily gamed: a model answering 1 task in 0.1s outscores one answering 14/15 in 10s.

**Fix:** Remove or redesign. Better: report correctness, cost, and latency as independent axes. Let the user decide the tradeoff.

---

## MINOR — Polish Items

### 15. EvalLog latency capture is uncertain

Inspect AI's documented EvalLog structure includes token counts but latency is not explicitly confirmed. May need custom implementation for P50/P95/P99 latency tracking.

### 16. Two eval modes is a false dichotomy

Model eval is just agent eval with a trivial agent (single-turn, no tools). The distinction is an implementation detail, not a conceptual split. Consider unifying into one eval mode where model eval is the degenerate case.

### 17. Task as Python module creates friction

Most eval tasks are data (prompt + files + expected output). Requiring a Python module per task is overkill. Consider tasks-as-data (YAML/JSON) with Python modules only for custom logic.

### 18. Four tiers is at least two too many

For a personal home-lab tool: "quick" and "full" suffice. Adversarial is a task category, not an execution tier. The tier system adds a classification problem without proportional value.

### 19. Leaderboard for one person

A sorted `bench history` output serves the same purpose. Add leaderboard only when you have enough runs to need it.

---

## Recommended PRD Rewrite Priorities

| Priority | Item | Effort |
|----------|------|--------|
| **P0** | Fix LiteLLM → Inspect native providers | 30 min |
| **P0** | Specify agent eval protocol or defer to Phase 2 | 1 hour |
| **P0** | Fix CALM citation | 10 min |
| **P0** | Fix safety scoring formula | 15 min |
| **P1** | Restructure phases (MVP → Agent → Infrastructure → Intelligence) | 1 hour |
| **P1** | Cut Phase 1 to model eval only, deterministic scoring | 30 min |
| **P1** | Target 30 tasks for Phase 1, drop statistical claims | 15 min |
| **P1** | Fix Docker contradiction | 5 min |
| **P2** | Add calibration protocol for LLM judge | 30 min |
| **P2** | Define task schema with concrete example | 1 hour |
| **P2** | Fix model_graded() references | 10 min |
| **P2** | Replace TerminalBench with real benchmarks | 15 min |
| **P2** | Remove/fix value score formula | 10 min |

---

## Bottom Line

The PRD is **70% right**. The core concept (Inspect AI + custom tasks + comparison), the two-mode architecture, and the tiered evaluation approach are all sound. But three things need to happen before writing code:

1. **Fix the facts** — LiteLLM assumption is wrong, CALM citation is fabricated, TerminalBench is unverifiable
2. **Scope Phase 1 down aggressively** — model eval only, deterministic scoring, no CLI framework, no SQLite. One Python script answering "is A better than B?"
3. **Specify the agent eval protocol** — or explicitly defer it to Phase 2 with a clear design doc before Phase 2 begins

The fastest path to value: 30 deterministic model-eval tasks, run through Inspect AI directly, compare scores in a table. Everything else layers on after that first answer is validated.
