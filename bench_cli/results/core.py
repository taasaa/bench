"""Core business logic for model card generation from eval logs.

Scans logs/*.eval files, groups by model, deduplicates to latest run per task,
and generates markdown model cards in results/ named by OpenRouter slug.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

import click

from bench_cli.pricing.litellm_config import is_managed_model, resolve_openrouter_id
from scorers.baseline_store import BaselineStore
from scorers.ratio_recompute import (
    recompute_price_ratio,
    recompute_time_ratio,
    recompute_token_ratio,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_RESULTS_DIR = _PROJECT_ROOT / "results"
_LOGS_DIR = _PROJECT_ROOT / "logs"

# Shared BaselineStore for ratio recomputation in _load_model_data (W3a/W3b).
# Cheap to construct (reads disk lazily per task on demand; store is currently
# empty so load() short-circuits at the is_file() check).
_BASELINE_STORE = BaselineStore()

# Regex to extract task name from eval filename:
# 2026-04-16T23-13-32-00-00_task-name_ID.eval
_FNAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T[\d-]+)_(.+)_([A-Za-z0-9]+)\.eval")


def _card_key(model: str, agent: str | None = None, agent_mode: str | None = None) -> str:
    """Build composite key for card grouping: bare model or model__agent__mode."""
    if agent:
        return f"{model}__{agent}__{agent_mode}"
    return model


# Router-tier meta-monikers (SB Operating Rules): never emit cards for these.
_ROUTER_MONIKERS = {"default", "thinking", "heavy", "background", "smart-router"}


def is_moniker_alias(bench_alias: str) -> bool:
    """True if alias is a router-tier meta-moniker (default/thinking/heavy/...).

    Checks the BARE name (first segment stripped) so OR ids like
    'minimaxai/minimax-m3' (bare 'minimax-m3') are correctly False. Also handles
    agent-eval composite keys 'model__agent__mode' by checking the model segment
    (OpenRouter ids never contain '__'), so agent-eval cards of monikers like
    'openai/default__claude__docker' are correctly excluded.
    """
    # Agent-eval composite key: model is everything before the first '__'
    # (OR ids use '-', never '__').
    model_part = bench_alias.split("__", 1)[0] if "__" in bench_alias else bench_alias
    bare = model_part.split("/", 1)[1] if "/" in model_part else model_part
    return bare.lower() in _ROUTER_MONIKERS



def _build_pillar_map() -> dict[str, str]:
    """Scan tasks/ directory to build task_name -> pillar mapping."""
    from bench_cli.inspect.core import _load_pillar_map

    return _load_pillar_map()


def _slug_from_alias(bench_alias: str) -> str:
    """Deterministic card filename slug from the recorded name.

    Slug = the recorded full name with '/' -> '-'. The recorded name is the
    OpenRouter id (e.g. 'minimaxai/minimax-m3') or an --as value; either way
    we slug the whole string. NEVER calls resolve_openrouter_id.

    For agent-eval composite keys (model__agent__mode), strip the agent suffix
    before slugging to avoid double-suffix in filenames.
    """
    # Strip agent suffix if present (model__agent__mode -> model)
    model_part = bench_alias.split("__", 1)[0] if "__" in bench_alias else bench_alias
    return model_part.replace("/", "-")


def _real_model_name(bench_alias: str) -> str:
    """Deterministic human-readable model name = the recorded full name.

    Mirrors _slug_from_alias's source so name and slug always agree. The
    recorded OR id already carries the provider; display it in full (the
    compare table strips to bare via bare_model_name elsewhere).

    For agent-eval composite keys (model__agent__mode), strip the agent suffix
    to avoid showing agent info in the model name (it's shown separately).
    """
    # Strip agent suffix if present (model__agent__mode -> model)
    model_part = bench_alias.split("__", 1)[0] if "__" in bench_alias else bench_alias
    return model_part


def _rating(score: float) -> str:
    """Convert a score/ratio to a rating label."""
    if score >= 0.90:
        return "excellent"
    if score >= 0.75:
        return "good"
    if score >= 0.60:
        return "fair"
    return "weak"


def _format_ratio(val: float | None) -> str:
    """Format a ratio value, handling NaN, None, and inf.

    Returns "--" for any invalid (NaN/None/inf) value. The literal "FREE" is
    reserved for managed/local models with no market price, and is rendered
    by the display layer using the separate `meta["free"]` flag, NOT here.
    """
    if val is None or math.isnan(val) or math.isinf(val):
        return "--"
    return f"{val:.3f}"


def _load_model_data(
    log_dir: Path | None = None, model_filter: str | None = None
) -> dict[str, dict]:
    """Scan eval logs and return per-card data with latest-run dedup.

    Args:
        model_filter: If set, only read files for this bench alias (e.g. "openai/qwen-local").

    Returns: {card_key: {tasks: {task_name: {...}}, agent, agent_mode, ...}}
             card_key is bare model alias for model evals, "model__agent__mode" for agent evals.
    """
    from inspect_ai.log import read_eval_log

    log_dir = log_dir or _LOGS_DIR
    model_data: dict[str, dict] = {}

    for eval_file in sorted(log_dir.glob("*.eval")):
        match = _FNAME_RE.search(eval_file.name)
        if not match:
            continue
        date_str = match.group(1)[:10]
        task_name = match.group(2)

        try:
            log = read_eval_log(str(eval_file))
        except Exception:
            continue

        # Skip non-success logs (parity with compare/core.py): started/error
        # logs are abandoned or partial runs with no valid scores, and including
        # them pollutes pillar averages (e.g. killed 0-sample runs -> corr 0.000).
        if getattr(log, "status", None) != "success":
            continue

        model = log.eval.model if log.eval else "unknown"

        # Early skip if filtering for a specific model
        if model_filter and model != model_filter:
            continue

        # Extract agent info from sample metadata (injected at eval time)
        agent = None
        agent_mode = None
        if log.samples:
            meta = log.samples[0].metadata
            if meta and isinstance(meta, dict):
                agent = meta.get("bench_agent")
                agent_mode = meta.get("bench_agent_mode")

        # Composite key: bare model for model evals, model__agent__mode for agent evals
        card_key = _card_key(model, agent, agent_mode)

        total_input = 0
        total_output = 0
        total_tokens_sum = 0  # sum over samples of per-sample total_tokens (token-ratio recompute)
        total_working_time = 0.0  # sum over samples of working_time (time-ratio recompute)
        n_samples = 0
        scores_by_scorer: dict[str, list[float]] = defaultdict(list)
        seen_scorers: set[str] = set()  # scorer presence (drives recompute), value-agnostic
        tier_breakdown: dict[str, dict] | None = None
        # Raw per-sample actual_cost_usd from price_ratio_scorer metadata, used to
        # recompute the cost ratio against the LIVE reference (the baked-in score
        # value goes stale after a cost re-baseline like m2.7 -> m3).
        cost_usd_samples: list[float | None] = []

        def _is_finite_number(v) -> bool:
            return isinstance(v, (int, float)) and not math.isnan(v) and not math.isinf(v)

        # Track per-sample model_usage so we can reconstruct cost for free-model
        # logs that have actual_cost_usd=0 baked in (pre-fix scorer behavior).
        per_sample_model_usage: list[dict] = []

        if log.samples:
            for sample in log.samples:
                n_samples += 1
                sample_total_tokens = 0
                if hasattr(sample, "model_usage") and sample.model_usage:
                    for usage in sample.model_usage.values():
                        total_input += getattr(usage, "input_tokens", 0)
                        total_output += getattr(usage, "output_tokens", 0)
                        sample_total_tokens += getattr(usage, "total_tokens", 0) or 0
                total_tokens_sum += sample_total_tokens
                total_working_time += getattr(sample, "working_time", 0.0) or 0.0
                # Keep per-sample model_usage for cost reconstruction below.
                per_sample_model_usage.append(
                    dict(sample.model_usage) if hasattr(sample, "model_usage") and sample.model_usage else {}
                )
                if hasattr(sample, "scores") and sample.scores:
                    for scorer_name, score in sample.scores.items():
                        seen_scorers.add(scorer_name)
                        val = score.value if hasattr(score, "value") else score
                        if _is_finite_number(val):
                            scores_by_scorer[scorer_name].append(val)
                    # Pull price_ratio_scorer metadata once per sample:
                    # tier_breakdown (card section) + raw actual_cost_usd
                    # (recompute ratio vs the LIVE reference).
                    pr_score = sample.scores.get("price_ratio_scorer")
                    md = getattr(pr_score, "metadata", None)
                    if isinstance(md, dict):
                        if tier_breakdown is None and (tb := md.get("tier_breakdown")):
                            tier_breakdown = tb
                        cost_usd_samples.append(md.get("actual_cost_usd"))
                    else:
                        cost_usd_samples.append(None)

        avg_scores = {
            k: round(sum(vals) / len(vals), 4)
            for k, vals in scores_by_scorer.items()
            if (filtered := [v for v in vals if _is_finite_number(v)])
            for vals in [filtered]
        }

        # Recompute the three ratio pillars from RAW usage/cost x the LIVE
        # reference (shared with bench_cli.compare), overwriting the baked-in
        # scorer values which go stale after a re-baseline (e.g. m2.7 -> m3).
        # Aggregation mirrors compare: token/time = ref / mean(actual) over
        # samples (ratio-of-means); cost = geometric mean of ref/cost over
        # positive samples. NaN is stored as-is (renders "--"); free models show
        # "FREE" via the separate meta["free"] flag in the display layer, not
        # the ratio value -- so results and compare agree on the raw ratio.
        if n_samples > 0:
            avg_tokens = total_tokens_sum / n_samples
            avg_time = total_working_time / n_samples
            if "token_ratio_scorer" in seen_scorers:
                avg_scores["token_ratio_scorer"] = round(
                    recompute_token_ratio(_BASELINE_STORE, task_name, avg_tokens), 4
                )
            if "time_ratio_scorer" in seen_scorers:
                avg_scores["time_ratio_scorer"] = round(
                    recompute_time_ratio(_BASELINE_STORE, task_name, avg_time), 4
                )
        if "price_ratio_scorer" in seen_scorers:
            # Reconstruct cost for samples where the baked-in value is 0/None
            # (typical for old free-model logs). Cost pillar must reflect
            # default paid-tier price, not $0. `model` is the recorded OR id
            # (e.g. "nvidia/nemotron-3-super-120b-a12b:free"); pass it as
            # `or_id` so the pricing lookup uses the LiteLLM reverse-key map.
            from bench_cli.pricing import reconstruct_cost_from_usage

            cost_usd_samples = [
                reconstruct_cost_from_usage(None, usage, cost, or_id=model)
                for usage, cost in zip(per_sample_model_usage, cost_usd_samples)
            ]
            avg_scores["price_ratio_scorer"] = round(
                recompute_price_ratio(_BASELINE_STORE, task_name, cost_usd_samples), 4
            )

        if card_key not in model_data:
            model_data[card_key] = {
                "tasks": {},
                "dates": [],
                "total_input": 0,
                "total_output": 0,
                "agent": agent,
                "agent_mode": agent_mode,
            }

        # Keep latest run per task
        if (
            task_name not in model_data[card_key]["tasks"]
            or date_str >= model_data[card_key]["tasks"][task_name]["date"]
        ):
            model_data[card_key]["tasks"][task_name] = {
                "date": date_str,
                "samples": n_samples,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "scores": avg_scores,
                "tier_breakdown": tier_breakdown,
            }
        model_data[card_key]["dates"].append(date_str)
        model_data[card_key]["total_input"] += total_input
        model_data[card_key]["total_output"] += total_output

    return model_data


# Scorers that contribute to the correctness pillar. A task's scores dict has
# exactly one of these (verify_sh for verify-only tasks, llm_judge for
# judge-only tasks, hybrid_scorer for tasks with both verify.sh and judge.md).
_CORRECTNESS_SCORERS = ("verify_sh", "llm_judge", "hybrid_scorer")


def _compute_pillar_scores(tasks: dict[str, dict]) -> dict[str, float]:
    """Compute 4-pillar averages across tasks."""
    correct_scores = []
    tok_ratios = []
    time_ratios = []
    price_ratios = []

    for task_data in tasks.values():
        s = task_data["scores"]
        correct_scores.extend(s[k] for k in _CORRECTNESS_SCORERS if k in s)
        if "token_ratio_scorer" in s:
            v = s["token_ratio_scorer"]
            if not math.isnan(v) and not math.isinf(v):
                tok_ratios.append(v)
        if "time_ratio_scorer" in s:
            v = s["time_ratio_scorer"]
            if not math.isnan(v) and not math.isinf(v):
                time_ratios.append(v)
        if "price_ratio_scorer" in s:
            v = s["price_ratio_scorer"]
            if not math.isnan(v) and not math.isinf(v):
                price_ratios.append(v)

    return {
        "correctness": round(sum(correct_scores) / len(correct_scores), 3) if correct_scores else 0,
        "token_ratio": round(sum(tok_ratios) / len(tok_ratios), 3) if tok_ratios else 0,
        "time_ratio": round(sum(time_ratios) / len(time_ratios), 3) if time_ratios else 0,
        "price_ratio": round(sum(price_ratios) / len(price_ratios), 3) if price_ratios else 0,
    }


def _extract_task_scores(tasks: dict[str, dict]) -> list[tuple[str, float, str]]:
    """Extract (task_name, correctness_score, pillar) tuples from tasks."""
    pillar_map = _build_pillar_map()
    task_scores = []
    for task_name, td in tasks.items():
        s = td["scores"]
        for k in _CORRECTNESS_SCORERS:
            if k in s:
                task_scores.append((task_name, s[k], pillar_map.get(task_name, "?")))
                break
    return task_scores


def _generate_summary(
    model_name: str,
    pillars: dict[str, float],
    task_scores: list[tuple[str, float, str]],
    bench_alias: str,
    free: bool = False,
    input_price: float = 0.0,
    output_price: float = 0.0,
) -> str:
    """Generate a mechanical summary of model performance.

    Args:
        free: True if the model is free (managed local OR $0/$0 via the price
            cache). When True, the cost section says "FREE" instead of showing
            a 0.00 ratio that would suggest the model is infinitely expensive.
        input_price: Real input price per million tokens (from paid variant for :free).
        output_price: Real output price per million tokens (from paid variant for :free).
    """

    task_scores.sort(key=lambda x: x[1], reverse=True)
    top = task_scores[:5]
    # Only show distinct "weakness" tasks when there are enough to split from
    # the top. With <= 5 tasks, top and bottom overlap so listing them as
    # "struggles with" the same tasks is noise.
    bottom = task_scores[-5:] if len(task_scores) > 5 else []

    correct = pillars["correctness"]
    tok = pillars["token_ratio"]
    time_r = pillars["time_ratio"]
    price_r = pillars["price_ratio"]

    # Build summary paragraphs
    lines = []
    lines.append(
        f"**{model_name}** achieves an overall correctness of **{correct:.0%}** "
        f"across {len(task_scores)} evaluation tasks."
    )

    # Correctness assessment
    if correct >= 0.85:
        lines.append(
            "This model demonstrates strong reliability across task categories, "
            "making it suitable for production use where accuracy is critical."
        )
    elif correct >= 0.75:
        lines.append(
            "Performance is solid for most coding tasks, though some edge cases "
            "in error handling and verification reveal room for improvement."
        )
    elif correct >= 0.60:
        lines.append(
            "Adequate for assisted coding workflows where human review catches errors, "
            "but not recommended for autonomous agent use without supervision."
        )
    else:
        lines.append(
            "This model struggles with complex multi-step reasoning and should be "
            "paired with strong verification layers in any production pipeline."
        )

    # Efficiency assessment
    if tok >= 1.0:
        lines.append(
            f"Token efficiency is {'strong' if tok >= 1.5 else 'reasonable'} "
            f"(ratio {tok:.2f}), producing concise responses. "
        )
    else:
        lines.append(
            f"Token efficiency is below benchmark (ratio {tok:.2f}), tending toward verbose output."
        )

    # Speed
    if time_r >= 1.0:
        lines.append(
            f"Latency is {'fast' if time_r >= 2.0 else 'competitive'} (ratio {time_r:.2f})."
        )
    else:
        lines.append(f"Latency is slower than benchmark (ratio {time_r:.2f}).")

    # Cost
    if free and (input_price > 0.0 or output_price > 0.0):
        # Free model with real prices from paid variant
        lines.append(
            f"This is a **currently free model** (normal price ${input_price:.4f}/M in, "
            f"${output_price:.4f}/M out), making it cost-optimal for any use case."
        )
    elif free:
        lines.append(
            "This is a **free model** ($0/M in, $0/M out), making it cost-optimal for any use case."
        )
    elif price_r >= 1.0:
        lines.append(
            f"Cost efficiency is strong (ratio {price_r:.2f}), "
            f"cheaper than the benchmark reference."
        )
    else:
        lines.append(f"Cost is above the benchmark reference (ratio {price_r:.2f}).")

    # Strengths
    if top:
        top_pillars = defaultdict(int)
        for _, _, pillar in top:
            top_pillars[pillar] += 1
        strong_area = max(top_pillars, key=top_pillars.get)
        lines.append(
            f"\n**Strengths:** Excels at {strong_area} tasks ({', '.join(t[0] for t in top[:3])})."
        )

    # Weaknesses
    if bottom:
        bottom_pillars = defaultdict(int)
        for _, _, pillar in bottom:
            bottom_pillars[pillar] += 1
        weak_area = max(bottom_pillars, key=bottom_pillars.get)
        lines.append(
            f"\n**Weaknesses:** Struggles with {weak_area} tasks"
            f" ({', '.join(t[0] for t in bottom[:3])})."
        )

    # Recommendation
    if correct >= 0.80 and (free or price_r >= 1.0):
        lines.append(
            "\n**Recommended for:** General coding assistance, code review, "
            "and automated workflows where cost-efficiency matters."
        )
    elif correct >= 0.75:
        lines.append(
            "\n**Recommended for:** Assisted coding, prototyping, and tasks "
            "where a human reviews the output."
        )
    elif free:
        lines.append(
            "\n**Recommended for:** Local development, experimentation, "
            "and cost-sensitive workflows where speed trumps accuracy."
        )
    else:
        lines.append(
            "\n**Recommended for:** Basic code generation with human oversight. "
            "Not suitable for autonomous agent use."
        )

    return "\n".join(lines)


def _get_model_metadata(bench_alias: str, litellm_path: Path | None = None) -> dict:
    """Collect model metadata for the card header."""
    litellm_map = {}
    try:
        from bench_cli.pricing.litellm_config import _load_litellm_alias_map

        litellm_map = _load_litellm_alias_map()
    except Exception:
        pass

    lookup_key = (
        bench_alias.replace("openai/", "").lower()
        if bench_alias.startswith("openai/")
        else bench_alias.lower()
    )
    litellm_model = litellm_map.get(lookup_key, "")

    # Determine provider/hosting
    if is_managed_model(bench_alias):
        if "lm_studio" in litellm_model:
            provider = "LM Studio (local)"
        elif "dashscope" in litellm_model:
            provider = "Alibaba Dashscope"
        elif "z.ai" in litellm_model:
            provider = "Zhipu AI"
        else:
            provider = "Local"
        hosting = "local"
    elif "nvidia" in bench_alias or "nvidia" in litellm_model:
        provider = "NVIDIA NIM"
        hosting = "NVIDIA NIM"
    elif "minimax" in litellm_model or "default" in bench_alias:
        provider = "MiniMax"
        hosting = "API"
    else:
        provider = "API"
        hosting = "API"

    # Context window from LiteLLM config (cached via _load_litellm_alias_map)
    ctx_window = None
    try:
        import yaml

        from bench_cli.pricing.litellm_config import _load_litellm_alias_map

        litellm_map = _load_litellm_alias_map()
        # Build reverse map: openrouter_id -> model_name
        reverse_map = {v: k for k, v in litellm_map.items()}
        # Resolve bench_alias to LiteLLM model_name
        # bench_alias might be an OpenRouter ID (e.g. "nvidia/nemotron-3-super-120b-a12b:free")
        # or a LiteLLM alias (e.g. "nemotron-super-120b-free")
        litellm_model_name = reverse_map.get(lookup_key, lookup_key)
        if litellm_model_name in litellm_map:
            litellm_path = litellm_path or (Path.home() / "dev" / "litellm" / "config.yaml")
            if litellm_path.is_file():
                with open(litellm_path) as f:
                    config = yaml.safe_load(f)
                for entry in config.get("model_list", []):
                    if entry.get("model_name", "").lower() == litellm_model_name.lower():
                        ctx_window = entry.get("model_info", {}).get("max_input_tokens")
                        break
    except Exception:
        pass

    # Pricing
    input_price = 0.0
    output_price = 0.0
    has_price = False
    try:
        from bench_cli.pricing.price_cache import OpenRouterCache

        cache = OpenRouterCache()
        or_id = (
            bench_alias
            if bench_alias in cache.get_all_prices()
            else resolve_openrouter_id(bench_alias)
        )
        # Track whether the model's OWN price (before any :free fallback) is $0/$0
        own_price_is_zero = False
        if or_id:
            price_info = cache.get_price(or_id)
            input_price = price_info.input_price
            output_price = price_info.output_price
            has_price = True
            # If model is :free ($0/$0), also fetch the paid variant's real price
            # so the card can display the actual market price with "(currently free)"
            # annotation. The paid variant is the same model id without ":free".
            if input_price == 0.0 and output_price == 0.0 and ":free" in or_id:
                own_price_is_zero = True
                paid_or_id = or_id.replace(":free", "")
                if paid_or_id in cache.get_all_prices():
                    paid_info = cache.get_price(paid_or_id)
                    if paid_info.input_price > 0.0 or paid_info.output_price > 0.0:
                        input_price = paid_info.input_price
                        output_price = paid_info.output_price
    except Exception:
        pass

    return {
        "provider": provider,
        "hosting": hosting,
        "ctx_window": ctx_window,
        "input_price": input_price,
        "output_price": output_price,
        "has_price": has_price,
        # "free" covers both :free access variants AND managed/local models —
        # drives the "(currently free)" annotation in the Overview Pricing line.
        # The cell display layer uses "managed_only" instead, so :free variants
        # with resolved paid-tier pricing show real ratios, not "FREE".
        "free": is_managed_model(bench_alias) or own_price_is_zero,
        "managed_only": is_managed_model(bench_alias),
        "litellm_model": litellm_model,
    }


def generate_card(bench_alias: str, model_data: dict, log_dir: Path | None = None) -> Path | None:
    """Generate a markdown model card for a single model.

    Returns path to the generated card, or None if no data.
    """
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _build_pillar_map()

    tasks = model_data.get("tasks", {})
    if not tasks:
        return None

    slug = _slug_from_alias(bench_alias)
    real_name = _real_model_name(bench_alias)
    agent = model_data.get("agent")
    agent_mode = model_data.get("agent_mode")

    filename = f"{slug}__{agent}__{agent_mode}.md" if agent else f"{slug}.md"
    out_path = _RESULTS_DIR / filename

    # Filter out smoke tasks
    eval_tasks = {
        k: v for k, v in tasks.items() if k not in ("smoke", "agent-smoke", "agent_smoke")
    }
    smoke_count = len(tasks) - len(eval_tasks)

    pillars = _compute_pillar_scores(eval_tasks)
    meta = _get_model_metadata(bench_alias)
    task_scores = _extract_task_scores(eval_tasks)
    summary = _generate_summary(
        real_name, pillars, task_scores, bench_alias,
        free=meta["free"],
        input_price=meta["input_price"],
        output_price=meta["output_price"],
    )

    total_samples = sum(t["samples"] for t in eval_tasks.values())
    total_in = sum(t["input_tokens"] for t in eval_tasks.values())
    total_out = sum(t["output_tokens"] for t in eval_tasks.values())
    dates = model_data.get("dates", [])
    date_range = f"{min(dates)} → {max(dates)}" if dates else "unknown"

    # Build card
    lines = []
    if agent:
        lines.append(f"# {real_name} + {agent} ({agent_mode})")
    else:
        lines.append(f"# {real_name}")
    lines.append("")
    status = "FREE" if meta["free"] else "paid"
    agent_info = f" | agent: {agent}/{agent_mode}" if agent else ""
    lines.append(
        f"> `{bench_alias}` | {meta['provider']} | {status}{agent_info} | Evaluated {date_range}"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(summary)
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Evaluated** | {date_range} |")
    task_note = f" ({smoke_count} smoke)" if smoke_count else ""
    lines.append(
        f"| **Tasks** | {len(eval_tasks)} eval tasks, {total_samples} samples{task_note} |"
    )
    lines.append(f"| **Provider** | {meta['provider']} |")
    lines.append(f"| **Hosting** | {meta['hosting']} |")
    ctx_str = f"{meta['ctx_window']:,}" if meta["ctx_window"] else "N/A"
    lines.append(f"| **Context Window** | {ctx_str} tokens |")
    if meta["free"] and meta["has_price"]:
        # Free model with real prices from paid variant: show real price + annotation
        lines.append(
            f"| **Pricing** | ${meta['input_price']:.4f}/M in, ${meta['output_price']:.4f}/M out (currently free) |"
        )
    elif meta["free"]:
        lines.append("| **Pricing** | $0.00 (free) |")
    elif meta["has_price"]:
        lines.append(
            f"| **Pricing** | ${meta['input_price']:.4f}/M in, ${meta['output_price']:.4f}/M out |"
        )
    else:
        lines.append("| **Pricing** | N/A |")
    lines.append(f"| **Status** | {status} |")
    lines.append("")

    # Overall scores
    lines.append("## Overall Scores")
    lines.append("")
    lines.append("| Pillar | Score | Rating |")
    lines.append("|--------|-------|--------|")
    lines.append(
        f"| **Correctness** | {pillars['correctness']:.3f} | {_rating(pillars['correctness'])} |"
    )
    lines.append(
        f"| **Token Efficiency** | {_format_ratio(pillars['token_ratio'])} "
        f"| {_rating(pillars['token_ratio'])} |"
    )
    lines.append(
        f"| **Latency** | {_format_ratio(pillars['time_ratio'])} "
        f"| {_rating(pillars['time_ratio'])} |"
    )
    cost_display = "FREE" if meta["managed_only"] else _format_ratio(pillars["price_ratio"])
    cost_rating = "excellent" if meta["managed_only"] else _rating(pillars["price_ratio"])
    lines.append(f"| **Cost Efficiency** | {cost_display} | {cost_rating} |")
    lines.append("")
    lines.append("> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60")
    lines.append("> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse")
    lines.append("")

    # Per-task results table
    lines.append("## Per-Task Results")
    lines.append("")
    lines.append("| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |")
    lines.append("|------|--------|--------|-------|-----------|------------|------------|")

    pillar_map = _build_pillar_map()
    for task_name in sorted(eval_tasks.keys()):
        td = eval_tasks[task_name]
        s = td["scores"]
        pillar = pillar_map.get(task_name, "?")

        # Determine scorer type (use the same scorer list as the pillars so
        # hybrid tasks render correctly in the per-task table).
        scorer = "--"
        score_val = "--"
        for k in _CORRECTNESS_SCORERS:
            if k in s:
                scorer = k
                score_val = f"{s[k]:.3f}"
                break

        tok = _format_ratio(s.get("token_ratio_scorer"))
        time_r = _format_ratio(s.get("time_ratio_scorer"))
        price = _format_ratio(s.get("price_ratio_scorer"))
        # Show "FREE" only for managed/local models with no market price. For
        # :free access variants with resolvable pricing, the scorer returns a
        # finite ratio at the paid-tier price — show that, not "FREE".
        if price == "--" and meta["managed_only"] and "price_ratio_scorer" in s:
            price = "FREE"

        lines.append(
            f"| {task_name} | {pillar} | {scorer} | {score_val} | {tok} | {time_r} | {price} |"
        )

    lines.append("")

    # Router Tier Usage (only if any task has tier_breakdown)
    has_tiers = any(td.get("tier_breakdown") for td in eval_tasks.values())
    if has_tiers:
        lines.append("## Router Tier Usage")
        lines.append("")

        # Aggregate
        tier_counts: dict[str, int] = {}
        tier_models: dict[str, str] = {}
        tier_costs: dict[str, float] = {}
        for task_name in sorted(eval_tasks):
            td = eval_tasks[task_name]
            tb = td.get("tier_breakdown")
            if not tb:
                continue
            for tier_name, tier_info in tb.items():
                tier_counts[tier_name] = tier_counts.get(tier_name, 0) + 1
                tier_costs[tier_name] = tier_costs.get(tier_name, 0.0) + tier_info.get("cost_usd", 0.0)
                or_id = tier_info.get("model", "")
                if or_id:
                    tier_models[tier_name] = or_id

        total_tier_tasks = sum(tier_counts.values())
        lines.append("| Tier | Model | Tasks | % | Cost |")
        lines.append("|------|-------|-------|---|------|")
        for tier_name in sorted(tier_counts):
            count = tier_counts[tier_name]
            pct = count / total_tier_tasks * 100 if total_tier_tasks else 0
            cost = tier_costs.get(tier_name, 0.0)
            or_id = tier_models.get(tier_name, "?")
            lines.append(f"| {tier_name} | {or_id} | {count} | {pct:.1f}% | ${cost:.6f} |")
        lines.append("")

        # Per-task mapping
        lines.append("### Per-Task Tier Assignment")
        lines.append("")
        lines.append("| Task | Tier | Model |")
        lines.append("|------|------|-------|")
        for task_name in sorted(eval_tasks):
            td = eval_tasks[task_name]
            tb = td.get("tier_breakdown")
            if not tb:
                continue
            for tier_name, tier_info in tb.items():
                or_id = tier_info.get("model", "?")
                lines.append(f"| {task_name} | {tier_name} | {or_id} |")
                break  # show primary tier only
        lines.append("")

    # Strengths & Weaknesses (reusing task_scores from _extract_task_scores)
    ranked_scores = sorted(task_scores, key=lambda x: x[1], reverse=True)
    n_tasks = len(ranked_scores)

    lines.append("## Strengths & Weaknesses")
    lines.append("")
    lines.append("### Top Tasks (by correctness)")
    for name, score, _ in ranked_scores[:5]:
        lines.append(f"1. **{name}** — {score:.3f}")
    lines.append("")
    # Skip the bottom list when there aren't enough tasks to split from the
    # top without overlap (otherwise it's just a duplicate of the strengths).
    if n_tasks > 5:
        lines.append("### Bottom Tasks (by correctness)")
        for name, score, _ in ranked_scores[-5:]:
            lines.append(f"1. **{name}** — {score:.3f}")
        lines.append("")

    # Token usage
    avg_in = total_in // max(total_samples, 1)
    avg_out = total_out // max(total_samples, 1)
    lines.append("## Token Usage")
    lines.append("")
    lines.append(f"- Total input: {total_in:,}")
    lines.append(f"- Total output: {total_out:,}")
    lines.append(f"- Avg input/sample: {avg_in:,}")
    lines.append(f"- Avg output/sample: {avg_out:,}")
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def generate_all_cards(log_dir: Path | None = None) -> list[Path]:
    """Generate model cards for all models with eval data.

    Returns list of paths to generated cards.
    """
    model_data = _load_model_data(log_dir)
    generated = []

    for bench_alias in sorted(model_data.keys()):
        if is_moniker_alias(bench_alias):
            continue
        try:
            path = generate_card(bench_alias, model_data[bench_alias], log_dir)
            if path:
                generated.append(path)
        except Exception as e:  # noqa: PERF203
            click.echo(f"Warning: Failed to generate card for {bench_alias}: {e}", err=True)

    return generated


def generate_card_for_model(
    bench_alias: str,
    log_dir: Path | None = None,
    agent: str | None = None,
    agent_mode: str | None = None,
) -> Path | None:
    """Generate/update a model card for a single model after eval run."""
    if is_moniker_alias(bench_alias):
        return None
    model_data = _load_model_data(log_dir, model_filter=bench_alias)
    card_key = _card_key(bench_alias, agent, agent_mode)
    if card_key not in model_data:
        return None
    return generate_card(bench_alias, model_data[card_key], log_dir)
