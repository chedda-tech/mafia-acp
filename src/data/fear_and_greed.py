"""Fear & Greed Index data from Alternative.me free API.

Fetches current F&G value and tracks history for period changes and trends.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

ALTERNATIVE_ME_URL = "https://api.alternative.me/fng/"


class FearAndGreedData:
    """Parsed Fear & Greed data point."""

    def __init__(self, value: int, timestamp: datetime) -> None:
        self.value = value
        self.timestamp = timestamp


class FearAndGreedFeed:
    """Fetches F&G from Alternative.me and tracks history.

    The API updates once per day. We fetch on each refresh cycle
    but the value only changes daily.
    """

    def __init__(self) -> None:
        self._history: deque[FearAndGreedData] = deque(maxlen=720)
        self._current: FearAndGreedData | None = None
        self._client = httpx.AsyncClient(timeout=15.0)
        self._bootstrapped = False

    async def fetch(self) -> int | None:
        """Fetch F&G data from Alternative.me.

        On first call, fetches 31 days of history so that 7d/30d change
        calculations work immediately. Subsequent calls fetch just the
        latest value (it only updates once per day anyway).

        Returns the current value (0-100) or None on failure.
        """
        limit = 31 if not self._bootstrapped else 1
        try:
            resp = await self._client.get(ALTERNATIVE_ME_URL, params={"limit": str(limit)})
            resp.raise_for_status()
            data = resp.json()
            entries = data.get("data", [])
            if not entries:
                return None

            if not self._bootstrapped:
                # Load history oldest-first so deque order is newest-first
                for entry in reversed(entries):
                    point = self._parse_entry(entry)
                    self._history.appendleft(point)
                self._current = self._history[0]
                self._bootstrapped = True
                logger.info("F&G bootstrapped with %d days of history", len(entries))
            else:
                point = self._parse_entry(entries[0])
                # Only append if it's a new data point (different timestamp)
                if not self._current or point.timestamp != self._current.timestamp:
                    self._history.appendleft(point)
                self._current = point

            return self._current.value
        except Exception as e:
            logger.warning("Alternative.me F&G fetch failed: %s", e)
            return None

    @staticmethod
    def _parse_entry(entry: dict) -> FearAndGreedData:
        """Parse a single API response entry."""
        return FearAndGreedData(
            value=int(entry["value"]),
            timestamp=datetime.fromtimestamp(int(entry["timestamp"]), tz=UTC),
        )

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

    async def close(self) -> None:
        await self._client.aclose()
