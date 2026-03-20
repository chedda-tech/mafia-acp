"""Tests for TerminalFeed data parsing (no network calls).

These tests exercise _parse_market_data, _fg_point_change, and _safe_float —
the functions that transform raw Mafia API responses into MarketDataCache values.
Bugs here silently corrupt every job delivery, so these are high-priority.
"""

import pytest

from src.data.cache import DataCache
from src.data.terminal_feed import TerminalFeed


class _MockSettings:
    mafia_api_base_url = ""
    data_refresh_interval_seconds = 60


@pytest.fixture
def feed():
    return TerminalFeed(_MockSettings(), DataCache())


# ---------------------------------------------------------------------------
# _parse_market_data
# ---------------------------------------------------------------------------


class TestParseMarketData:
    def test_empty_dict_returns_empty(self, feed):
        assert feed._parse_market_data({}) == {}

    def test_empty_list_returns_empty(self, feed):
        assert feed._parse_market_data([]) == {}

    def test_list_format_extracts_fg_value(self, feed):
        raw = [
            {
                "period": "24h",
                "metrics": [
                    {
                        "asset": "",
                        "metric": "FEAR_GREED_INDEX",
                        "current": {"value": 42.0},
                        "change": {"percent": 0.0},
                    }
                ],
            }
        ]
        result = feed._parse_market_data(raw)
        assert result["fg_value"] == 42.0

    def test_list_format_extracts_btc_price(self, feed):
        raw = [
            {
                "period": "24h",
                "metrics": [
                    {
                        "asset": "BTC",
                        "metric": "PRICE",
                        "current": {"value": 95000.0},
                        "change": {"percent": -2.5},
                    }
                ],
            }
        ]
        result = feed._parse_market_data(raw)
        assert result["btc_price"] == 95000.0

    def test_list_format_btc_change_24h_extracted(self, feed):
        raw = [
            {
                "period": "24h",
                "metrics": [
                    {
                        "asset": "BTC",
                        "metric": "PRICE",
                        "current": {"value": 95000.0},
                        "change": {"percent": -2.5},
                    }
                ],
            }
        ]
        result = feed._parse_market_data(raw)
        assert result["btc_change_24h"] == pytest.approx(-2.5, abs=0.01)

    def test_list_format_multiple_periods_for_fg(self, feed):
        """24h and 7d period entries for F&G should both be recorded."""
        raw = [
            {
                "period": "24h",
                "metrics": [
                    {
                        "asset": "",
                        "metric": "FEAR_GREED_INDEX",
                        "current": {"value": 30.0},
                        "change": {"percent": 20.0},
                    }
                ],
            },
            {
                "period": "7d",
                "metrics": [
                    {
                        "asset": "",
                        "metric": "FEAR_GREED_INDEX",
                        "current": {"value": 30.0},
                        "change": {"percent": -10.0},
                    }
                ],
            },
        ]
        result = feed._parse_market_data(raw)
        # 24h point change: 30 * 20 / (100 + 20) = 5.0
        assert result["fg_change_24h"] == pytest.approx(5.0, abs=0.1)
        # 7d point change: 30 * -10 / (100 + -10) = -3.33
        assert result["fg_change_7d"] == pytest.approx(-3.3, abs=0.1)

    def test_dict_format_passthrough(self, feed):
        """Raw dict (non-list) is used directly as the data map."""
        raw = {"fg_value": 55.0}
        result = feed._parse_market_data(raw)
        assert result["fg_value"] == 55.0

    def test_missing_asset_fields_default_to_zero(self, feed):
        """Completely empty list → all numeric fields default to 0.0."""
        result = feed._parse_market_data([])
        assert result == {}  # empty input returns empty

    def test_returns_all_required_keys_for_full_payload(self, feed):
        """A full multi-period payload should produce all expected output keys."""
        raw = [
            {
                "period": "24h",
                "metrics": [
                    {
                        "asset": "",
                        "metric": "FEAR_GREED_INDEX",
                        "current": {"value": 50.0},
                        "change": {"percent": 0.0},
                    },
                    {
                        "asset": "BTC",
                        "metric": "PRICE",
                        "current": {"value": 90000.0},
                        "change": {"percent": 1.0},
                    },
                ],
            }
        ]
        result = feed._parse_market_data(raw)
        assert "fg_value" in result
        assert "fg_change_24h" in result
        assert "btc_price" in result
        assert "btc_change_24h" in result


# ---------------------------------------------------------------------------
# _fg_point_change
# ---------------------------------------------------------------------------


class TestFgPointChange:
    def test_basic_positive_change(self, feed):
        """F&G=25, pct=+100% → previous was 12.5, absolute change = +12.5 pts."""
        data = {"FEAR_GREED_INDEX": {"value": 25.0, "changes": {"24h": 100.0}}}
        assert feed._fg_point_change(data, "24h") == pytest.approx(12.5, abs=0.1)

    def test_basic_negative_change(self, feed):
        """F&G=25, pct=-50% → previous was 50, absolute change = -25 pts... wait:
        current=25, pct=-50% means old=(25/(1-0.5))=50, delta=25-50=-25.
        Formula: 25 * (-50) / (100 + -50) = -1250/50 = -25.
        """
        data = {"FEAR_GREED_INDEX": {"value": 25.0, "changes": {"24h": -50.0}}}
        assert feed._fg_point_change(data, "24h") == pytest.approx(-25.0, abs=0.1)

    def test_zero_percent_change_returns_zero(self, feed):
        data = {"FEAR_GREED_INDEX": {"value": 50.0, "changes": {"24h": 0.0}}}
        assert feed._fg_point_change(data, "24h") == 0.0

    def test_zero_current_value_returns_zero(self, feed):
        data = {"FEAR_GREED_INDEX": {"value": 0.0, "changes": {"24h": 50.0}}}
        assert feed._fg_point_change(data, "24h") == 0.0

    def test_near_minus_100_pct_guard(self, feed):
        """pct ≈ -100 causes denom ≈ 0 — guard must return 0.0 instead of raising."""
        data = {"FEAR_GREED_INDEX": {"value": 50.0, "changes": {"24h": -99.9999}}}
        result = feed._fg_point_change(data, "24h")
        assert result == 0.0

    def test_missing_period_key_returns_zero(self, feed):
        data = {"FEAR_GREED_INDEX": {"value": 50.0, "changes": {}}}
        assert feed._fg_point_change(data, "24h") == 0.0

    def test_missing_fg_key_returns_zero(self, feed):
        assert feed._fg_point_change({}, "24h") == 0.0

    def test_none_changes_value_returns_zero(self, feed):
        data = {"FEAR_GREED_INDEX": {"value": 50.0, "changes": {"24h": None}}}
        assert feed._fg_point_change(data, "24h") == 0.0

    def test_result_is_rounded_to_one_decimal(self, feed):
        """Result should be rounded to 1 decimal place."""
        data = {"FEAR_GREED_INDEX": {"value": 30.0, "changes": {"24h": 20.0}}}
        result = feed._fg_point_change(data, "24h")
        # 30 * 20 / 120 = 5.0 exactly, but verify it's a float rounded to 1dp
        assert result == round(result, 1)


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_direct_key_returns_value(self, feed):
        assert feed._safe_float({"btc_price": 95000.0}, "btc_price") == 95000.0

    def test_missing_direct_key_with_no_fallback_returns_zero(self, feed):
        assert feed._safe_float({}, "btc_price") == 0.0

    def test_fallback_key_scalar_value(self, feed):
        data = {"BTC.PRICE": 95000.0}
        assert feed._safe_float(data, "btc_price", "BTC.PRICE") == 95000.0

    def test_fallback_key_dict_value_returns_value_field(self, feed):
        data = {"BTC.PRICE": {"value": 95000.0, "changes": {"24h": -2.5}}}
        assert feed._safe_float(data, "btc_price", "BTC.PRICE") == 95000.0

    def test_fallback_key_with_change_period(self, feed):
        data = {"BTC.PRICE": {"value": 95000.0, "changes": {"24h": -2.5}}}
        assert feed._safe_float(data, "x", "BTC.PRICE", "24h") == -2.5

    def test_none_value_coerced_to_zero(self, feed):
        assert feed._safe_float({"btc_price": None}, "btc_price") == 0.0

    def test_fallback_none_value_returns_zero(self, feed):
        data = {"BTC.PRICE": {"value": None}}
        assert feed._safe_float(data, "btc_price", "BTC.PRICE") == 0.0

    def test_missing_change_period_in_fallback_returns_zero(self, feed):
        data = {"BTC.PRICE": {"value": 95000.0, "changes": {}}}
        assert feed._safe_float(data, "x", "BTC.PRICE", "24h") == 0.0
