"""Tests for signal detection, market analysis, and AI narrator."""

from src.data.models import MarketDataCache, MarketOutlook
from src.intelligence.ai_narrator import _determine_outlook, _fallback_analysis
from src.intelligence.signal_detector import detect_signals


class TestSignalDetection:
    def test_fear_capitulation(self):
        """F&G < 25 + volume spike should trigger fear_capitulation."""
        data = MarketDataCache(
            fg_value=18,
            btc_volume_change_24h=50.0,
            eth_volume_change_24h=60.0,
            sol_volume_change_24h=45.0,
        )
        signals = detect_signals(data)
        signal_types = [s.signal for s in signals]
        assert "fear_capitulation" in signal_types

    def test_no_fear_capitulation_without_volume(self):
        """F&G < 25 but no volume spike should not trigger."""
        data = MarketDataCache(fg_value=18, btc_volume_change_24h=5.0)
        signals = detect_signals(data)
        signal_types = [s.signal for s in signals]
        assert "fear_capitulation" not in signal_types

    def test_greed_exhaustion(self):
        """F&G > 75 + declining momentum should trigger greed_exhaustion."""
        data = MarketDataCache(fg_value=82, fg_change_24h=-8)
        signals = detect_signals(data)
        signal_types = [s.signal for s in signals]
        assert "greed_exhaustion" in signal_types

    def test_no_greed_exhaustion_still_rising(self):
        """F&G > 75 but still rising should not trigger."""
        data = MarketDataCache(fg_value=82, fg_change_24h=3)
        signals = detect_signals(data)
        signal_types = [s.signal for s in signals]
        assert "greed_exhaustion" not in signal_types

    def test_btc_dominance_rising(self):
        data = MarketDataCache(btc_dominance_change_24h=1.5)
        signals = detect_signals(data)
        signal_types = [s.signal for s in signals]
        assert "btc_dominance_rising" in signal_types

    def test_btc_dominance_falling(self):
        data = MarketDataCache(btc_dominance_change_24h=-1.2)
        signals = detect_signals(data)
        signal_types = [s.signal for s in signals]
        assert "btc_dominance_falling" in signal_types

    def test_volume_spike(self):
        data = MarketDataCache(
            btc_volume_change_24h=50.0,
            eth_volume_change_24h=45.0,
            sol_volume_change_24h=55.0,
        )
        signals = detect_signals(data)
        signal_types = [s.signal for s in signals]
        assert "volume_spike" in signal_types

    def test_volume_dry_up(self):
        data = MarketDataCache(
            btc_volume_change_24h=-35.0,
            eth_volume_change_24h=-40.0,
            sol_volume_change_24h=-32.0,
        )
        signals = detect_signals(data)
        signal_types = [s.signal for s in signals]
        assert "volume_dry_up" in signal_types

    def test_no_signals_in_neutral_market(self):
        """Normal market conditions should produce no signals."""
        data = MarketDataCache(
            fg_value=50,
            fg_change_24h=1,
            btc_dominance_change_24h=0.1,
            btc_volume_change_24h=5.0,
            eth_volume_change_24h=3.0,
            sol_volume_change_24h=-2.0,
        )
        signals = detect_signals(data)
        assert len(signals) == 0

    def test_signal_strength_strong(self):
        """High magnitude should produce strong signals."""
        data = MarketDataCache(
            fg_value=10,
            btc_volume_change_24h=70.0,
            eth_volume_change_24h=65.0,
            sol_volume_change_24h=80.0,
        )
        signals = detect_signals(data)
        fear_signals = [s for s in signals if s.signal == "fear_capitulation"]
        assert len(fear_signals) == 1
        assert fear_signals[0].strength == "strong"


class TestFallbackAnalysis:
    def test_returns_summary(self):
        data = MarketDataCache(fg_value=22, fg_classification="extreme_fear", fg_change_24h=-7)
        signals = detect_signals(data)
        result = _fallback_analysis(data, signals)
        assert "summary" in result
        assert "signals" in result
        assert "outlook" in result
        assert "22" in result["summary"]

    def test_outlook_fear_capitulation(self):
        from src.data.models import Signal
        signals = [Signal(signal="fear_capitulation", strength="strong", description="test")]
        data = MarketDataCache(fg_value=18)
        outlook = _determine_outlook(data, signals)
        assert outlook == MarketOutlook.BEARISH_SHORT_BULLISH_MEDIUM.value

    def test_outlook_neutral(self):
        data = MarketDataCache(fg_value=50)
        outlook = _determine_outlook(data, [])
        assert outlook == MarketOutlook.NEUTRAL.value
