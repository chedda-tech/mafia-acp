"""Tests for signal detection, market analysis, and AI narrator."""

from src.data.models import MarketDataCache
from src.intelligence.ai_narrator import (
    _TRAJECTORY_INSIGHTS,
    _build_llm_context,
    _fallback_analysis,
    _is_sentiment_consistent,
    _trajectory_insight,
)
from src.intelligence.signal_detector import (
    _altseason_signal,
    _dominance_strength,
    _fg_magnitude_strength,
    _fg_trajectory,
    detect_signals,
    map_market_regime,
)


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
        data = MarketDataCache(btc_dominance_change_24h=2.0)
        signals = detect_signals(data)
        signal_types = [s.signal for s in signals]
        assert "btc_dominance_rising" in signal_types

    def test_btc_dominance_falling(self):
        data = MarketDataCache(btc_dominance_change_24h=-2.0)
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
    def test_returns_structured_output(self):
        data = MarketDataCache(fg_value=22, fg_classification="extreme_fear", fg_change_24h=-7)
        signals = detect_signals(data)
        result = _fallback_analysis(data, signals)
        assert "overview" in result
        assert "analysis" in result
        assert "insight" in result
        assert "signals" in result
        assert "regime" in result
        assert "22" in result["overview"]

    def test_insight_is_contrarian_in_fear(self):
        data = MarketDataCache(fg_value=10, fg_change_24h=-5)
        signals = detect_signals(data)
        result = _fallback_analysis(data, signals)
        # Insight should be non-empty and not just repeat the numbers
        assert len(result["insight"]) > 20
        assert "10" not in result["insight"]  # insight shouldn't regurgitate the F&G number

    def test_btc_change_included_in_overview_when_nonzero(self):
        data = MarketDataCache(fg_value=50, btc_change_24h=-3.5)
        result = _fallback_analysis(data, [])
        assert "3.5" in result["overview"]

    def test_overview_omits_btc_when_zero(self):
        data = MarketDataCache(fg_value=50, btc_change_24h=0.0)
        result = _fallback_analysis(data, [])
        assert "BTC" not in result["overview"]

    def test_overview_includes_dominance_when_nonzero(self):
        data = MarketDataCache(fg_value=50, btc_dominance=52.0, btc_dominance_change_24h=0.8)
        result = _fallback_analysis(data, [])
        assert "dominance" in result["overview"].lower()
        assert "52.0%" in result["overview"]

    def test_signals_list_serialised(self):
        data = MarketDataCache(fg_value=10, btc_volume_change_24h=80.0, eth_volume_change_24h=70.0, sol_volume_change_24h=75.0)
        signals = detect_signals(data)
        result = _fallback_analysis(data, signals)
        assert isinstance(result["signals"], list)
        assert all("signal" in s for s in result["signals"])


class TestTrajectoryInsight:
    def test_every_trajectory_key_returns_non_empty_string(self):
        for key in _TRAJECTORY_INSIGHTS:
            insight = _trajectory_insight(key)
            assert isinstance(insight, str) and len(insight) > 10, f"Empty insight for '{key}'"

    def test_unknown_trajectory_returns_default(self):
        result = _trajectory_insight("Some Unknown State")
        assert "discipline" in result.lower() or "signal" in result.lower()

    def test_extreme_fear_deepening_is_contrarian(self):
        result = _trajectory_insight("Extreme Fear Deepening")
        # Should reference bottoms or historical context — contrarian framing
        assert "bottom" in result.lower() or "historical" in result.lower() or "cycle" in result.lower()

    def test_extreme_greed_insight_warns_of_risk(self):
        result = _trajectory_insight("Extreme Greed Accelerating")
        assert "euphoric" in result.lower() or "smart money" in result.lower() or "crowd" in result.lower()


class TestBuildLlmContext:
    def test_returns_market_state_and_signals(self):
        data = MarketDataCache(fg_value=30, btc_change_24h=-2.0, btc_change_7d=3.0)
        from src.intelligence.signal_detector import map_market_regime
        regimes = map_market_regime(data)
        signals = detect_signals(data)
        ctx = _build_llm_context(regimes, signals)
        assert "market_state" in ctx
        assert "signals" in ctx

    def test_market_state_contains_required_fields(self):
        data = MarketDataCache(fg_value=50, btc_change_24h=1.0, btc_change_7d=2.0)
        from src.intelligence.signal_detector import map_market_regime
        regimes = map_market_regime(data)
        ctx = _build_llm_context(regimes, [])
        ms = ctx["market_state"]
        assert "fear_and_greed" in ms
        assert "trend" in ms
        assert "volume" in ms
        assert "dominance" in ms
        assert "rotation_outlook" in ms
        assert "btc_performance" in ms

    def test_btc_performance_shows_direction(self):
        data = MarketDataCache(fg_value=50, btc_change_24h=-2.5, btc_change_7d=5.1)
        from src.intelligence.signal_detector import map_market_regime
        regimes = map_market_regime(data)
        ctx = _build_llm_context(regimes, [])
        perf = ctx["market_state"]["btc_performance"]
        assert "-2.5%" in perf
        assert "+5.1%" in perf


class TestIsSentimentConsistent:
    def test_allows_neutral_trajectory(self):
        result = {"overview": "F&G at 50.", "insight": "No strong edge."}
        regimes = {"fg_trajectory": "Neutral"}
        assert _is_sentiment_consistent(result, regimes) is True

    def test_blocks_bullish_in_fear_deepening(self):
        result = {"overview": "F&G at 10.", "insight": "This is a bullish setup."}
        regimes = {"fg_trajectory": "Extreme Fear Deepening"}
        assert _is_sentiment_consistent(result, regimes) is False

    def test_blocks_bullish_in_fear_intensifying(self):
        result = {"overview": "Market dropped.", "insight": "Bullish divergence visible."}
        regimes = {"fg_trajectory": "Fear Intensifying"}
        assert _is_sentiment_consistent(result, regimes) is False

    def test_allows_non_bullish_in_fear_deepening(self):
        result = {"overview": "Capitulation.", "insight": "Keep powder dry."}
        regimes = {"fg_trajectory": "Extreme Fear Deepening"}
        assert _is_sentiment_consistent(result, regimes) is True

    def test_allows_bullish_in_greed_trajectory(self):
        """In a greed trajectory, 'bullish' in the response is not contradictory."""
        result = {"overview": "Bullish momentum.", "insight": "Stay disciplined."}
        regimes = {"fg_trajectory": "Greed Building"}
        assert _is_sentiment_consistent(result, regimes) is True


class TestMapMarketRegime:
    def test_extreme_fear_regime(self):
        data = MarketDataCache(fg_value=10)
        regime = map_market_regime(data)
        assert regime["sentiment_regime"] == "Extreme Fear"

    def test_extreme_greed_regime(self):
        data = MarketDataCache(fg_value=90)
        regime = map_market_regime(data)
        assert regime["sentiment_regime"] == "Extreme Greed"

    def test_neutral_regime(self):
        data = MarketDataCache(fg_value=50)
        regime = map_market_regime(data)
        assert regime["sentiment_regime"] == "Neutral"

    def test_bullish_trend_regime(self):
        data = MarketDataCache(btc_change_24h=2.0, btc_change_7d=5.0)
        regime = map_market_regime(data)
        assert "Bullish" in regime["trend_regime"]

    def test_pullback_in_uptrend_regime(self):
        data = MarketDataCache(btc_change_24h=-1.0, btc_change_7d=8.0)
        regime = map_market_regime(data)
        assert "pullback" in regime["trend_regime"].lower()

    def test_high_volume_regime(self):
        data = MarketDataCache(
            btc_volume_change_24h=50.0,
            eth_volume_change_24h=45.0,
            sol_volume_change_24h=40.0,
        )
        regime = map_market_regime(data)
        assert "Elevated" in regime["volume_regime"]

    def test_depressed_volume_regime(self):
        data = MarketDataCache(
            btc_volume_change_24h=-40.0,
            eth_volume_change_24h=-35.0,
            sol_volume_change_24h=-30.0,
        )
        regime = map_market_regime(data)
        assert "Depressed" in regime["volume_regime"]

    def test_btc_dominance_flight_to_safety(self):
        data = MarketDataCache(btc_dominance_change_24h=2.0)
        regime = map_market_regime(data)
        assert "safety" in regime["dominance_regime"].lower()

    def test_btc_dominance_risk_on(self):
        data = MarketDataCache(btc_dominance_change_24h=-2.0)
        regime = map_market_regime(data)
        assert "Risk-on" in regime["dominance_regime"]

    def test_returns_all_expected_keys(self):
        data = MarketDataCache()
        regime = map_market_regime(data)
        expected = {"sentiment_regime", "trend_regime", "volume_regime", "dominance_regime",
                    "fg_trajectory", "altseason_signal", "btc_change_24h", "btc_change_7d", "fg_value"}
        assert expected.issubset(set(regime.keys()))


class TestFgTrajectory:
    def test_extreme_fear_deepening(self):
        data = MarketDataCache(fg_value=15, fg_change_24h=-5)
        assert _fg_trajectory(data) == "Extreme Fear Deepening"

    def test_extreme_fear_stabilizing(self):
        data = MarketDataCache(fg_value=20, fg_change_24h=5)
        assert _fg_trajectory(data) == "Extreme Fear — Stabilizing"

    def test_extreme_fear_persisting(self):
        data = MarketDataCache(fg_value=20, fg_change_24h=1)
        assert _fg_trajectory(data) == "Extreme Fear Persisting"

    def test_fear_intensifying(self):
        data = MarketDataCache(fg_value=35, fg_change_24h=-5)
        assert _fg_trajectory(data) == "Fear Intensifying"

    def test_fear_easing(self):
        data = MarketDataCache(fg_value=35, fg_change_24h=6)
        assert _fg_trajectory(data) == "Fear Easing"

    def test_fear_consolidating(self):
        data = MarketDataCache(fg_value=35, fg_change_24h=1)
        assert _fg_trajectory(data) == "Fear Consolidating"

    def test_neutral_greed_building(self):
        data = MarketDataCache(fg_value=50, fg_change_24h=4)
        assert _fg_trajectory(data) == "Neutral — Greed Building"

    def test_neutral_softening(self):
        data = MarketDataCache(fg_value=50, fg_change_24h=-4)
        assert _fg_trajectory(data) == "Neutral — Softening"

    def test_neutral(self):
        data = MarketDataCache(fg_value=50, fg_change_24h=1)
        assert _fg_trajectory(data) == "Neutral"

    def test_greed_building(self):
        data = MarketDataCache(fg_value=65, fg_change_24h=5)
        assert _fg_trajectory(data) == "Greed Building"

    def test_greed_cooling(self):
        data = MarketDataCache(fg_value=65, fg_change_24h=-4)
        assert _fg_trajectory(data) == "Greed Cooling"

    def test_extreme_greed_accelerating(self):
        data = MarketDataCache(fg_value=85, fg_change_24h=5)
        assert _fg_trajectory(data) == "Extreme Greed Accelerating"

    def test_extreme_greed_cooling(self):
        data = MarketDataCache(fg_value=85, fg_change_24h=-5)
        assert _fg_trajectory(data) == "Extreme Greed Cooling"

    def test_extreme_greed_persisting(self):
        data = MarketDataCache(fg_value=85, fg_change_24h=1)
        assert _fg_trajectory(data) == "Extreme Greed Persisting"


class TestAltseasonSignal:
    def test_btc_dominant(self):
        data = MarketDataCache(btc_dominance_change_7d=3.0)
        result = _altseason_signal(data)
        assert "BTC outperforming" in result
        assert "3.0%" in result

    def test_altcoin_rotation(self):
        data = MarketDataCache(btc_dominance_change_7d=-3.0)
        result = _altseason_signal(data)
        assert "Altcoin rotation" in result
        assert "3.0%" in result

    def test_no_rotation(self):
        data = MarketDataCache(btc_dominance_change_7d=1.0)
        result = _altseason_signal(data)
        assert "No rotation" in result


class TestMapMarketRegimeAdditional:
    def test_relief_bounce_in_downtrend(self):
        """Short-term positive + medium-term negative = relief bounce."""
        data = MarketDataCache(btc_change_24h=2.0, btc_change_7d=-5.0)
        regime = map_market_regime(data)
        assert "relief bounce" in regime["trend_regime"].lower()

    def test_capitulation_when_both_negative(self):
        data = MarketDataCache(btc_change_24h=-3.0, btc_change_7d=-7.0)
        regime = map_market_regime(data)
        assert "Capitulation" in regime["trend_regime"]

    def test_fg_trajectory_fear_recovery_in_progress(self):
        """c7d > 3 and c30d < -7 in Fear zone → Recovery in Progress."""
        data = MarketDataCache(fg_value=35, fg_change_24h=1, fg_change_7d=5.0, fg_change_30d=-10.0)
        assert _fg_trajectory(data) == "Fear — Recovery in Progress"

    def test_greed_exhaustion_strength_strong(self):
        """F&G > 75 + large decline → strong greed_exhaustion signal."""
        data = MarketDataCache(fg_value=82, fg_change_24h=-12)
        signals = detect_signals(data)
        greed_signals = [s for s in signals if s.signal == "greed_exhaustion"]
        assert len(greed_signals) == 1
        assert greed_signals[0].strength == "strong"

    def test_greed_exhaustion_strength_moderate(self):
        data = MarketDataCache(fg_value=82, fg_change_24h=-6)
        signals = detect_signals(data)
        greed_signals = [s for s in signals if s.signal == "greed_exhaustion"]
        assert greed_signals[0].strength == "moderate"

    def test_btc_dominance_rising_strength_strong(self):
        """Dominance change >= 2.0 → strong signal."""
        data = MarketDataCache(btc_dominance_change_24h=2.5)
        signals = detect_signals(data)
        dom_signals = [s for s in signals if s.signal == "btc_dominance_rising"]
        assert dom_signals[0].strength == "strong"

    def test_btc_dominance_rising_strength_moderate(self):
        """Dominance change 1.5–2.0 → moderate signal."""
        data = MarketDataCache(btc_dominance_change_24h=1.8)
        signals = detect_signals(data)
        dom_signals = [s for s in signals if s.signal == "btc_dominance_rising"]
        assert dom_signals[0].strength == "moderate"

    def test_greed_sentiment_regime(self):
        """fg_value 55–74 should map to 'Greed' sentiment regime."""
        data = MarketDataCache(fg_value=65)
        regime = map_market_regime(data)
        assert regime["sentiment_regime"] == "Greed"

    def test_greed_persisting_trajectory(self):
        """F&G in greed zone with small change → Greed Persisting."""
        data = MarketDataCache(fg_value=65, fg_change_24h=1)
        assert _fg_trajectory(data) == "Greed Persisting"

    def test_greed_exhaustion_strength_weak(self):
        """Small F&G decline in extreme greed → weak greed_exhaustion signal."""
        data = MarketDataCache(fg_value=80, fg_change_24h=-2)
        signals = detect_signals(data)
        greed_signals = [s for s in signals if s.signal == "greed_exhaustion"]
        assert len(greed_signals) == 1
        assert greed_signals[0].strength == "weak"

    def test_fg_magnitude_strength_weak_branch(self):
        assert _fg_magnitude_strength(3.0) == "weak"

    def test_dominance_strength_weak_branch(self):
        """Change < 1.0 maps to weak — covers the function's third tier."""
        assert _dominance_strength(0.5) == "weak"

