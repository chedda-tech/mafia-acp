"""Market data feed from the Mafia API (CoinMarketCap-backed).

Refreshes every 60 seconds and updates the shared cache.
All data — Fear & Greed, prices, volumes, dominance, market cap — comes
from a single /api/metrics/multi-period call.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import httpx

from src.agent.config import Settings
from src.data.cache import DataCache
from src.data.models import MarketDataCache, classify_fg

logger = logging.getLogger(__name__)


class TerminalFeed:
    """Fetches data from the Mafia API and keeps the DataCache fresh.

    Single data source: Mafia API (CoinMarketCap-backed).
    Provides prices, volumes, dominance, market cap, and Fear & Greed Index.
    """

    def __init__(self, settings: Settings, cache: DataCache) -> None:
        self._settings = settings
        self._cache = cache
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

    async def _refresh(self) -> None:
        """Fetch latest data from the Mafia API and update cache."""
        raw = await self._fetch_terminal_data()
        parsed = self._parse_market_data(raw)

        fg = int(parsed.get("fg_value", 50) or 50)
        now = datetime.now(UTC)

        cache_data = MarketDataCache(
            # Fear & Greed (from CMC via Mafia API)
            fg_value=fg,
            fg_classification=classify_fg(fg),
            fg_change_1h=parsed.get("fg_change_1h", 0.0),
            fg_change_24h=parsed.get("fg_change_24h", 0.0),
            fg_change_7d=parsed.get("fg_change_7d", 0.0),
            fg_change_30d=parsed.get("fg_change_30d", 0.0),
            # Market data (from Mafia API)
            btc_price=parsed.get("btc_price", 0.0),
            btc_change_24h=parsed.get("btc_change_24h", 0.0),
            btc_change_7d=parsed.get("btc_change_7d", 0.0),
            btc_dominance=parsed.get("btc_dominance", 0.0),
            btc_dominance_change_24h=parsed.get("btc_dominance_change_24h", 0.0),
            btc_dominance_change_7d=parsed.get("btc_dominance_change_7d", 0.0),
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
            last_updated=now,
        )

        await self._cache.update(cache_data)
        logger.debug("Feed refreshed: F&G=%d (%s)", fg, cache_data.fg_classification)

    async def _fetch_terminal_data(self) -> dict | list:
        """Fetch market data from the Mafia API."""
        if not self._settings.mafia_api_base_url:
            return {}

        base_url = self._settings.mafia_api_base_url.rstrip("/")
        endpoint = f"{base_url}/api/metrics/multi-period"
        params = {
            "periods": "1h,24h,7d,30d",
            "metrics": "FEAR_GREED_INDEX,BTC.PRICE,BTC.DOMINANCE,BTC.VOLUME_24H,ETH.PRICE,ETH.VOLUME_24H,SOL.PRICE,SOL.VOLUME_24H,TOTAL_MARKET_CAP,TOTAL_VOLUME_24H",
        }

        try:
            resp = await self._client.get(endpoint, params=params)
            resp.raise_for_status()
            return resp.json().get("data", [])
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
        if key in data:
            return float(data[key] or 0)

        if fallback_key and fallback_key in data:
            val = data[fallback_key]
            if isinstance(val, dict):
                if change_period:
                    changes = val.get("changes", {})
                    if isinstance(changes, dict):
                        return float(
                            changes.get(change_period, changes.get(change_period.upper(), 0)) or 0
                        )
                    return 0.0
                return float(val.get("value", 0) or 0)
            if not change_period:
                return float(val or 0)

        return 0.0

    def _fg_point_change(self, data: dict, period: str) -> float:
        """Compute absolute point change for F&G on the 0-100 scale.

        The Mafia API returns percent change relative to the old value (standard
        financial percent). We convert to absolute points so signal thresholds
        remain intuitive: +10 points means F&G moved 10 units on the 100-point scale.

        Formula: points = current * pct / (100 + pct)
        Example: current=25, pct=+66.7% (was 15) → 25 * 66.7 / 166.7 = 10 pts
        """
        fg_data = data.get("FEAR_GREED_INDEX", {})
        current = float(fg_data.get("value", 0) or 0)
        if current == 0:
            return 0.0
        pct = float((fg_data.get("changes", {}) or {}).get(period, 0) or 0)
        if pct == 0:
            return 0.0
        denom = 100.0 + pct
        if abs(denom) < 1e-3:  # guard against pct ≈ -100 (ZeroDivisionError)
            return 0.0
        return round(current * pct / denom, 1)

    def _parse_market_data(self, raw_data: dict | list) -> dict:
        """Parse Mafia API /api/metrics/multi-period response into cache fields.

        Normalizes the multi-period metrics payload into a dict keyed by
        'ASSET.METRIC' with 'value' and 'changes' entries.
        """
        if not raw_data:
            return {}

        data: dict = {}
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

        # F&G: absolute point changes on 0-100 scale
        fg_value = self._safe_float(data, "fg_value", "FEAR_GREED_INDEX")

        return {
            "fg_value": fg_value,
            "fg_change_1h": self._fg_point_change(data, "1h"),
            "fg_change_24h": self._fg_point_change(data, "24h"),
            "fg_change_7d": self._fg_point_change(data, "7d"),
            "fg_change_30d": self._fg_point_change(data, "30d"),
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
