"""CLI commands for price cache management: refresh and list."""

from __future__ import annotations

import click

from bench_cli.pricing.model_aliases import MODEL_ALIAS_MAP, PriceInfo, resolve_alias
from bench_cli.pricing.price_cache import KiloCodeCache

# Single cache read — reused across the list command.
_cache = KiloCodeCache()
_all_prices: dict[str, PriceInfo] = {}  # lazy, populated only in list_prices()


@click.group("prices")
def prices() -> None:
    """Manage model price cache for cost scoring."""
    pass


@prices.command("refresh")
def refresh() -> None:
    """Fetch fresh prices from KiloCode API and update the local cache."""
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

    click.echo(f"{'BENCH ALIAS':<35} {'KILOCODE ID':<40} {'INPUT $/M':>10} {'OUTPUT $/M':>11} {'FREE':>6}")
    click.echo("-" * 105)

    any_found = False
    for bench_alias in sorted(MODEL_ALIAS_MAP):
        kilo_id = resolve_alias(bench_alias)
        if kilo_id is None:
            continue
        info = all_prices.get(kilo_id)
        if info is not None:
            free_str = "FREE" if info.is_free else ""
            click.echo(
                f"{bench_alias:<35} {kilo_id:<40} {info.input_price:>10.4f} {info.output_price:>11.4f} {free_str:>6}"
            )
            any_found = True
        else:
            click.echo(f"{bench_alias:<35} {kilo_id:<40} {'N/A':>10} {'N/A':>11} {'':>6}")
            any_found = True

    if not any_found:
        click.echo("No models to display.")
