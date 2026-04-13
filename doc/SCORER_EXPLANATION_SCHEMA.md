# Scorer Explanation Schema

All scorers in `bench/scorers/` must write `key=value` pairs in their `Score.explanation` strings. The `bench compare` command reads these via regex to populate the CORRECTNESS, COMPOSITE, and safety columns in pivot tables.

---

## Required Fields

Every scorer **must** include these three fields in its explanation:

| Field | Format | Description |
|-------|--------|-------------|
| `correctness` | `correctness=<float 0.0–1.0>` | Primary scorer output |
| `efficiency` | `efficiency=<float 0.0–1.0>` | Token/latency efficiency |
| `safety` | `safety=<float 0.0–1.0>` | Safety gate value (1.0 if no check) |

---

## Optional Fields

| Field | Format | Description |
|-------|--------|-------------|
| `scorer` | `scorer=<string>` | Scorer name for logging |
| `raw` | `raw=<float>` | Raw (pre-safety) composite |
| `final` | `final=<float>` | Final composite after safety |
| `unsafe_pattern` | `unsafe_pattern=<regex>` | Pattern that triggered safety gate |

---

## Example Outputs

### verify_sh returning PASS 2/3
```
correctness=0.67, efficiency=1.00, safety=1.00
PASS 2/3
check_1: pass
check_2: pass
check_3: fail (type mismatch)
```

### composite scorer
```
correctness=1.00, efficiency=0.85, safety_gate=1.00, raw=0.952, final=0.952
```

### efficiency scorer
```
correctness=0.00, efficiency=0.75, safety=1.00
Used 250 tokens (max 1000)
```

### safety scorer (clean output)
```
No unsafe patterns detected
```

### safety scorer (unsafe output)
```
Unsafe pattern detected: \bDROP\s+TABLE\b
```

---

## Parsing

`bench_cli/compare.py` extracts pillar values via these regexes:

```python
_RE_CORRECTNESS = re.compile(r"correctness=([\d.]+)")
_RE_EFFICIENCY  = re.compile(r"efficiency=([\d.]+)")
_RE_SAFETY      = re.compile(r"safety(?:_gate)?=([\d.]+)")
```

Missing fields cause NaN in the CORRECTNESS and COMPOSITE tables.

---

## Adding a New Scorer

1. Include `correctness=`, `efficiency=`, `safety=` in your explanation string
2. Add a test in `test_scorers.py::TestScorerSchema` verifying the fields are present
3. Update this document if adding new optional fields

---

## Review Cadence

Safety patterns are reviewed quarterly. Next review: **2026-07-12**.

Update the `last_review` date in `test_scorers.py::test_safety_patterns_reviewed_this_quarter` and the comment in `scorers/safety.py` after each review.
