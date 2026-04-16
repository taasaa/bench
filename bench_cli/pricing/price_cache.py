"""KiloCode API price cache with 3-day TTL.

Fetches model pricing from the KiloCode API and caches it locally as JSON.
The cache lives at bench/pricing/kilocode-models.json relative to the project root.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

from bench_cli.pricing.model_aliases import PriceInfo

# Project root: where pyproject.toml lives (parent of bench_cli/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CACHE_DIR = _PROJECT_ROOT / "logs" / "pricing"
_CACHE_FILE = _CACHE_DIR / "kilocode-models.json"

_KILOCODE_API_URL = "https://api.kilo.ai/api/openrouter/models"
_TTL_DAYS = 3


class CacheMiss(Exception):
    """Raised when price data is unavailable for a model."""


class KiloCodeCache:
    """Manages the local price cache backed by the KiloCode API."""

    def __init__(self, cache_path: Path | None = None) -> None:
        self._cache_path = cache_path or _CACHE_FILE

    @property
    def cache_path(self) -> Path:
        """Return the path to the cache file."""
        return self._cache_path

    def fetch_and_cache_prices(self) -> Path:
        """Fetch prices from KiloCode API and write to local cache.

        Returns:
            Path to the written cache file.

        Raises:
            RuntimeError: If KILOCODE_API_KEY is not set or the API call fails.
        """
        api_key = os.environ.get("KILOCODE_API_KEY", "").strip()
        if not api_key:
            print(
                "WARNING: KILOCODE_API_KEY not set in environment. "
                "Price cache cannot be refreshed. "
                "Add KILOCODE_API_KEY=<key> to your .env file.",
                file=sys.stderr,
            )
            raise RuntimeError("KILOCODE_API_KEY not set")

        request = urllib.request.Request(
            _KILOCODE_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(f"KiloCode API request failed: {exc}") from exc

        # Normalize API response into {model_id: price_dict} format.
        models: dict[str, dict[str, Any]] = {}
        # The API may return a list of model objects or a dict with a "data" key.
        model_list = raw if isinstance(raw, list) else raw.get("data", [])
        if isinstance(model_list, dict):
            # Some APIs return {id: details} directly
            model_list = [
                {"id": mid, **details} for mid, details in model_list.items()
            ]

        for entry in model_list:
            if not isinstance(entry, dict):
                continue
            model_id = entry.get("id") or entry.get("model", "")
            if not model_id:
                continue
            # Extract pricing — KiloCode/OpenRouter format uses nested pricing dict
            pricing = entry.get("pricing", entry)
            input_price = _safe_float(pricing.get("prompt", pricing.get("input", 0)))
            output_price = _safe_float(pricing.get("completion", pricing.get("output", 0)))
            context = entry.get("context_length") or entry.get("context_window")
            context = int(context) if context is not None else None

            models[model_id] = {
                "input": input_price,
                "output": output_price,
                "context": context,
            }

        cache_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "models": models,
        }

        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_cache(cache_data)
        return self._cache_path

    def get_price(self, kilo_model_id: str) -> PriceInfo:
        """Read cached price for a KiloCode model ID.

        Args:
            kilo_model_id: KiloCode model identifier (e.g. "qwen/qwen-local").

        Returns:
            PriceInfo with pricing data.

        Raises:
            CacheMiss: If cache file missing, stale, or model not in cache.
        """
        cache = self._read_cache()
        if cache is None:
            raise CacheMiss(f"No price cache found at {self._cache_path}")

        if self._is_stale(cache):
            raise CacheMiss(
                f"Price cache is stale (fetched {cache.get('fetched_at', 'unknown')}). "
                "Run 'bench prices refresh' to update."
            )

        models = cache.get("models", {})
        if kilo_model_id not in models:
            raise CacheMiss(
                f"Model '{kilo_model_id}' not found in price cache. "
                "Run 'bench prices refresh' to update."
            )

        entry = models[kilo_model_id]
        return PriceInfo(
            kilo_model_id=kilo_model_id,
            input_price=entry["input"],
            output_price=entry["output"],
            context_window=entry.get("context"),
        )

    def _is_stale(self, cache: dict[str, Any]) -> bool:
        """Return True if the cache is older than the TTL."""
        fetched_at_str = cache.get("fetched_at", "")
        if not fetched_at_str:
            return True
        try:
            fetched_at = datetime.fromisoformat(fetched_at_str)
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - fetched_at
            return age > timedelta(days=_TTL_DAYS)
        except (ValueError, TypeError):
            return True

    def _read_cache(self) -> dict[str, Any] | None:
        """Read and parse the cache file. Returns None if missing or invalid."""
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "models" in data:
                return data
        except (json.JSONDecodeError, FileNotFoundError, OSError):
            pass
        return None

    def _write_cache(self, data: dict[str, Any]) -> None:
        """Write cache data to disk as JSON."""
        self._cache_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_freshness(self) -> str | None:
        """Return the fetched_at timestamp from cache, or None."""
        cache = self._read_cache()
        if cache is None:
            return None
        return cache.get("fetched_at")

    def get_all_prices(self) -> dict[str, PriceInfo]:
        """Read all cached prices in a single file read.

        Returns:
            Dict mapping KiloCode model IDs to PriceInfo.
            Returns empty dict if cache is missing or stale.
        """
        cache = self._read_cache()
        if cache is None or self._is_stale(cache):
            return {}
        result = {}
        for kilo_id, entry in cache.get("models", {}).items():
            result[kilo_id] = PriceInfo(
                kilo_model_id=kilo_id,
                input_price=entry["input"],
                output_price=entry["output"],
                context_window=entry.get("context"),
            )
        return result


def _safe_float(value: Any) -> float:
    """Convert a value to float, defaulting to 0.0."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Module-level convenience functions (used by scorers and CLI)
# ---------------------------------------------------------------------------

_default_cache = KiloCodeCache()


def fetch_and_cache_prices() -> Path:
    """Fetch prices and write cache. See KiloCodeCache.fetch_and_cache_prices."""
    return _default_cache.fetch_and_cache_prices()


def get_price(kilo_model_id: str) -> PriceInfo:
    """Get price from default cache. See KiloCodeCache.get_price."""
    return _default_cache.get_price(kilo_model_id)
