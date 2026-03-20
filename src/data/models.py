"""Data models for market data, job deliverables, and signal detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# --- Fear & Greed Classification ---


class FearAndGreedClassification(StrEnum):
    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"


def classify_fg(value: int) -> str:
    """Map a Fear & Greed value (0-100) to its classification string."""
    if value <= 24:
        return FearAndGreedClassification.EXTREME_FEAR.value
    elif value <= 44:
        return FearAndGreedClassification.FEAR.value
    elif value <= 55:
        return FearAndGreedClassification.NEUTRAL.value
    elif value <= 74:
        return FearAndGreedClassification.GREED.value
    else:
        return FearAndGreedClassification.EXTREME_GREED.value


# --- Market Data Cache ---


@dataclass
class MarketDataCache:
    """In-memory cache of all market data. Shared across all monitoring jobs."""

    # Fear & Greed
    fg_value: int = 50
    fg_classification: str = "neutral"
    fg_change_1h: float = 0.0
    fg_change_24h: float = 0.0
    fg_change_7d: float = 0.0
    fg_change_30d: float = 0.0
    fg_7d_low: int = 50
    fg_7d_high: int = 50
    fg_trend_2d: str = "flat"  # "up", "down", "flat"
    fg_trend_3d: str = "flat"

    # BTC
    btc_price: float = 0.0
    btc_change_24h: float = 0.0
    btc_change_7d: float = 0.0
    btc_dominance: float = 0.0
    btc_dominance_change_24h: float = 0.0
    btc_dominance_change_7d: float = 0.0
    btc_volume_24h: float = 0.0
    btc_volume_change_24h: float = 0.0

    # ETH
    eth_price: float = 0.0
    eth_change_24h: float = 0.0
    eth_change_7d: float = 0.0
    eth_volume_24h: float = 0.0
    eth_volume_change_24h: float = 0.0

    # SOL
    sol_price: float = 0.0
    sol_change_24h: float = 0.0
    sol_change_7d: float = 0.0
    sol_volume_24h: float = 0.0
    sol_volume_change_24h: float = 0.0

    # Global
    total_market_cap: float = 0.0
    total_market_cap_change_24h: float = 0.0
    total_market_cap_change_7d: float = 0.0
    total_volume_24h: float = 0.0

    # Metadata
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get_price(self, symbol: str) -> float | None:
        """Get price for a given asset symbol."""
        prices = {
            "BTC": self.btc_price,
            "ETH": self.eth_price,
            "SOL": self.sol_price,
        }
        return prices.get(symbol.upper())

    def get_asset_data(self, symbol: str) -> dict[str, Any] | None:
        """Get full asset data dict for a symbol."""
        symbol = symbol.upper()
        if symbol == "BTC":
            return {
                "symbol": "BTC",
                "price": self.btc_price,
                "change_24h": self.btc_change_24h,
                "change_7d": self.btc_change_7d,
                "volume_24h": _format_volume(self.btc_volume_24h),
                "volume_change_24h": self.btc_volume_change_24h,
            }
        elif symbol == "ETH":
            return {
                "symbol": "ETH",
                "price": self.eth_price,
                "change_24h": self.eth_change_24h,
                "change_7d": self.eth_change_7d,
                "volume_24h": _format_volume(self.eth_volume_24h),
                "volume_change_24h": self.eth_volume_change_24h,
            }
        elif symbol == "SOL":
            return {
                "symbol": "SOL",
                "price": self.sol_price,
                "change_24h": self.sol_change_24h,
                "change_7d": self.sol_change_7d,
                "volume_24h": _format_volume(self.sol_volume_24h),
                "volume_change_24h": self.sol_volume_change_24h,
            }
        return None


# --- Signal Detection ---


class SignalType(StrEnum):
    FEAR_CAPITULATION = "fear_capitulation"
    GREED_EXHAUSTION = "greed_exhaustion"
    BTC_DOMINANCE_RISING = "btc_dominance_rising"
    BTC_DOMINANCE_FALLING = "btc_dominance_falling"
    VOLUME_SPIKE = "volume_spike"
    VOLUME_DRY_UP = "volume_dry_up"


class SignalStrength(StrEnum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


@dataclass
class Signal:
    """A detected market signal."""

    signal: str
    strength: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "signal": self.signal,
            "strength": self.strength,
            "description": self.description,
        }


# --- Helpers ---


def _format_volume(volume: float) -> str:
    """Format volume as human-readable string (e.g., '28.5B')."""
    if volume >= 1_000_000_000_000:
        return f"{volume / 1_000_000_000_000:.1f}T"
    elif volume >= 1_000_000_000:
        return f"{volume / 1_000_000_000:.1f}B"
    elif volume >= 1_000_000:
        return f"{volume / 1_000_000:.1f}M"
    else:
        return f"{volume:,.0f}"


def format_market_cap(value: float) -> str:
    """Format market cap as human-readable string."""
    return _format_volume(value)
