"""Fear & Greed Index data feed with fallback sources."""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Alternative.me free API (primary)
ALTERNATIVE_ME_URL = "https://api.alternative.me/fng/"
# CoinMarketCap (fallback, requires API key)
CMC_FNG_URL = "https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest"
CMC_FNG_HISTORICAL_URL = "https://pro-api.coinmarketcap.com/v3/fear-and-greed/historical"


class FearAndGreedData:
    """Parsed Fear & Greed data point."""

    def __init__(self, value: int, timestamp: datetime) -> None:
        self.value = value
        self.timestamp = timestamp


class FearAndGreedFeed:
    """Fetches F&G data from Alternative.me (primary) and CoinMarketCap (fallback).

    Maintains a rolling history for calculating period changes and trends.
    """

    def __init__(self, cmc_api_key: str = "") -> None:
        self._cmc_api_key = cmc_api_key
        self._client = httpx.AsyncClient(timeout=15.0)
        # Rolling history: newest first, keep up to 30 days of hourly data
        self._history: deque[FearAndGreedData] = deque(maxlen=720)
        self._current: FearAndGreedData | None = None

    async def fetch(self) -> FearAndGreedData | None:
        """Fetch current F&G value. Tries Alternative.me first, then CMC."""
        data = await self._fetch_alternative_me()
        if data is None and self._cmc_api_key:
            data = await self._fetch_cmc()
        if data is not None:
            self._current = data
            self._history.appendleft(data)
        return data

    async def fetch_historical(self, days: int = 30) -> list[FearAndGreedData]:
        """Fetch historical F&G data to bootstrap change calculations."""
        data = await self._fetch_alternative_me_historical(days)
        if not data and self._cmc_api_key:
            data = await self._fetch_cmc_historical(days)
        if data:
            # Merge into history (deduplicate by approximate timestamp)
            for point in reversed(data):
                self._history.append(point)
        return data

    @property
    def current_value(self) -> int | None:
        return self._current.value if self._current else None

    def get_change(self, hours: int) -> float:
        """Calculate F&G change over the given number of hours."""
        if not self._current or len(self._history) < 2:
            return 0.0
        target_time = self._current.timestamp.timestamp() - (hours * 3600)
        closest = self._find_closest(target_time)
        if closest is None:
            return 0.0
        return float(self._current.value - closest.value)

    def get_period_low(self, days: int) -> int:
        """Get lowest F&G value in the last N days."""
        if not self._history:
            return self._current.value if self._current else 50
        cutoff = datetime.now(UTC).timestamp() - (days * 86400)
        values = [p.value for p in self._history if p.timestamp.timestamp() >= cutoff]
        return min(values) if values else (self._current.value if self._current else 50)

    def get_period_high(self, days: int) -> int:
        """Get highest F&G value in the last N days."""
        if not self._history:
            return self._current.value if self._current else 50
        cutoff = datetime.now(UTC).timestamp() - (days * 86400)
        values = [p.value for p in self._history if p.timestamp.timestamp() >= cutoff]
        return max(values) if values else (self._current.value if self._current else 50)

    def get_trend(self, days: int) -> str:
        """Determine F&G trend over the last N days: 'up', 'down', or 'flat'."""
        if len(self._history) < 2:
            return "flat"
        cutoff = datetime.now(UTC).timestamp() - (days * 86400)
        points = [p for p in self._history if p.timestamp.timestamp() >= cutoff]
        if len(points) < 2:
            return "flat"
        # Compare oldest to newest in the period
        oldest = points[-1].value
        newest = points[0].value
        diff = newest - oldest
        if diff > 2:
            return "up"
        elif diff < -2:
            return "down"
        return "flat"

    def _find_closest(self, target_timestamp: float) -> FearAndGreedData | None:
        """Find the data point closest to the target timestamp."""
        best: FearAndGreedData | None = None
        best_diff = float("inf")
        for point in self._history:
            diff = abs(point.timestamp.timestamp() - target_timestamp)
            if diff < best_diff:
                best_diff = diff
                best = point
        return best

    # --- Data source implementations ---

    async def _fetch_alternative_me(self) -> FearAndGreedData | None:
        """Fetch from Alternative.me free API."""
        try:
            resp = await self._client.get(ALTERNATIVE_ME_URL, params={"limit": "1"})
            resp.raise_for_status()
            data = resp.json()
            entry = data["data"][0]
            return FearAndGreedData(
                value=int(entry["value"]),
                timestamp=datetime.fromtimestamp(int(entry["timestamp"]), tz=UTC),
            )
        except Exception as e:
            logger.warning("Alternative.me F&G fetch failed: %s", e)
            return None

    async def _fetch_alternative_me_historical(self, days: int) -> list[FearAndGreedData]:
        """Fetch historical data from Alternative.me."""
        try:
            resp = await self._client.get(ALTERNATIVE_ME_URL, params={"limit": str(days)})
            resp.raise_for_status()
            data = resp.json()
            return [
                FearAndGreedData(
                    value=int(entry["value"]),
                    timestamp=datetime.fromtimestamp(int(entry["timestamp"]), tz=UTC),
                )
                for entry in data.get("data", [])
            ]
        except Exception as e:
            logger.warning("Alternative.me historical fetch failed: %s", e)
            return []

    async def _fetch_cmc(self) -> FearAndGreedData | None:
        """Fetch from CoinMarketCap API (fallback)."""
        try:
            headers = {"X-CMC_PRO_API_KEY": self._cmc_api_key}
            resp = await self._client.get(CMC_FNG_URL, headers=headers)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            entry = data["data"]
            return FearAndGreedData(
                value=int(entry["value"]),
                timestamp=datetime.fromisoformat(entry["last_updated"]),
            )
        except Exception as e:
            logger.warning("CMC F&G fetch failed: %s", e)
            return None

    async def _fetch_cmc_historical(self, days: int) -> list[FearAndGreedData]:
        """Fetch historical data from CoinMarketCap."""
        try:
            headers = {"X-CMC_PRO_API_KEY": self._cmc_api_key}
            resp = await self._client.get(
                CMC_FNG_HISTORICAL_URL,
                headers=headers,
                params={"limit": str(days)},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return [
                FearAndGreedData(
                    value=int(entry["value"]),
                    timestamp=datetime.fromisoformat(entry["timestamp"]),
                )
                for entry in data.get("data", [])
            ]
        except Exception as e:
            logger.warning("CMC historical F&G fetch failed: %s", e)
            return []

    async def close(self) -> None:
        await self._client.aclose()
