"""CLI commands for price cache management: refresh, list, add."""

from __future__ import annotations

from pathlib import Path

import click

from bench_cli.pricing.litellm_config import (
    _load_litellm_alias_map,
    get_router_tiers,
    is_managed_model,
    resolve_openrouter_id,
)
from bench_cli.pricing.price_cache import OpenRouterCache

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CACHE_FILE = _PROJECT_ROOT / "logs" / "pricing" / "openrouter-models.json"


def _get_cache(ctx: click.Context) -> OpenRouterCache:
    """Return cache from Click context (test-injected) or the default project cache."""
    obj = ctx.obj or {}
    if "cache" in obj:
        return obj["cache"]
    return OpenRouterCache(cache_path=_CACHE_FILE)


@click.group("prices")
@click.pass_context
def prices(ctx: click.Context) -> None:
    """Manage model price cache for cost scoring."""
    ctx.ensure_object(dict)


@prices.command("refresh")
@click.pass_context
def refresh(ctx: click.Context) -> None:
    """Fetch fresh prices from OpenRouter API and update the local cache."""
    cache = _get_cache(ctx)
    try:
        path = cache.fetch_and_cache_prices()
        click.echo(f"Price cache refreshed: {path}")
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from None


@prices.command("list")
@click.pass_context
def list_prices(ctx: click.Context) -> None:
    """Print cached prices for all models in the LiteLLM config.

    Shows all models from ~/dev/litellm/config.yaml, with their cached price
    if available, or N/A if not yet in cache.
    """
    cache = _get_cache(ctx)
    freshness = cache.get_freshness()

    if freshness:
        date_str = freshness[:10] if len(freshness) >= 10 else freshness
        click.echo(f"Price cache: {date_str}\n")
    else:
        click.echo("Price cache: not found (run 'bench prices refresh' first)\n")

    all_prices = cache.get_all_prices()
    litellm_map = _load_litellm_alias_map()

    # Build reverse map: OpenRouter ID → bench alias
    reverse: dict[str, str] = {}
    for bench_alias, or_id in litellm_map.items():
        if or_id not in reverse:
            reverse[or_id] = bench_alias

    click.echo(f"{'BENCH ALIAS':<35} {'OPENROUTER ID':<45} {'INPUT $/M':>10} {'OUTPUT $/M':>11}")
    click.echo("-" * 104)

    shown = 0
    for or_id, price_info in sorted(all_prices.items()):
        bench_alias = reverse.get(or_id, "(unknown)")
        click.echo(
            f"{bench_alias:<35} {or_id:<45} "
            f"{price_info.input_price * 1e6:>10.4f} "
            f"{price_info.output_price * 1e6:>11.4f}"
        )
        shown += 1

    if shown == 0:
        click.echo("No models in cache (run 'bench prices refresh' first).")
    else:
        click.echo(f"\n{shown} model(s) in cache.")


@prices.command("add")
@click.argument("alias")
@click.argument("input_price", type=float, default=None, required=False)
@click.argument("output_price", type=float, default=None, required=False)
@click.pass_context
def add_price(ctx: click.Context, alias: str, input_price: float | None, output_price: float | None) -> None:
    """Add or update a model's price in the cache.

    ALIAS is the bench LiteLLM alias (e.g. openai/nvidia-mistral-small4).
    INPUT_PRICE is USD per million input tokens.
    OUTPUT_PRICE is USD per million output tokens.

    The model must be in ~/dev/litellm/config.yaml.

    For router models (model_info.router: true), each tier is treated like a
    separate model: the exact same price-add flow is run per tier (lookup,
    prompt if missing, write if provided). No single shared price.

    Example (interactive):
        bench prices add openai/smart-router
    Then commands print for each missing tier:
        Error: '{missing_tier}' (mistralai/mistral-small-4-119b-2603) not cached.
        To add price: bench prices add openai/background <input_price> <output_price>
    Or (programmatic): provide prices per tier:
        bench prices add openai/background 0.50 2.00
        bench prices add openai/default 0.30 1.20
        bench prices add openai/heavy 2.00 8.00
        bench prices add openai/thinking 5.00 15.00
    """

    cache = _get_cache(ctx)
    all_prices = cache.get_all_prices()

    # Check if this is a router and get its tiers
    tiers = get_router_tiers(alias)

    if tiers is not None:
        # Router: apply the exact same flow PER TIER
        # Each tier goes through: resolve -> cache check -> prompt or block -> add
        errors: list[str] = []
        for tier in tiers:
            tier_alias = f"openai/{tier}"
            or_id = resolve_openrouter_id(tier_alias)

            if or_id is not None and or_id in all_prices:
                # Already cached — nothing to do
                continue

            # NOT IN CACHE — use the same error/prompt flow as single models
            if input_price is None or output_price is None:
                errors.append(f"{tier} ({or_id})")
            else:
                # Add with the provided price for this tier
                tier_or_id = or_id or tier_alias
                cache.add_price(tier_or_id, input_price, output_price)

        if errors:
            click.echo(
                "No price provided and router tier(s) missing cache:\n"
                + "\n".join(f"  • {e}" for e in errors)
                + "\n\n"
                "Add each tier: bench prices add openai/<tier> <input> <output>\n"
                "Or provide prices for desired tiers on this run:\n"
                f"  bench prices add {alias} <input> <output>",
                err=True,
            )
            raise SystemExit(1)

        click.echo(
            f"Router {alias}: processed {len(tiers)} tiers (prices added or unchanged) "
            "(same flow per tier)"
        )
        return

    # Non-router: original single-price flow (unchanged)
    if is_managed_model(alias):
        click.echo(
            f"Error: {alias} is a managed/local model — not in OpenRouter catalog.", err=True
        )
        raise SystemExit(1)

    or_id = resolve_openrouter_id(alias)

    if or_id is None:
        if alias.startswith("openai/") or alias.startswith("openrouter/"):
            cache.add_price(alias, input_price or 0.0, output_price or 0.0)
            click.echo(f"Added: {alias} (${input_price or 0.0:.4f}/M in, ${output_price or 0.0:.4f}/M out)")
            return

        click.echo(
            f"Error: '{alias}' is not in ~/dev/litellm/config.yaml.\n"
            f"  Only models in the LiteLLM config can have prices added.\n"
            f"  If this model should be configured there, add it first.",
            err=True,
        )
        raise SystemExit(1)

    # Exact same flow as before — ask interactively if price not provided, add to cache
    if input_price is None or output_price is None:
        from bench_cli.pricing import get_price

        try:
            price_info = get_price(or_id)
        except Exception:
            price_info = None

        click.echo(f"Price for {or_id} (resolved from {alias}):")
        ip = click.prompt("  Input price per 1M tokens ($)", type=float)
        op = click.prompt("  Output price per 1M tokens ($)", type=float)
        cache.add_price(or_id, ip, op)
        click.echo(f"Added: {alias} (${ip:.4f}/M in, ${op:.4f}/M out) → {or_id}")
        return

    cache.add_price(or_id, input_price, output_price)
    click.echo(f"Added: {alias} (${input_price:.4f}/M in, ${output_price:.4f}/M out) → {or_id}")
