# Scorer Explanation Schema

All scorers in `scorers/` write `key=value` pairs in their `Score.explanation` strings. The `bench compare` command reads these via regex to populate the CORRECT column in the pillar table.

---

## Correctness Scorers

Tasks use one of two correctness scorers:

### verify_sh

Outputs `PASS N/M` format. Explanation contains:

```
correctness=0.67, efficiency=1.00, safety=1.00
PASS 2/3
check_1: pass
check_2: pass
check_3: fail (type mismatch)
```

### llm_judge

LLM judge returns `SCORE: N` (0-10, normalized to 0-1). Explanation contains:

```
correctness=0.80
Judge reasoning text here...
SCORE: 8
```

---

## Ratio Scorers

### token_ratio_scorer

```
efficiency_ratio=1.230, actual_total_tokens=406, reference_tokens=500, reference_source=system_default
```

### time_ratio_scorer

```
latency_ratio=0.720, actual_seconds=41.2, reference_seconds=29.6, reference_source=baseline, reference_model=qwen-local
```

When suppressed (below noise floor):

```
latency_ratio=suppressed, actual_seconds=3.1, reference_seconds=2.8, noise_floor=5.0s, note=ratio unreliable (below noise floor)
```

---

## Parsing

`bench_cli/compare.py` extracts pillar values:

- **Correctness**: `_numeric_val()` reads `llm_judge` (preferred) or `verify_sh` score value
- **Efficiency**: `token_ratio_scorer` score value
- **Latency**: `time_ratio_scorer` score value (NaN = suppressed)

No regex parsing of explanation strings for pillar values — values are read directly from `Score.value`.

---

## Adding a New Scorer

1. Create `scorers/<name>.py` with `@scorer(metrics=[mean()])` decorator
2. Return `Score(value, explanation, metadata)` with `"pillar": "<pillar_name>"` in metadata
3. Export from `scorers/__init__.py`
4. Update `compare.py` `_extract_from_scorers()` if adding a new correctness source
5. Add tests in `tests/test_scorers.py`

---

*Last updated: 2026-04-14*
