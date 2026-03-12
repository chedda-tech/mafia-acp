"""Thread-safe in-memory market data cache."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from src.data.models import MarketDataCache

logger = logging.getLogger(__name__)


class DataCache:
    """Singleton-style cache for market data. All monitoring jobs share this."""

    def __init__(self, stale_threshold_seconds: int = 300) -> None:
        self._data = MarketDataCache()
        self._lock = asyncio.Lock()
        self._stale_threshold = stale_threshold_seconds
        self._initialized = False

    async def update(self, data: MarketDataCache) -> None:
        """Update the cache with fresh market data."""
        async with self._lock:
            self._data = data
            self._initialized = True
            logger.debug("Cache updated at %s", data.last_updated.isoformat())

    async def get_latest(self) -> MarketDataCache:
        """Get the latest cached market data."""
        async with self._lock:
            return self._data

    def is_stale(self) -> bool:
        """Check if cached data is older than the staleness threshold."""
        if not self._initialized:
            return True
        age = (datetime.now(UTC) - self._data.last_updated).total_seconds()
        return age > self._stale_threshold

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def last_updated(self) -> datetime:
        return self._data.last_updated
