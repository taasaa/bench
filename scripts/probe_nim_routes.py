#!/usr/bin/env python3
"""Direct proxy probe for NVIDIA NIM routes.

Two-stage cache-busted probe:
  Stage 1 (main): short + long prompts with unique nonce — viability + timing
  Stage 2 (borderline): q3-prompt retry confirmation for models that looked
                         broken/unusual in stage 1

Writes logs/_nim-viability/cachebust.json (raw) + per-alias JSON. Run
report_viability.py to print the summary table.

Use case: assessing NIM route viability without committing to multi-hour
full eval. Source prompts from real bench task dataset.json inputs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROXY = "http://smallbox:4000/v1"
NIM_ALIASES = [
    "kimi-2.6",
    "minimax-m3",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "nemotron-ultra-550b",
    "mistral-large-3-675b",
    "qwen3.5-397b",
    "glm-5.1",
    "nemotron-nano-omni-30b",
    "diffusiongemma-26b-a4b",
]

SHORT_PROMPT = (
    "How do you create a Python virtual environment using `uv`? "
    "Answer in exactly 2 steps. Do not explain what virtual environments are, "
    "do not explain why you should use them, do not mention alternatives. "
    "Just the 2 steps."
)
LONG_PROMPT = (
    "Implement a Python class called `Cache` with exactly two methods: "
    "`get(key)` and `set(key, value)`. Use a simple internal dictionary for storage.\n\n"
    "Important constraints:\n"
    "- The class must be named `Cache`\n"
    "- It must have exactly `get` and `set` methods — nothing else\n"
    "- Do NOT add delete, clear, or any cleanup methods\n"
    "- Do NOT add TTL or expiry logic of any kind\n"
    "- Do NOT add any private helper methods\n"
    "- Do NOT add type hints\n"
    "- Do NOT add docstrings\n"
    "- Do NOT add a `__repr__` or `__str__`\n"
    "- The class must work correctly for basic get/set use"
)

MAX_TOKENS_SHORT = 256
MAX_TOKENS_LONG = 1024
PER_CALL_TIMEOUT_S = 120.0
RETRY_BACKOFF_S = [2, 5, 10]

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

BORDERLINE_RECHECK_ALIASES = {"qwen3.5-397b", "nemotron-nano-omni-30b", "kimi-2.6"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_api_key() -> str:
    """Load OPENAI_API_KEY from .env (override shell env)."""
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path, override=True)
        except ImportError:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "OPENAI_API_KEY":
                    os.environ[k.strip()] = v.strip()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(f"ERROR: OPENAI_API_KEY not in env or .env at {env_path}")
    return api_key


def _has_sensible_english(text: str) -> bool:
    """Loose coherence check used to decide if a model response is gibberish."""
    if not text:
        return False
    tokens = re.findall(r"[A-Za-z]{3,}", text)
    if not tokens:
        return False
    markers = {
        "the", "and", "with", "class", "def", "init", "return", "venv",
        "activate", "python", "step", "source", "directory", "install",
        "create", "data", "store", "self", "method", "keys", "value",
    }
    lower = {t.lower() for t in tokens}
    return bool(markers & lower) or (
        sum(1 for t in lower if t in markers) / max(len(lower), 1) > 0.2
    )


def _classify_exception(exc: BaseException) -> tuple[int | None, str]:
    status = getattr(exc, "status_code", None)
    if status is None:
        msg = str(exc).lower()
        if "timeout" in msg or "timed out" in msg:
            return None, "timeout"
        if "connection" in msg:
            return None, "connection_error"
        return None, "error"
    if status in RETRYABLE_STATUS:
        return status, f"http_{status}"
    return status, f"http_{status}"


def _stream_chat(
    client: Any,
    model: str,
    prompt: str,
    max_tokens: int,
    timeout_s: float,
) -> dict[str, Any]:
    t_start = time.monotonic()
    t_first_token: float | None = None
    chunks: list[str] = []
    usage_input: int | None = None
    usage_output: int | None = None
    finish_reason: str | None = None
    response_id: str | None = None

    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        stream=True,
        stream_options={"include_usage": True},  # type: ignore[arg-type]
        timeout=timeout_s,
    )

    for chunk in stream:
        if t_first_token is None:
            t_first_token = time.monotonic()
        if chunk.id and not response_id:
            response_id = chunk.id
        for choice in getattr(chunk, "choices", []) or []:
            delta = getattr(choice, "delta", None)
            if delta and getattr(delta, "content", None):
                chunks.append(delta.content)
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason
        u = getattr(chunk, "usage", None)
        if u is not None:
            usage_input = getattr(u, "prompt_tokens", None) or usage_input
            usage_output = getattr(u, "completion_tokens", None) or usage_output

    t_end = time.monotonic()
    text = "".join(chunks)
    out_tokens = usage_output if usage_output is not None else len(chunks)

    total_s = t_end - t_start
    ttft_s = (t_first_token - t_start) if t_first_token is not None else None
    gen_s = (t_end - t_first_token) if t_first_token is not None else total_s
    tok_per_s = (out_tokens / gen_s) if gen_s > 0 else None

    return {
        "ok": True,
        "response_id": response_id,
        "finish_reason": finish_reason,
        "ttft_s": round(ttft_s, 3) if ttft_s is not None else None,
        "total_s": round(total_s, 3),
        "gen_s": round(gen_s, 3) if t_first_token is not None else None,
        "input_tokens": usage_input,
        "output_tokens": out_tokens,
        "tok_per_s": round(tok_per_s, 2) if tok_per_s is not None else None,
        "preview": text[:200].replace("\n", " "),
        "text_len": len(text),
    }


def probe_one(
    client: Any,
    alias: str,
    prompt: str,
    max_tokens: int,
    retries: int,
) -> dict[str, Any]:
    """Probe (alias, prompt) with retries on 429/5xx/timeout."""
    last_exc: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = []
    for attempt_idx in range(retries + 1):
        try:
            res = _stream_chat(client, alias, prompt, max_tokens, PER_CALL_TIMEOUT_S)
            res["attempts"] = attempt_idx + 1
            res["attempt_log"] = attempts
            return res
        except Exception as exc:  # noqa: BLE001
            status, category = _classify_exception(exc)
            attempt_entry = {
                "attempt": attempt_idx + 1,
                "status": status,
                "category": category,
                "error": f"{type(exc).__name__}: {exc}",
            }
            attempts.append(attempt_entry)
            last_exc = attempt_entry
            retryable = status in RETRYABLE_STATUS or category in ("timeout", "connection_error")
            if not retryable or attempt_idx >= retries:
                return {
                    "ok": False,
                    "attempts": attempt_idx + 1,
                    "attempt_log": attempts,
                    "final_status": status,
                    "final_category": category,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            backoff = RETRY_BACKOFF_S[min(attempt_idx, len(RETRY_BACKOFF_S) - 1)]
            print(f"    attempt {attempt_idx + 1} {category} (status={status}); retry in {backoff}s", flush=True)
            time.sleep(backoff)
    return {
        "ok": False,
        "attempts": len(attempts),
        "attempt_log": attempts,
        "final_status": last_exc["status"] if last_exc else None,
        "final_category": last_exc["category"] if last_exc else "error",
        "error": last_exc["error"] if last_exc else "unknown",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aliases", nargs="+", default=None)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "logs" / "_nim-viability"))
    ap.add_argument("--proxy", default=DEFAULT_PROXY)
    ap.add_argument("--no-stage2", action="store_true", help="Skip borderline recheck (stage 2)")
    args = ap.parse_args()

    aliases = args.aliases or NIM_ALIASES
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    api_key = _load_api_key()

    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("ERROR: openai SDK not in .venv")

    client = OpenAI(base_url=args.proxy, api_key=api_key)
    nonce = uuid.uuid4().hex[:8]
    short_busted = SHORT_PROMPT + f" [nonce:{nonce}]"
    long_busted = LONG_PROMPT + f" [nonce:{nonce}]"

    print(f"Probing {len(aliases)} NIM route(s) via {args.proxy}")
    print(f"Output: {out_dir}")
    print(f"Cache-bust nonce: {nonce}")
    print(f"Retries: {args.retries} on 429/5xx/timeout")
    print()

    rows: list[dict[str, Any]] = []
    for alias in aliases:
        print(f"[{alias}] short ...", end=" ", flush=True)
        s = probe_one(client, alias, short_busted, MAX_TOKENS_SHORT, args.retries)
        print(f"ok={s.get('ok')} ttft={s.get('ttft_s')}s total={s.get('total_s')}s text_len={s.get('text_len')}")

        print(f"[{alias}] long  ...", end=" ", flush=True)
        l = probe_one(client, alias, long_busted, MAX_TOKENS_LONG, args.retries)
        print(f"ok={l.get('ok')} ttft={l.get('ttft_s')}s total={l.get('total_s')}s text_len={l.get('text_len')}")

        row: dict[str, Any] = {"alias": alias, "short": s, "long": l}

        # Stage 2: recheck models whose short response was empty or incoherent
        s_coherent = _has_sensible_english(s.get("preview", "") or "")
        if (
            not args.no_stage2
            and alias in BORDERLINE_RECHECK_ALIASES
            and s.get("ok")
            and (s.get("text_len", 0) == 0 or not s_coherent)
        ):
            print(f"[{alias}] borderline recheck (3x fresh q3) ...", flush=True)
            rechecks = []
            for i in range(3):
                p = SHORT_PROMPT + f" [recheck:{nonce}-{i}]"
                rr = probe_one(client, alias, p, MAX_TOKENS_SHORT, args.retries)
                rechecks.append(rr)
                print(
                    f"  recheck {i + 1}: ok={rr.get('ok')} total={rr.get('total_s')}s text_len={rr.get('text_len')} out_tok={rr.get('output_tokens')}"
                )
            row["borderline_recheck"] = rechecks
            print()

        rows.append(row)
        print()

    # Persist aggregate
    aggregate_path = out_dir / "cachebust.json"
    aggregate_path.write_text(json.dumps({"nonce": nonce, "rows": rows}, indent=2))

    # Per-alias JSON
    for row in rows:
        per = out_dir / f"{row['alias'].replace('/', '_')}.json"
        per.write_text(json.dumps(row, indent=2))

    print(f"Raw JSON: {aggregate_path}")
    print(f"Per-alias JSON: {out_dir}/<alias>.json")
    print()
    print("Next: .venv/bin/python scripts/report_viability.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())