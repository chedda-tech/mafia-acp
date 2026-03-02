"""Signal detection engine for market analysis.

Detects 6 market signal types with strength ratings:
- fear_capitulation: F&G < 25 + volume spike
- greed_exhaustion: F&G > 75 + declining momentum
- btc_dominance_rising: Capital rotating to BTC (risk-off)
- btc_dominance_falling: Capital rotating to alts (risk-on)
- volume_spike: 24h volume up 40%+
- volume_dry_up: 24h volume down 30%+
"""

from __future__ import annotations

import logging

from src.data.models import MarketDataCache, Signal, SignalStrength, SignalType

logger = logging.getLogger(__name__)


def detect_signals(data: MarketDataCache) -> list[Signal]:
    """Evaluate current market data against all signal patterns."""
    signals: list[Signal] = []

    # Fear capitulation: F&G < 25 + volume spike
    if data.fg_value < 25:
        avg_volume_change = _avg_volume_change(data)
        if avg_volume_change > 20:
            strength = _volume_strength(avg_volume_change)
            signals.append(Signal(
                signal=SignalType.FEAR_CAPITULATION.value,
                strength=strength,
                description=f"F&G at {data.fg_value} with volume up {avg_volume_change:.0f}% — "
                "historically a bottom signal",
            ))

    # Greed exhaustion: F&G > 75 + declining momentum
    if data.fg_value > 75:
        if data.fg_change_24h < 0:
            strength = _fg_magnitude_strength(abs(data.fg_change_24h))
            signals.append(Signal(
                signal=SignalType.GREED_EXHAUSTION.value,
                strength=strength,
                description=(
                    f"F&G at {data.fg_value}, declining "
                    f"{abs(data.fg_change_24h):.0f} pts — exhaustion signal"
                ),
            ))

    # BTC dominance shifts (>1% change in 24h = significant)
    if data.btc_dominance_change_24h > 0.5:
        strength = _dominance_strength(data.btc_dominance_change_24h)
        signals.append(Signal(
            signal=SignalType.BTC_DOMINANCE_RISING.value,
            strength=strength,
            description=f"BTC dominance up {data.btc_dominance_change_24h:.1f}% in 24h — "
            "risk-off rotation, alts likely to underperform",
        ))

    if data.btc_dominance_change_24h < -0.5:
        strength = _dominance_strength(abs(data.btc_dominance_change_24h))
        signals.append(Signal(
            signal=SignalType.BTC_DOMINANCE_FALLING.value,
            strength=strength,
            description=f"BTC dominance down {abs(data.btc_dominance_change_24h):.1f}% in 24h — "
            "risk-on rotation, alt season signal",
        ))

    # Volume spike: avg volume change > 40%
    avg_vol = _avg_volume_change(data)
    if avg_vol > 40:
        strength = _volume_strength(avg_vol)
        signals.append(Signal(
            signal=SignalType.VOLUME_SPIKE.value,
            strength=strength,
            description=f"24h volume up {avg_vol:.0f}% — suggests forced selling or FOMO buying",
        ))

    # Volume dry-up: avg volume change < -30%
    if avg_vol < -30:
        strength = _volume_strength(abs(avg_vol))
        signals.append(Signal(
            signal=SignalType.VOLUME_DRY_UP.value,
            strength=strength,
            description=(
                f"24h volume down {abs(avg_vol):.0f}% — "
                "low conviction, potential range-bound"
            ),
        ))

    return signals


def _avg_volume_change(data: MarketDataCache) -> float:
    """Average volume change across tracked assets."""
    changes = [
        data.btc_volume_change_24h,
        data.eth_volume_change_24h,
        data.sol_volume_change_24h,
    ]
    non_zero = [c for c in changes if c != 0.0]
    if not non_zero:
        return 0.0
    return sum(non_zero) / len(non_zero)


def _volume_strength(change: float) -> str:
    """Map volume change magnitude to signal strength."""
    if change >= 60:
        return SignalStrength.STRONG.value
    elif change >= 40:
        return SignalStrength.MODERATE.value
    return SignalStrength.WEAK.value


def _fg_magnitude_strength(change: float) -> str:
    """Map F&G change magnitude to signal strength."""
    if change >= 10:
        return SignalStrength.STRONG.value
    elif change >= 5:
        return SignalStrength.MODERATE.value
    return SignalStrength.WEAK.value


def _dominance_strength(change: float) -> str:
    """Map dominance change to signal strength."""
    if change >= 2.0:
        return SignalStrength.STRONG.value
    elif change >= 1.0:
        return SignalStrength.MODERATE.value
    return SignalStrength.WEAK.value
