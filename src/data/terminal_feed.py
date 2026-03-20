"""Market data feed combining Alternative.me (F&G) and Terminal API (market data).

Refreshes every 60 seconds and updates the shared cache.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import httpx

from src.agent.config import Settings
from src.data.cache import DataCache
from src.data.fear_and_greed import FearAndGreedFeed
from src.data.models import MarketDataCache, classify_fg

logger = logging.getLogger(__name__)


class TerminalFeed:
    """Fetches data from all sources and keeps the DataCache fresh.

    Data sources:
    1. Alternative.me — Fear & Greed Index (free, updates daily)
    2. Terminal API — Prices, volumes, dominance, market cap (when configured)
    """

    def __init__(self, settings: Settings, cache: DataCache) -> None:
        self._settings = settings
        self._cache = cache
        self._fg_feed = FearAndGreedFeed()
        self._client = httpx.AsyncClient(timeout=15.0)
        self._running = False

    async def start(self) -> None:
        """Start the feed loop. Runs until cancelled."""
        self._running = True
        interval = self._settings.data_refresh_interval_seconds
        logger.info("Data feed starting (refresh every %ds)", interval)

        while self._running:
            try:
                await self._refresh()
            except Exception as e:
                logger.error("Feed refresh failed: %s", e)
            await asyncio.sleep(interval)

    async def stop(self) -> None:
        self._running = False
        await self._client.aclose()
        await self._fg_feed.close()

    async def _refresh(self) -> None:
        """Fetch latest data from all sources and update cache."""
        # Fetch F&G and market data concurrently
        fg_value, market_data = await asyncio.gather(
            self._fg_feed.fetch(),
            self._fetch_terminal_data(),
        )

        now = datetime.now(UTC)
        fg = fg_value if fg_value is not None else (self._fg_feed.current_value or 50)
        parsed = self._parse_market_data(market_data)

        cache_data = MarketDataCache(
            # Fear & Greed (from Alternative.me)
            fg_value=fg,
            fg_classification=classify_fg(fg),
            fg_change_1h=self._fg_feed.get_change(1),
            fg_change_24h=self._fg_feed.get_change(24),
            fg_change_7d=self._fg_feed.get_change(168),
            fg_change_30d=self._fg_feed.get_change(720),
            fg_7d_low=self._fg_feed.get_period_low(7),
            fg_7d_high=self._fg_feed.get_period_high(7),
            fg_trend_2d=self._fg_feed.get_trend(2),
            fg_trend_3d=self._fg_feed.get_trend(3),
            # Market data (from Terminal API)
            btc_price=parsed.get("btc_price", 0.0),
            btc_change_24h=parsed.get("btc_change_24h", 0.0),
            btc_change_7d=parsed.get("btc_change_7d", 0.0),
            btc_dominance=parsed.get("btc_dominance", 0.0),
            btc_dominance_change_24h=parsed.get("btc_dominance_change_24h", 0.0),
            btc_volume_24h=parsed.get("btc_volume_24h", 0.0),
            btc_volume_change_24h=parsed.get("btc_volume_change_24h", 0.0),
            eth_price=parsed.get("eth_price", 0.0),
            eth_change_24h=parsed.get("eth_change_24h", 0.0),
            eth_change_7d=parsed.get("eth_change_7d", 0.0),
            eth_volume_24h=parsed.get("eth_volume_24h", 0.0),
            eth_volume_change_24h=parsed.get("eth_volume_change_24h", 0.0),
            sol_price=parsed.get("sol_price", 0.0),
            sol_change_24h=parsed.get("sol_change_24h", 0.0),
            sol_change_7d=parsed.get("sol_change_7d", 0.0),
            sol_volume_24h=parsed.get("sol_volume_24h", 0.0),
            sol_volume_change_24h=parsed.get("sol_volume_change_24h", 0.0),
            total_market_cap=parsed.get("total_market_cap", 0.0),
            total_market_cap_change_24h=parsed.get("total_market_cap_change_24h", 0.0),
            total_market_cap_change_7d=parsed.get("total_market_cap_change_7d", 0.0),
            total_volume_24h=parsed.get("total_volume_24h", 0.0),
            # Metadata
            last_updated=now,
        )

        await self._cache.update(cache_data)
        logger.debug(
            "Feed refreshed: F&G=%d (%s)",
            fg,
            cache_data.fg_classification,
        )

    async def _fetch_terminal_data(self) -> dict | list:
        """Fetch market data from the Mafia API."""
        if not self._settings.mafia_api_base_url:
            return {}

        base_url = self._settings.mafia_api_base_url.rstrip("/")
        # We can use /api/metrics/multi-period to get rich data
        endpoint = f"{base_url}/api/metrics/multi-period"
        params = {
            "periods": "1h,24h,7d,30d",
            "metrics": "BTC.PRICE,BTC.DOMINANCE,BTC.VOLUME_24H,ETH.PRICE,ETH.VOLUME_24H,SOL.PRICE,SOL.VOLUME_24H,TOTAL_MARKET_CAP,TOTAL_VOLUME_24H",
        }

        try:
            resp = await self._client.get(endpoint, params=params)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data
        except Exception as e:
            logger.warning("Mafia API fetch failed: %s", e)
            return {}

    def _safe_float(
        self,
        data: dict,
        key: str,
        fallback_key: str | None = None,
        change_period: str | None = None,
    ) -> float:
        """Extract float value safely, checking multiple potential structures."""
        # 1. Try flat key (e.g. 'btc_price')
        if key in data:
            return float(data[key] or 0)

        # 2. Try nested structure from multi-period (e.g. 'BTC.PRICE' -> 'value' or 'changes')
        if fallback_key and fallback_key in data:
            val = data[fallback_key]
            if isinstance(val, dict):
                if change_period:
                    changes = val.get("changes", {})
                    # If changes is a dict, get the period, else it might have direct keys or be flat.
                    if isinstance(changes, dict):
                        return float(
                            changes.get(change_period, changes.get(change_period.upper(), 0)) or 0
                        )
                    return 0.0
                return float(val.get("value", 0) or 0)
            # If flat value returned directly from fallback_key
            if not change_period:
                return float(val or 0)

        return 0.0

    def _parse_market_data(self, raw_data: dict | list) -> dict:
        """Parse Mafia API /api/metrics/multi-period response into cache fields.

        Normalizes the multi-period metrics payload into a dict keyed by
        'ASSET.METRIC' with 'value' and 'changes' entries. Update this mapping
        if the Mafia API response format changes.
        """
        if not raw_data:
            return {}

        data = {}
        # Multi-period payload flattens to nested structures -> {"BTC.PRICE": {"value": 123, "changes": {"24h": -0.56}}}
        if isinstance(raw_data, list):
            for period_data in raw_data:
                period = period_data.get("period", "")
                metrics = period_data.get("metrics", [])
                for m in metrics:
                    asset = m.get("asset", "")
                    metric_name = m.get("metric", "")

                    key = f"{asset}.{metric_name}" if asset else metric_name

                    if key not in data:
                        data[key] = {}

                    data[key]["value"] = m.get("current", {}).get("value", 0.0)

                    if "changes" not in data[key]:
                        data[key]["changes"] = {}

                    data[key]["changes"][period] = m.get("change", {}).get("percent", 0.0)
        else:
            data = raw_data

        return {
            "btc_price": self._safe_float(data, "btc_price", "BTC.PRICE"),
            "btc_change_24h": self._safe_float(data, "btc_change_24h", "BTC.PRICE", "24h"),
            "btc_change_7d": self._safe_float(data, "btc_change_7d", "BTC.PRICE", "7d"),
            "btc_dominance": self._safe_float(data, "btc_dominance", "BTC.DOMINANCE"),
            "btc_dominance_change_24h": self._safe_float(
                data, "btc_dominance_change_24h", "BTC.DOMINANCE", "24h"
            ),
            "btc_dominance_change_7d": self._safe_float(
                data, "btc_dominance_change_7d", "BTC.DOMINANCE", "7d"
            ),
            "btc_volume_24h": self._safe_float(data, "btc_volume_24h", "BTC.VOLUME_24H"),
            "btc_volume_change_24h": self._safe_float(
                data, "btc_volume_change_24h", "BTC.VOLUME_24H", "24h"
            ),
            "eth_price": self._safe_float(data, "eth_price", "ETH.PRICE"),
            "eth_change_24h": self._safe_float(data, "eth_change_24h", "ETH.PRICE", "24h"),
            "eth_change_7d": self._safe_float(data, "eth_change_7d", "ETH.PRICE", "7d"),
            "eth_volume_24h": self._safe_float(data, "eth_volume_24h", "ETH.VOLUME_24H"),
            "eth_volume_change_24h": self._safe_float(
                data, "eth_volume_change_24h", "ETH.VOLUME_24H", "24h"
            ),
            "sol_price": self._safe_float(data, "sol_price", "SOL.PRICE"),
            "sol_change_24h": self._safe_float(data, "sol_change_24h", "SOL.PRICE", "24h"),
            "sol_change_7d": self._safe_float(data, "sol_change_7d", "SOL.PRICE", "7d"),
            "sol_volume_24h": self._safe_float(data, "sol_volume_24h", "SOL.VOLUME_24H"),
            "sol_volume_change_24h": self._safe_float(
                data, "sol_volume_change_24h", "SOL.VOLUME_24H", "24h"
            ),
            "total_market_cap": self._safe_float(data, "total_market_cap", "TOTAL_MARKET_CAP"),
            "total_market_cap_change_24h": self._safe_float(
                data, "total_market_cap_change_24h", "TOTAL_MARKET_CAP", "24h"
            ),
            "total_market_cap_change_7d": self._safe_float(
                data, "total_market_cap_change_7d", "TOTAL_MARKET_CAP", "7d"
            ),
            "total_volume_24h": self._safe_float(data, "total_volume_24h", "TOTAL_VOLUME_24H"),
        }
