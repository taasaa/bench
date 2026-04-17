"""CLI commands for price cache management: refresh, list, add."""

from __future__ import annotations

import click

from bench_cli.pricing.model_aliases import MODEL_ALIAS_MAP, resolve_alias
from bench_cli.pricing.price_cache import OpenRouterCache

# Single cache instance — reused across all commands.
_cache = OpenRouterCache()


@click.group("prices")
def prices() -> None:
    """Manage model price cache for cost scoring."""
    pass


@prices.command("refresh")
def refresh() -> None:
    """Fetch fresh prices from OpenRouter API and update the local cache."""
    try:
        path = _cache.fetch_and_cache_prices()
        click.echo(f"Price cache refreshed: {path}")
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@prices.command("list")
def list_prices() -> None:
    """Print cached prices for all known bench models."""
    freshness = _cache.get_freshness()

    if freshness:
        date_str = freshness[:10] if len(freshness) >= 10 else freshness
        click.echo(f"Price cache: {date_str}\n")
    else:
        click.echo("Price cache: not found (run 'bench prices refresh' first)\n")

    # Single file read for all models
    all_prices = _cache.get_all_prices()

    click.echo(f"{'BENCH ALIAS':<35} {'OPENROUTER ID':<40} {'INPUT $/M':>10} {'OUTPUT $/M':>11} {'FREE':>6}")
    click.echo("-" * 105)

    any_found = False
    for bench_alias in sorted(MODEL_ALIAS_MAP):
        or_id = resolve_alias(bench_alias)
        if or_id is None:
            continue
        info = all_prices.get(or_id)
        if info is not None:
            free_str = "FREE" if info.is_free else ""
            click.echo(
                f"{bench_alias:<35} {or_id:<40} {info.input_price:>10.4f} {info.output_price:>11.4f} {free_str:>6}"
            )
            any_found = True
        else:
            click.echo(f"{bench_alias:<35} {or_id:<40} {'N/A':>10} {'N/A':>11} {'':>6}")
            any_found = True

    if not any_found:
        click.echo("No models to display.")


@prices.command("add")
@click.argument("alias")
@click.argument("input_price", type=float)
@click.argument("output_price", type=float)
def add_price(alias: str, input_price: float, output_price: float) -> None:
    """Add or update a model's price in the cache.

    ALIAS is the bench LiteLLM alias (e.g. openai/nvidia-mistral-small4).
    INPUT_PRICE is USD per million input tokens.
    OUTPUT_PRICE is USD per million output tokens.

    Example: bench prices add openai/nvidia-mistral-small4 0.15 0.60
    """
    from bench_cli.pricing.litellm_config import is_managed_model, resolve_openrouter_id

    if is_managed_model(alias):
        click.echo(f"Error: {alias} is a managed/local model with no OpenRouter ID.", err=True)
        raise SystemExit(1)

    or_id = resolve_openrouter_id(alias)
    if or_id is None:
        or_id = resolve_alias(alias)
        if or_id is None:
            click.echo(f"Error: Unknown model alias '{alias}'. Cannot resolve to OpenRouter ID.", err=True)
            raise SystemExit(1)

    _cache.add_price(or_id, input_price, output_price)
    click.echo(f"Added: {alias} (${input_price:.4f}/M in, ${output_price:.4f}/M out) → {or_id}")
