# Bench Documentation

## Contents

| Document | Description |
|----------|-------------|
| [PRD-DRAFT.md](./PRD-DRAFT.md) | Draft PRD v6 — post Inspect AI feature audit |
| [PRD-REVIEW.md](./PRD-REVIEW.md) | Technical co-founder review of PRD |
| [EVAL-TASKS.md](./EVAL-TASKS.md) | 15 eval tasks derived from actual work/failures |
| [IMPLEMENTATION-NOTES.md](./IMPLEMENTATION-NOTES.md) | **Start here** — comprehensive implementation record |

## Quick Reference

For AI agents and new contributors, read these in order:

1. **Start:** [IMPLEMENTATION-NOTES.md](./IMPLEMENTATION-NOTES.md) — architecture, task inventory, scoring, file layout
2. **Context:** [PRD-DRAFT.md](./PRD-DRAFT.md) — why Bench exists, design decisions, Phase 1/2/3 roadmap
3. **Tasks:** [EVAL-TASKS.md](./EVAL-TASKS.md) — 15 eval tasks with failure patterns and scoring logic
4. **Reference:** [AGENT.md](../AGENT.md) — living project reference at repo root (agent-facing)

## Key Entry Points

```bash
bench run --tier full --model openai/gemma-4-e2-local    # Run eval
bench compare                                           # Compare scores
python3 -m pytest tests/ -v                             # Test suite
```
