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
from bench_cli.pricing.model_aliases import MODEL_ALIAS_MAP

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_RESULTS_DIR = _PROJECT_ROOT / "results"
_LOGS_DIR = _PROJECT_ROOT / "logs"

# Regex to extract task name from eval filename:
# 2026-04-16T23-13-32-00-00_task-name_ID.eval
_FNAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T[\d-]+)_(.+)_([A-Za-z0-9]+)\.eval")


def _card_key(model: str, agent: str | None = None, agent_mode: str | None = None) -> str:
    """Build composite key for card grouping: bare model or model__agent__mode."""
    if agent:
        return f"{model}__{agent}__{agent_mode}"
    return model


def _build_pillar_map() -> dict[str, str]:
    """Scan tasks/ directory to build task_name -> pillar mapping."""
    from bench_cli.inspect.core import _load_pillar_map

    return _load_pillar_map()


def _slug_from_alias(bench_alias: str) -> str:
    """Convert bench alias to a filename slug using OpenRouter ID.

    Falls back to LiteLLM config model name for local models.
    """
    or_id = resolve_openrouter_id(bench_alias)
    if or_id:
        return or_id.replace("/", "-")
    # Fallback: use MODEL_ALIAS_MAP or the alias itself
    mapped = MODEL_ALIAS_MAP.get(bench_alias)
    if mapped:
        return mapped.replace("/", "-")
    # Last resort: strip openai/ prefix
    return bench_alias.replace("openai/", "").replace("/", "-")


def _real_model_name(bench_alias: str) -> str:
    """Get a human-readable model name from bench alias."""
    or_id = resolve_openrouter_id(bench_alias)
    if or_id:
        # Capitalize provider and model parts nicely
        return or_id
    mapped = MODEL_ALIAS_MAP.get(bench_alias)
    if mapped:
        return mapped
    return bench_alias.replace("openai/", "")


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
    """Format a ratio value, handling NaN and None."""
    if val is None:
        return "--"
    if math.isnan(val):
        return "--"
    if math.isinf(val):
        return "FREE"
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
        n_samples = 0
        scores_by_scorer: dict[str, list[float]] = defaultdict(list)

        if log.samples:
            for sample in log.samples:
                n_samples += 1
                if hasattr(sample, "model_usage") and sample.model_usage:
                    for usage in sample.model_usage.values():
                        total_input += getattr(usage, "input_tokens", 0)
                        total_output += getattr(usage, "output_tokens", 0)
                if hasattr(sample, "scores") and sample.scores:
                    for scorer_name, score in sample.scores.items():
                        val = score.value if hasattr(score, "value") else score
                        if isinstance(val, (int, float)):
                            scores_by_scorer[scorer_name].append(val)

        avg_scores: dict[str, float] = {}
        for k, vals in scores_by_scorer.items():
            numeric = [
                v
                for v in vals
                if isinstance(v, (int, float)) and not math.isnan(v) and not math.isinf(v)
            ]
            if numeric:
                avg_scores[k] = round(sum(numeric) / len(numeric), 4)

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
            }
        model_data[card_key]["dates"].append(date_str)
        model_data[card_key]["total_input"] += total_input
        model_data[card_key]["total_output"] += total_output

    return model_data


def _compute_pillar_scores(tasks: dict[str, dict]) -> dict[str, float]:
    """Compute 4-pillar averages across tasks."""
    correct_scores = []
    tok_ratios = []
    time_ratios = []
    price_ratios = []

    for task_data in tasks.values():
        s = task_data["scores"]
        correct_scores.extend(s[k] for k in ["verify_sh", "llm_judge"] if k in s)
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
        for k in ["verify_sh", "llm_judge"]:
            if k in s:
                task_scores.append((task_name, s[k], pillar_map.get(task_name, "?")))
                break
    return task_scores


def _generate_summary(
    model_name: str,
    pillars: dict[str, float],
    task_scores: list[tuple[str, float, str]],
    bench_alias: str,
) -> str:
    """Generate a mechanical summary of model performance."""

    task_scores.sort(key=lambda x: x[1], reverse=True)
    top = task_scores[:5]
    bottom = task_scores[-5:]

    correct = pillars["correctness"]
    tok = pillars["token_ratio"]
    time_r = pillars["time_ratio"]
    price_r = pillars["price_ratio"]

    free = is_managed_model(bench_alias)

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
    if free:
        lines.append(
            "This is a **free model** running locally, making it cost-optimal for any use case."
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


def _get_model_metadata(bench_alias: str) -> dict:
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
        if lookup_key in litellm_map:
            litellm_path = Path.home() / "dev" / "litellm" / "config.yaml"
            if litellm_path.is_file():
                with open(litellm_path) as f:
                    config = yaml.safe_load(f)
                for entry in config.get("model_list", []):
                    if entry.get("model_name", "").lower() == lookup_key:
                        ctx_window = entry.get("model_info", {}).get("max_input_tokens")
                        break
    except Exception:
        pass

    # Pricing
    input_price = 0.0
    output_price = 0.0
    has_price = False
    try:
        or_id = resolve_openrouter_id(bench_alias)
        if or_id:
            from bench_cli.pricing.price_cache import OpenRouterCache

            cache = OpenRouterCache()
            price_info = cache.get_price(or_id)
            input_price = price_info.input_price
            output_price = price_info.output_price
            has_price = True
    except Exception:
        pass

    return {
        "provider": provider,
        "hosting": hosting,
        "ctx_window": ctx_window,
        "input_price": input_price,
        "output_price": output_price,
        "has_price": has_price,
        "free": is_managed_model(bench_alias),
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
    summary = _generate_summary(real_name, pillars, task_scores, bench_alias)

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
    if meta["free"]:
        lines.append("| **Pricing** | $0.00 (free, local) |")
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
    cost_display = "FREE" if meta["free"] else _format_ratio(pillars["price_ratio"])
    cost_rating = "excellent" if meta["free"] else _rating(pillars["price_ratio"])
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

        # Determine scorer type
        scorer = "--"
        score_val = "--"
        if "verify_sh" in s:
            scorer = "verify_sh"
            score_val = f"{s['verify_sh']:.3f}"
        elif "llm_judge" in s:
            scorer = "llm_judge"
            score_val = f"{s['llm_judge']:.3f}"

        tok = _format_ratio(s.get("token_ratio_scorer"))
        time_r = _format_ratio(s.get("time_ratio_scorer"))
        price = _format_ratio(s.get("price_ratio_scorer"))
        if meta["free"] and "price_ratio_scorer" in s:
            price = "FREE"

        lines.append(
            f"| {task_name} | {pillar} | {scorer} | {score_val} | {tok} | {time_r} | {price} |"
        )

    lines.append("")

    # Strengths & Weaknesses (reusing task_scores from _extract_task_scores)
    ranked_scores = sorted(task_scores, key=lambda x: x[1], reverse=True)

    lines.append("## Strengths & Weaknesses")
    lines.append("")
    lines.append("### Top 5 Tasks (by correctness)")
    for name, score, _ in ranked_scores[:5]:
        lines.append(f"1. **{name}** — {score:.3f}")
    lines.append("")
    lines.append("### Bottom 5 Tasks (by correctness)")
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
    model_data = _load_model_data(log_dir, model_filter=bench_alias)
    card_key = _card_key(bench_alias, agent, agent_mode)
    if card_key not in model_data:
        return None
    return generate_card(bench_alias, model_data[card_key], log_dir)
