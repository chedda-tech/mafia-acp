"""Tests for the fear_and_greed job handler and F&G classification."""

from src.data.models import MarketDataCache, classify_fg


class TestClassifyFG:
    def test_extreme_fear(self):
        assert classify_fg(0) == "extreme_fear"
        assert classify_fg(24) == "extreme_fear"

    def test_fear(self):
        assert classify_fg(25) == "fear"
        assert classify_fg(44) == "fear"

    def test_neutral(self):
        assert classify_fg(45) == "neutral"
        assert classify_fg(55) == "neutral"

    def test_greed(self):
        assert classify_fg(56) == "greed"
        assert classify_fg(74) == "greed"

    def test_extreme_greed(self):
        assert classify_fg(75) == "extreme_greed"
        assert classify_fg(100) == "extreme_greed"


class TestMarketDataCache:
    def test_get_price(self):
        data = MarketDataCache(btc_price=95000, eth_price=3200, sol_price=180)
        assert data.get_price("BTC") == 95000
        assert data.get_price("ETH") == 3200
        assert data.get_price("SOL") == 180
        assert data.get_price("DOGE") is None

    def test_get_price_case_insensitive(self):
        data = MarketDataCache(btc_price=95000)
        assert data.get_price("btc") == 95000
        assert data.get_price("Btc") == 95000

    def test_get_asset_data(self):
        data = MarketDataCache(
            btc_price=95000,
            btc_change_24h=-2.1,
            btc_change_7d=-5.4,
            btc_volume_24h=28_500_000_000,
            btc_volume_change_24h=45.2,
        )
        asset = data.get_asset_data("BTC")
        assert asset is not None
        assert asset["symbol"] == "BTC"
        assert asset["price"] == 95000
        assert asset["change_24h"] == -2.1
        assert asset["volume_24h"] == "28.5B"

    def test_get_asset_data_unknown(self):
        data = MarketDataCache()
        assert data.get_asset_data("DOGE") is None

    def test_default_values(self):
        data = MarketDataCache()
        assert data.fg_value == 50
        assert data.fg_classification == "neutral"
        assert data.btc_price == 0.0
