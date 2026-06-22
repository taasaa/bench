#!/usr/bin/env python3
"""Print a final viability report from logs/_nim-viability/cachebust.json.

Uses cache-busted probe data (proxy's Redis cache masked real performance
in the initial run). Verdict = combination of timing + content quality.

Usage:
    .venv/bin/python scripts/report_viability.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = REPO_ROOT / "logs" / "_nim-viability" / "cachebust.json"


def _has_sensible_english(text: str) -> bool:
    """Loose coherence check: contains real English words/phrases."""
    if not text:
        return False
    # Strip non-letter chars and split into word-like runs.
    tokens = re.findall(r"[A-Za-z]{3,}", text)
    if not tokens:
        return False
    # Common English words from q3/f6 domain — if any are present, likely coherent.
    markers = {
        "the", "and", "with", "class", "def", "init", "return", "venv",
        "activate", "python", "step", "source", "directory", "install",
        "create", "data", "store", "self", "method", "keys", "value",
    }
    lower = {t.lower() for t in tokens}
    if markers & lower:
        return True
    # Fallback: if >50% of tokens are common short English words, likely coherent.
    common = sum(1 for t in lower if t in markers)
    return common / max(len(lower), 1) > 0.2


def _is_actual_answer(text: str) -> bool:
    """Stricter check: response looks like an answer, not reasoning preamble.

    A response that starts with 'The user is asking...', 'Let me think...',
    'I need to...' is the model's chain-of-thought leaking into the visible
    output — not an actual answer. Looks for answer-shaped openings.
    """
    if not text:
        return False
    lowered = text.strip().lower()
    # Reasoning preamble patterns — the model is thinking out loud.
    preamble_starts = (
        "the user is asking",
        "the user wants",
        "the user asks",
        "the user requested",
        "the user has",
        "the user is",
        "let me think",
        "let me analyze",
        "let me consider",
        "let me write",
        "let me implement",
        "let me reason",
        "i need to",
        "i should",
        "i will write",
        "i will now",
        "i will implement",
        "i will create",
        "i am asked",
        "i'm asked",
        "i've been asked",
        "we need to",
        "we are to",
        "we will",
        "the prompt",
        "the question",
        "the task",
        "the request",
        "the instructions",
        "the user",
        "reasonable_user",
        "user prompt",
        "this is a",
        "in this task",
        "to answer this",
        "to respond to",
    )
    for prefix in preamble_starts:
        if lowered.startswith(prefix):
            return False
    # Answer-shaped openings.
    answer_starts = (
        "1.", "1)", "step 1", "step one", "first,", "first.", "first ",
        "```",  # code block
        "run ", "use ", "create ", "execute ", "implement ", "import ",
        "class ", "def ", "from ",
        "here", "the cache", "this is", "you can", "you should",
    )
    return any(lowered.startswith(s) for s in answer_starts)


def _classify(short: dict, long_: dict, recheck: list | None = None) -> tuple[str, str, str]:
    """Return (verdict, note, color_hint) using text_len as truth source.

    If recheck (list of dicts from stage 2) is supplied and the original short
    produced 0 visible chars, use the recheck results to refine: if rechecks
    succeed, mark 'usable' (initial empty response was an anomaly); if
    rechecks also empty, mark 'broken' (consistent behavior).
    """
    s_ok = short.get("ok", False)
    l_ok = long_.get("ok", False)
    if not s_ok and not l_ok:
        return "broken", "both prompts failed (after retries)", "bad"
    if not s_ok or not l_ok:
        return "broken", "one prompt failed (after retries)", "bad"

    s_text = short.get("text_len", 0)
    l_text = long_.get("text_len", 0)
    l_total = long_.get("total_s") or 0.0
    l_out_tokens = long_.get("output_tokens") or 0
    l_finish = long_.get("finish_reason")

    s_coherent = _has_sensible_english(short.get("preview", "") or "")
    l_coherent = _has_sensible_english(long_.get("preview", "") or "")

    # Borderline recheck: if the original short was empty or incoherent,
    # look at rechecks to characterize consistency.
    if recheck:
        ok_rechecks = [r for r in recheck if r.get("ok")]
        recheck_text_lens = [r.get("text_len", 0) for r in ok_rechecks]
        recheck_is_answer = [
            _is_actual_answer(r.get("preview", "") or "") for r in ok_rechecks
        ]
        n = len(ok_rechecks)
        if n == 0:
            return "broken", "all q3 retries failed", "bad"
        if all(t == 0 for t in recheck_text_lens):
            return (
                "broken",
                f"q3 retry x{n}: all empty (consistent reasoning-only behavior)",
                "bad",
            )
        n_answers = sum(1 for t, a in zip(recheck_text_lens, recheck_is_answer) if t > 0 and a)
        if n_answers < n:
            return (
                "flaky",
                f"q3 retry x{n}: only {n_answers}/{n} produced actual answers (rest = reasoning preamble/gibberish)",
                "bad",
            )
        return (
            "usable",
            f"q3 retry x{n}: all produced actual answers (initial was anomaly)",
            "ok",
        )

    if s_text == 0:
        return (
            "broken",
            f"short produced 0 visible chars ({short.get('output_tokens', '?')} tokens reasoning, no answer)",
            "bad",
        )

    if not s_coherent:
        return "broken", "short output is gibberish / not English-coherent", "bad"

    if l_finish == "length" and l_out_tokens >= 1024 and l_text < 200:
        return "slow", f"long hit max_tokens ({l_out_tokens}) — heavy reasoning", "warn"

    if not l_coherent and l_text > 0:
        return "slow", "long output is gibberish / incoherent", "warn"

    if l_total > 60:
        return "slow", f"long took {l_total:.1f}s", "warn"
    if l_total > 20:
        return "slow", f"long took {l_total:.1f}s (over 20s)", "warn"

    return "usable", "responds coherently, reasonable latency", "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=str(DEFAULT_PATH))
    args = ap.parse_args()
    p = Path(args.path)
    data = json.loads(p.read_text())

    print("=" * 120)
    print(f"NVIDIA NIM ROUTE VIABILITY REPORT — cache-busted probes (nonce {data['nonce']})")
    print("=" * 120)
    print(
        f"{'alias':28} {'verdict':9} "
        f"{'short TTFT/total':>20} {'out/chars':>11} "
        f"{'long TTFT/total':>20} {'out/chars':>11} "
        f"{'vis tok/s':>9}  note"
    )
    print("-" * 120)

    by_v = {"usable": [], "slow": [], "broken": [], "flaky": []}
    for row in data["rows"]:
        alias = row["alias"]
        s = row["short"]
        l_ = row["long"]
        recheck = row.get("borderline_recheck")
        verdict, note, _ = _classify(s, l_, recheck=recheck)
        l_total = l_.get("total_s") or 0.0
        vis_tps = (l_.get("text_len", 0) / 4) / l_total if l_total > 0 else 0.0
        s_out = s.get("output_tokens", "-")
        s_chars = s.get("text_len", 0)
        l_out = l_.get("output_tokens", "-")
        l_chars = l_.get("text_len", 0)
        s_str = f"{s.get('ttft_s', '-'):.2f}/{s.get('total_s', '-'):.2f}s"
        l_str = f"{l_.get('ttft_s', '-'):.2f}/{l_total:.2f}s"
        print(
            f"{alias:28} {verdict:9} "
            f"{s_str:>20} {f'{s_out}/{s_chars}':>11} "
            f"{l_str:>20} {f'{l_out}/{l_chars}':>11} "
            f"{vis_tps:>9.1f}  {note}"
        )
        by_v[verdict].append((alias, note))

    print("-" * 120)

    counts = {v: len(by_v[v]) for v in ("usable", "slow", "broken", "flaky")}
    print(f"Verdicts: {counts}")

    print("\nFindings:")
    for v in ("usable", "slow", "flaky", "broken"):
        if by_v[v]:
            print(f"\n  {v.upper()} ({len(by_v[v])}):")
            for alias, note in by_v[v]:
                print(f"    - {alias}: {note}")

    print("\nNotes on methodology:")
    print("  - Cache-busted probes: a unique nonce was appended to each prompt to")
    print("    bypass the proxy's Redis cache (which masked real performance in")
    print("    the initial uncached run — kimi-2.6 was initially misclassified as")
    print("    producing gibberish; the cache had been serving stale bad output).")
    print("  - Coherence is judged on visible text only (text_len), since some")
    print("    reasoning models (nemotron-nano-omni, qwen3.5-397b) emit large")
    print("    reasoning blocks that inflate 'usage.completion_tokens' without")
    print("    contributing to the user-visible response.")
    print("  - Verdict thresholds: usable = coherent + <20s on the long prompt;")
    print("    slow = coherent but >20s or hit max_tokens; broken = 0 visible")
    print("    chars or incoherent.")
    print("  - Source: logs/_nim-viability/cachebust.json (raw per-call data)")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())