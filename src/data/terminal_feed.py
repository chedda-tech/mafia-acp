"""Market data feed connecting to the existing MAFIA Terminal API.

The Terminal API aggregates CoinMarketCap data and serves it via REST.
This module fetches from that API every 60 seconds and updates the shared cache.

The Terminal API URL and response structure will be provided by the user.
This implementation uses an abstraction layer so the actual endpoint details
can be plugged in easily.
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
    """Connects to the MAFIA Terminal API and keeps the DataCache fresh.

    Combines data from:
    1. Terminal API (prices, dominance, volumes, market cap)
    2. FearAndGreedFeed (F&G index with history)
    """

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        fg_feed: FearAndGreedFeed,
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._fg_feed = fg_feed
        self._client = httpx.AsyncClient(timeout=15.0)
        self._running = False

    async def start(self) -> None:
        """Start the feed loop. Runs until cancelled."""
        self._running = True
        interval = self._settings.data_refresh_interval_seconds
        logger.info("Terminal feed starting (refresh every %ds)", interval)

        # Bootstrap F&G history on first run
        await self._fg_feed.fetch_historical(days=30)

        while self._running:
            try:
                await self._refresh()
            except Exception as e:
                logger.error("Feed refresh failed: %s", e)
            await asyncio.sleep(self._settings.data_refresh_interval_seconds)

    async def stop(self) -> None:
        self._running = False
        await self._client.aclose()
        await self._fg_feed.close()

    async def _refresh(self) -> None:
        """Fetch latest data from all sources and update cache."""
        # Fetch F&G
        fg_data = await self._fg_feed.fetch()

        # Fetch market data from Terminal API
        market_data = await self._fetch_terminal_data()

        # Build cache update
        now = datetime.now(UTC)
        fg_value = fg_data.value if fg_data else (self._fg_feed.current_value or 50)

        cache_data = MarketDataCache(
            # Fear & Greed
            fg_value=fg_value,
            fg_classification=classify_fg(fg_value),
            fg_change_1h=self._fg_feed.get_change(1),
            fg_change_24h=self._fg_feed.get_change(24),
            fg_change_7d=self._fg_feed.get_change(168),
            fg_change_30d=self._fg_feed.get_change(720),
            fg_7d_low=self._fg_feed.get_period_low(7),
            fg_7d_high=self._fg_feed.get_period_high(7),
            fg_trend_2d=self._fg_feed.get_trend(2),
            fg_trend_3d=self._fg_feed.get_trend(3),
            # Market data from Terminal
            **self._parse_market_data(market_data),
            # Metadata
            last_updated=now,
        )

        await self._cache.update(cache_data)
        logger.debug("Feed refreshed: F&G=%d (%s)", fg_value, cache_data.fg_classification)

    async def _fetch_terminal_data(self) -> dict:
        """Fetch market data from the Terminal API.

        The actual endpoint URL and response structure will be provided.
        This is the abstraction point — swap in the real API when ready.
        """
        if not self._settings.terminal_api_url:
            logger.debug("No Terminal API URL configured, using empty market data")
            return {}

        try:
            resp = await self._client.get(f"{self._settings.terminal_api_url}/api/market-data")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Terminal API fetch failed: %s", e)
            return {}

    def _parse_market_data(self, data: dict) -> dict:
        """Parse Terminal API response into MarketDataCache fields.

        Adapt this method when the actual Terminal API response format is known.
        Currently returns sensible defaults when data is empty.
        """
        if not data:
            return {
                "btc_price": 0.0,
                "btc_change_24h": 0.0,
                "btc_change_7d": 0.0,
                "btc_dominance": 0.0,
                "btc_dominance_change_24h": 0.0,
                "btc_volume_24h": 0.0,
                "btc_volume_change_24h": 0.0,
                "eth_price": 0.0,
                "eth_change_24h": 0.0,
                "eth_change_7d": 0.0,
                "eth_volume_24h": 0.0,
                "eth_volume_change_24h": 0.0,
                "sol_price": 0.0,
                "sol_change_24h": 0.0,
                "sol_change_7d": 0.0,
                "sol_volume_24h": 0.0,
                "sol_volume_change_24h": 0.0,
                "total_market_cap": 0.0,
                "total_market_cap_change_24h": 0.0,
                "total_market_cap_change_7d": 0.0,
                "total_volume_24h": 0.0,
            }

        # Parse the Terminal API response.
        # TODO: Adapt field names when actual API response format is provided.
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
