"""Tests for market_analysis helper functions and report building.

Covers _parse_requirements, _build_rotation_signal, _dominance_trend,
and _build_report (without LLM calls — include_analysis=False).
"""

import json

import pytest
from virtuals_acp.models import ACPJobPhase

from src.data.cache import DataCache
from src.data.models import MarketDataCache
from src.intelligence.market_analysis import (
    _build_report,
    _build_rotation_signal,
    _dominance_trend,
    _parse_requirements,
    handle_market_sentiment,
)
from src.intelligence.signal_detector import map_market_regime


# ---------------------------------------------------------------------------
# Minimal test double for ACPJob
# ---------------------------------------------------------------------------


class _DummyJob:
    def __init__(self, *, job_id: int, phase: ACPJobPhase = ACPJobPhase.TRANSACTION, context=None):
        self.id = job_id
        self.phase = phase
        self.context = context
        self.deliveries: list[str] = []
        self.accepted = False

    def accept(self, reason: str) -> None:
        self.accepted = True

    def deliver(self, payload: str) -> None:
        self.deliveries.append(payload)

    def get_service_name(self) -> str | None:
        return "market_sentiment"


# ---------------------------------------------------------------------------
# _parse_requirements
# ---------------------------------------------------------------------------


class TestParseRequirements:
    def test_none_context_returns_empty(self):
        job = _DummyJob(job_id=300, context=None)
        assert _parse_requirements(job) == {}

    def test_empty_dict_context_returns_empty(self):
        job = _DummyJob(job_id=301, context={})
        assert _parse_requirements(job) == {}

    def test_dict_context_direct(self):
        job = _DummyJob(job_id=302, context={"include_analysis": False, "focus_assets": ["BTC"]})
        result = _parse_requirements(job)
        assert result["include_analysis"] is False
        assert result["focus_assets"] == ["BTC"]

    def test_dict_context_nested_requirement(self):
        job = _DummyJob(
            job_id=303,
            context={"requirement": {"include_analysis": True, "focus_assets": ["ETH", "SOL"]}},
        )
        result = _parse_requirements(job)
        assert result["include_analysis"] is True
        assert "ETH" in result["focus_assets"]

    def test_string_context_json_parsed(self):
        payload = json.dumps({"focus_assets": ["BTC", "ETH"], "include_analysis": False})
        job = _DummyJob(job_id=304, context=payload)
        result = _parse_requirements(job)
        assert result["focus_assets"] == ["BTC", "ETH"]

    def test_invalid_string_context_returns_empty(self):
        job = _DummyJob(job_id=305, context="not valid json {{")
        assert _parse_requirements(job) == {}

    def test_nested_requirement_as_string(self):
        inner = json.dumps({"focus_assets": ["SOL"]})
        job = _DummyJob(job_id=306, context={"requirement": inner})
        result = _parse_requirements(job)
        assert result["focus_assets"] == ["SOL"]


# ---------------------------------------------------------------------------
# _dominance_trend
# ---------------------------------------------------------------------------


class TestDominanceTrend:
    def test_rising(self):
        assert _dominance_trend(0.5) == "rising"

    def test_falling(self):
        assert _dominance_trend(-0.5) == "falling"

    def test_stable_near_zero(self):
        assert _dominance_trend(0.0) == "stable"
        assert _dominance_trend(0.29) == "stable"
        assert _dominance_trend(-0.29) == "stable"

    def test_boundary_exactly_0_3_is_rising(self):
        assert _dominance_trend(0.3) == "stable"  # not strictly > 0.3

    def test_boundary_just_above_0_3_is_rising(self):
        assert _dominance_trend(0.31) == "rising"


# ---------------------------------------------------------------------------
# _build_rotation_signal
# ---------------------------------------------------------------------------


class TestBuildRotationSignal:
    def _regimes(self, data: MarketDataCache) -> dict:
        return map_market_regime(data)

    def test_btc_dominant(self):
        data = MarketDataCache(btc_dominance_change_7d=3.0)
        result = _build_rotation_signal(data, self._regimes(data))
        assert result["type"] == "btc_dominant"
        assert result["btc_dominance_change_7d"] == pytest.approx(3.0)

    def test_altseason(self):
        data = MarketDataCache(btc_dominance_change_7d=-3.0)
        result = _build_rotation_signal(data, self._regimes(data))
        assert result["type"] == "altseason"
        assert result["btc_dominance_change_7d"] == pytest.approx(-3.0)

    def test_no_rotation(self):
        data = MarketDataCache(btc_dominance_change_7d=1.0)
        result = _build_rotation_signal(data, self._regimes(data))
        assert result["type"] == "no_rotation"

    def test_includes_label_and_change(self):
        data = MarketDataCache(btc_dominance_change_7d=3.0)
        result = _build_rotation_signal(data, self._regimes(data))
        assert "label" in result
        assert "btc_dominance_change_7d" in result


# ---------------------------------------------------------------------------
# _build_report (include_analysis=False to avoid LLM/Settings calls)
# ---------------------------------------------------------------------------


class TestBuildReport:
    def test_report_has_required_top_level_keys(self):
        data = MarketDataCache(fg_value=45, btc_price=90000.0)
        report = _build_report(data, ["BTC", "ETH", "SOL"], include_analysis=False)
        for key in ("timestamp", "regimes", "fear_and_greed", "btc_dominance",
                    "rotation_signal", "total_market_cap", "assets", "source", "analysis"):
            assert key in report, f"Missing key: {key}"

    def test_analysis_is_none_when_excluded(self):
        data = MarketDataCache()
        report = _build_report(data, ["BTC"], include_analysis=False)
        assert report["analysis"] is None

    def test_fear_and_greed_value_matches_data(self):
        data = MarketDataCache(fg_value=22, fg_change_24h=-4.0)
        report = _build_report(data, [], include_analysis=False)
        assert report["fear_and_greed"]["value"] == 22
        assert report["fear_and_greed"]["change_24h"] == -4.0

    def test_assets_filtered_to_focus_list(self):
        data = MarketDataCache(btc_price=90000.0, eth_price=3000.0, sol_price=150.0)
        report = _build_report(data, ["BTC"], include_analysis=False)
        symbols = [a["symbol"] for a in report["assets"]]
        assert symbols == ["BTC"]
        assert "ETH" not in symbols

    def test_unknown_asset_excluded_silently(self):
        data = MarketDataCache()
        report = _build_report(data, ["BTC", "DOGE"], include_analysis=False)
        symbols = [a["symbol"] for a in report["assets"]]
        assert "DOGE" not in symbols

    def test_btc_dominance_trend_included(self):
        data = MarketDataCache(btc_dominance=52.0, btc_dominance_change_24h=0.5)
        report = _build_report(data, [], include_analysis=False)
        assert "trend" in report["btc_dominance"]
        assert report["btc_dominance"]["trend"] == "rising"

    def test_source_is_mafia_terminal(self):
        report = _build_report(MarketDataCache(), [], include_analysis=False)
        assert report["source"] == "mafia_terminal"


# ---------------------------------------------------------------------------
# handle_market_sentiment — TRANSACTION delivery (no polling thread)
# ---------------------------------------------------------------------------


class TestHandleMarketSentimentDelivery:
    def test_transaction_delivers_valid_json(self):
        """TRANSACTION phase should deliver a parseable JSON report."""
        cache = DataCache()
        job = _DummyJob(
            job_id=350,
            phase=ACPJobPhase.TRANSACTION,
            context={"requirement": {"include_analysis": False, "focus_assets": ["BTC"]}},
        )
        handle_market_sentiment(job, None, cache, object())
        assert len(job.deliveries) == 1
        payload = json.loads(job.deliveries[0])
        assert "fear_and_greed" in payload
        assert "source" in payload

    def test_transaction_deduplication(self):
        """Calling TRANSACTION handler twice for the same job should only deliver once."""
        cache = DataCache()
        job = _DummyJob(
            job_id=351,
            phase=ACPJobPhase.TRANSACTION,
            context={"requirement": {"include_analysis": False}},
        )
        handle_market_sentiment(job, None, cache, object())
        handle_market_sentiment(job, None, cache, object())
        assert len(job.deliveries) == 1
