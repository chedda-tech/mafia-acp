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

    async def _fetch_terminal_data(self) -> dict:
        """Fetch market data from the Terminal API."""
        if not self._settings.terminal_api_url:
            return {}

        try:
            resp = await self._client.get(self._settings.terminal_api_url)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Terminal API fetch failed: %s", e)
            return {}

    def _parse_market_data(self, data: dict) -> dict:
        """Parse Terminal API response into cache fields.

        Adapt field names here when the actual API response format is known.
        """
        if not data:
            return {}

        return {
            "btc_price": float(data.get("btc_price", 0)),
            "btc_change_24h": float(data.get("btc_change_24h", 0)),
            "btc_change_7d": float(data.get("btc_change_7d", 0)),
            "btc_dominance": float(data.get("btc_dominance", 0)),
            "btc_dominance_change_24h": float(data.get("btc_dominance_change_24h", 0)),
            "btc_volume_24h": float(data.get("btc_volume_24h", 0)),
            "btc_volume_change_24h": float(data.get("btc_volume_change_24h", 0)),
            "eth_price": float(data.get("eth_price", 0)),
            "eth_change_24h": float(data.get("eth_change_24h", 0)),
            "eth_change_7d": float(data.get("eth_change_7d", 0)),
            "eth_volume_24h": float(data.get("eth_volume_24h", 0)),
            "eth_volume_change_24h": float(data.get("eth_volume_change_24h", 0)),
            "sol_price": float(data.get("sol_price", 0)),
            "sol_change_24h": float(data.get("sol_change_24h", 0)),
            "sol_change_7d": float(data.get("sol_change_7d", 0)),
            "sol_volume_24h": float(data.get("sol_volume_24h", 0)),
            "sol_volume_change_24h": float(data.get("sol_volume_change_24h", 0)),
            "total_market_cap": float(data.get("total_market_cap", 0)),
            "total_market_cap_change_24h": float(data.get("total_market_cap_change_24h", 0)),
            "total_market_cap_change_7d": float(data.get("total_market_cap_change_7d", 0)),
            "total_volume_24h": float(data.get("total_volume_24h", 0)),
        }
