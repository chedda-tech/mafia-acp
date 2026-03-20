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


def map_market_regime(data: MarketDataCache) -> dict[str, str | float]:
    """Deterministically map market state to a predefined regime for the AI narrator.

    This ensures the AI is constrained to commenting on safe, deterministic rules
    rather than inventing trading advice.
    """
    # 1. Fear and Greed Baseline
    fg = data.fg_value
    if fg <= 24:
        sentiment_regime = "Extreme Fear"
    elif fg <= 45:
        sentiment_regime = "Fear"
    elif fg <= 54:
        sentiment_regime = "Neutral"
    elif fg <= 74:
        sentiment_regime = "Greed"
    else:
        sentiment_regime = "Extreme Greed"

    # 2. Trend Mapping (Using BTC 7d vs 30d changes as proxy, or 24h vs 7d since we only cache up to 7d reliably for now)
    # The cache actually has 7d, wait let's check MarketDataCache
    # MarketDataCache has btc_change_24h and btc_change_7d.
    # We can use that.
    short_term = data.btc_change_24h
    medium_term = data.btc_change_7d

    if short_term < 0 and medium_term > 0:
        trend_regime = "Short-term pullback in a structural uptrend"
    elif short_term > 0 and medium_term < 0:
        trend_regime = "Short-term relief bounce in a structural downtrend"
    elif short_term > 0 and medium_term > 0:
        trend_regime = "Bullish momentum acceleration"
    else:
        trend_regime = "Capitulation / Distribution regime"

    # 3. Volatility / Volume regime
    avg_vol = _avg_volume_change(data)
    if avg_vol > 30:
        vol_regime = "High accumulation/distribution (Elevated Volume)"
    elif avg_vol < -20:
        vol_regime = "Low conviction / Ranging (Depressed Volume)"
    else:
        vol_regime = "Average trading activity"

    # 4. Dominance (1.5% threshold — below this is intraday noise, not structural rotation)
    if data.btc_dominance_change_24h > 1.5:
        dom_regime = "Flight to safety / BTC outperformance"
    elif data.btc_dominance_change_24h < -1.5:
        dom_regime = "Risk-on / Altcoin rotation"
    else:
        dom_regime = "Stable dominance"

    return {
        "sentiment_regime": sentiment_regime,
        "trend_regime": trend_regime,
        "volume_regime": vol_regime,
        "dominance_regime": dom_regime,
        "fg_trajectory": _fg_trajectory(data),
        "altseason_signal": _altseason_signal(data),
        "btc_change_24h": short_term,
        "btc_change_7d": medium_term,
        "fg_value": fg,
    }


def detect_signals(data: MarketDataCache) -> list[Signal]:
    """Evaluate current market data against all signal patterns."""
    signals: list[Signal] = []

    # Fear capitulation: F&G < 25 + volume spike
    if data.fg_value < 25:
        avg_volume_change = _avg_volume_change(data)
        if avg_volume_change > 20:
            strength = _volume_strength(avg_volume_change)
            signals.append(
                Signal(
                    signal=SignalType.FEAR_CAPITULATION.value,
                    strength=strength,
                    description=f"F&G at {data.fg_value} with volume up {avg_volume_change:.0f}% — "
                    "historically a bottom signal",
                )
            )

    # Greed exhaustion: F&G > 75 + declining momentum
    if data.fg_value > 75:
        if data.fg_change_24h < 0:
            strength = _fg_magnitude_strength(abs(data.fg_change_24h))
            signals.append(
                Signal(
                    signal=SignalType.GREED_EXHAUSTION.value,
                    strength=strength,
                    description=(
                        f"F&G at {data.fg_value}, declining "
                        f"{abs(data.fg_change_24h):.0f} pts — exhaustion signal"
                    ),
                )
            )

    # BTC dominance shifts (>1.5% change in 24h = significant; below this is intraday noise)
    if data.btc_dominance_change_24h > 1.5:
        strength = _dominance_strength(data.btc_dominance_change_24h)
        signals.append(
            Signal(
                signal=SignalType.BTC_DOMINANCE_RISING.value,
                strength=strength,
                description=f"BTC dominance up {data.btc_dominance_change_24h:.1f}% in 24h — "
                "risk-off rotation, alts likely to underperform",
            )
        )

    if data.btc_dominance_change_24h < -1.5:
        strength = _dominance_strength(abs(data.btc_dominance_change_24h))
        signals.append(
            Signal(
                signal=SignalType.BTC_DOMINANCE_FALLING.value,
                strength=strength,
                description=f"BTC dominance down {abs(data.btc_dominance_change_24h):.1f}% in 24h — "
                "risk-on rotation, alt season signal",
            )
        )

    # Volume spike: avg volume change > 40%
    avg_vol = _avg_volume_change(data)
    if avg_vol > 40:
        strength = _volume_strength(avg_vol)
        signals.append(
            Signal(
                signal=SignalType.VOLUME_SPIKE.value,
                strength=strength,
                description=f"24h volume up {avg_vol:.0f}% — suggests forced selling or FOMO buying",
            )
        )

    # Volume dry-up: avg volume change < -30%
    if avg_vol < -30:
        strength = _volume_strength(abs(avg_vol))
        signals.append(
            Signal(
                signal=SignalType.VOLUME_DRY_UP.value,
                strength=strength,
                description=(
                    f"24h volume down {abs(avg_vol):.0f}% — low conviction, potential range-bound"
                ),
            )
        )

    return signals


def _avg_volume_change(data: MarketDataCache) -> float:
    """Average volume change across tracked assets."""
    changes = [
        data.btc_volume_change_24h,
        data.eth_volume_change_24h,
        data.sol_volume_change_24h,
    ]
    valid_changes = [c for c in changes if c is not None]
    if not valid_changes or all(c == 0.0 for c in valid_changes):
        return 0.0
    return sum(valid_changes) / len(valid_changes)


def _fg_trajectory(data: MarketDataCache) -> str:
    """Combine F&G zone + momentum into a single authoritative trajectory label."""
    fg = data.fg_value
    c24 = data.fg_change_24h
    c7d = data.fg_change_7d
    c30d = data.fg_change_30d

    if fg <= 24:  # Extreme Fear
        if c24 < -3:
            return "Extreme Fear Deepening"
        elif c24 > 3 or c7d > 5:
            return "Extreme Fear — Stabilizing"
        return "Extreme Fear Persisting"
    elif fg <= 45:  # Fear
        if c24 < -3:
            return "Fear Intensifying"
        elif c7d > 3 and c30d < -7:
            return "Fear — Recovery in Progress"
        elif c24 > 5:
            return "Fear Easing"
        return "Fear Consolidating"
    elif fg <= 54:  # Neutral
        if c24 > 3:
            return "Neutral — Greed Building"
        elif c24 < -3:
            return "Neutral — Softening"
        return "Neutral"
    elif fg <= 74:  # Greed
        if c24 > 3:
            return "Greed Building"
        elif c24 < -3:
            return "Greed Cooling"
        return "Greed Persisting"
    else:  # Extreme Greed
        if c24 < -3:
            return "Extreme Greed Cooling"
        elif c24 > 3:
            return "Extreme Greed Accelerating"
        return "Extreme Greed Persisting"


def _altseason_signal(data: MarketDataCache) -> str:
    """Derive BTC vs alts rotation signal from 7d dominance change."""
    dom7d = data.btc_dominance_change_7d
    if dom7d > 2.0:
        return f"BTC outperforming — dominance up {dom7d:.1f}% over 7d, alts facing headwinds"
    elif dom7d < -2.0:
        return f"Altcoin rotation signal — BTC dominance down {abs(dom7d):.1f}% over 7d"
    return "No rotation signal — dominance stable over 7d"


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
