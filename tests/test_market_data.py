"""
Tests for shared.market_data.

All yfinance calls are mocked — no network required.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from shared.market_data import (
    QuoteResult,
    _is_stale,
    _load_cache,
    _save_cache,
    _to_float,
    fetch_quotes,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_info(
    price: float = 1650.0,
    yield_: float = 0.012,
    high: float = 1800.0,
    low: float = 1400.0,
    payout: float = 0.15,
    name: str = "HDFC Bank Limited",
) -> dict:
    return {
        "currentPrice": price,
        "trailingAnnualDividendYield": yield_,
        "fiftyTwoWeekHigh": high,
        "fiftyTwoWeekLow": low,
        "payoutRatio": payout,
        "longName": name,
    }


def _mock_yf_ticker(info: dict) -> MagicMock:
    mock = MagicMock()
    mock.info = info
    return mock


def _cached_entry(ticker: str, price: float = 1650.0, hours_ago: float = 1.0) -> dict:
    """Build a raw cache dict entry that is `hours_ago` hours old."""
    fetched_at = (datetime.now() - timedelta(hours=hours_ago)).isoformat()
    return {
        "ticker": ticker,
        "price": price,
        "yield_pct": 1.2,
        "fifty_two_week_high": 1800.0,
        "fifty_two_week_low": 1400.0,
        "company_name": "HDFC Bank Limited",
        "payout_ratio_pct": 15.0,
        "error": None,
        "fetched_at": fetched_at,
    }


# ---------------------------------------------------------------------------
# QuoteResult properties
# ---------------------------------------------------------------------------

class TestQuoteResultProperties:
    def _result(self, **kwargs) -> QuoteResult:
        defaults = dict(
            ticker="HDFCBANK.NS",
            price=1650.0,
            yield_pct=1.2,
            fifty_two_week_high=1800.0,
            fifty_two_week_low=1400.0,
            company_name="HDFC Bank",
            payout_ratio_pct=15.0,
            error=None,
            fetched_at=datetime.now().isoformat(),
        )
        return QuoteResult(**{**defaults, **kwargs})

    def test_is_valid_true_when_price_and_no_error(self):
        assert self._result().is_valid is True

    def test_is_valid_false_when_error_set(self):
        assert self._result(error="timeout", price=None).is_valid is False

    def test_is_valid_false_when_price_none(self):
        assert self._result(price=None).is_valid is False

    def test_pct_below_52w_high(self):
        r = self._result(price=1650.0, fifty_two_week_high=1800.0)
        expected = (1800 - 1650) / 1800 * 100
        assert r.pct_below_52w_high == pytest.approx(expected, rel=1e-3)

    def test_pct_below_52w_high_none_when_price_missing(self):
        r = self._result(price=None, fifty_two_week_high=1800.0)
        assert r.pct_below_52w_high is None

    def test_pct_below_52w_high_none_when_high_missing(self):
        r = self._result(price=1650.0, fifty_two_week_high=None)
        assert r.pct_below_52w_high is None

    def test_pct_below_52w_high_none_when_high_is_zero(self):
        r = self._result(price=100.0, fifty_two_week_high=0.0)
        assert r.pct_below_52w_high is None


# ---------------------------------------------------------------------------
# _to_float
# ---------------------------------------------------------------------------

class TestToFloat:
    def test_converts_int(self):
        assert _to_float(1650) == pytest.approx(1650.0)

    def test_converts_float(self):
        assert _to_float(1650.5) == pytest.approx(1650.5)

    def test_none_returns_none(self):
        assert _to_float(None) is None

    def test_non_numeric_returns_none(self):
        assert _to_float("N/A") is None

    def test_string_number_converts(self):
        assert _to_float("1650.0") == pytest.approx(1650.0)


# ---------------------------------------------------------------------------
# _is_stale
# ---------------------------------------------------------------------------

class TestIsStale:
    def test_fresh_entry_not_stale(self):
        entry = {"fetched_at": datetime.now().isoformat()}
        assert _is_stale(entry, expiry_hours=24) is False

    def test_old_entry_is_stale(self):
        old = (datetime.now() - timedelta(hours=25)).isoformat()
        entry = {"fetched_at": old}
        assert _is_stale(entry, expiry_hours=24) is True

    def test_exactly_at_boundary_is_stale(self):
        # Slightly over the boundary
        at_boundary = (datetime.now() - timedelta(hours=24, seconds=1)).isoformat()
        entry = {"fetched_at": at_boundary}
        assert _is_stale(entry, expiry_hours=24) is True

    def test_missing_fetched_at_is_stale(self):
        assert _is_stale({}, expiry_hours=24) is True

    def test_invalid_datetime_is_stale(self):
        assert _is_stale({"fetched_at": "not-a-date"}, expiry_hours=24) is True


# ---------------------------------------------------------------------------
# _load_cache / _save_cache
# ---------------------------------------------------------------------------

class TestCacheIO:
    def test_load_missing_file(self, tmp_path):
        assert _load_cache(tmp_path / "nonexistent.json") == {}

    def test_load_corrupt_json(self, tmp_path):
        p = tmp_path / "cache.json"
        p.write_text("{ invalid json }", encoding="utf-8")
        assert _load_cache(p) == {}

    def test_roundtrip(self, tmp_path):
        p = tmp_path / "cache.json"
        data = {"HDFCBANK.NS": {"price": 1650.0}}
        _save_cache(p, data)
        assert _load_cache(p) == data

    def test_save_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "deep" / "nested" / "cache.json"
        _save_cache(p, {"x": 1})
        assert p.exists()

    def test_load_empty_file_treated_as_empty(self, tmp_path):
        p = tmp_path / "cache.json"
        p.write_text("", encoding="utf-8")
        assert _load_cache(p) == {}


# ---------------------------------------------------------------------------
# fetch_quotes — cache behaviour
# ---------------------------------------------------------------------------

class TestFetchQuotesCaching:
    TICKER = "HDFCBANK.NS"

    def test_cache_miss_calls_yfinance(self, tmp_path):
        cache = tmp_path / "cache.json"
        with patch("shared.market_data.yf.Ticker") as mock_cls:
            mock_cls.return_value = _mock_yf_ticker(_make_info())
            results = fetch_quotes([self.TICKER], cache, cache_expiry_hours=24)

        mock_cls.assert_called_once_with(self.TICKER)
        assert results[self.TICKER].is_valid

    def test_fresh_cache_skips_yfinance(self, tmp_path):
        cache = tmp_path / "cache.json"
        _save_cache(cache, {self.TICKER: _cached_entry(self.TICKER, hours_ago=1)})

        with patch("shared.market_data.yf.Ticker") as mock_cls:
            results = fetch_quotes([self.TICKER], cache, cache_expiry_hours=24)

        mock_cls.assert_not_called()
        assert results[self.TICKER].price == pytest.approx(1650.0)

    def test_stale_cache_refetches(self, tmp_path):
        cache = tmp_path / "cache.json"
        _save_cache(cache, {self.TICKER: _cached_entry(self.TICKER, hours_ago=25)})

        with patch("shared.market_data.yf.Ticker") as mock_cls:
            mock_cls.return_value = _mock_yf_ticker(_make_info(price=1700.0))
            results = fetch_quotes([self.TICKER], cache, cache_expiry_hours=24)

        mock_cls.assert_called_once()
        assert results[self.TICKER].price == pytest.approx(1700.0)

    def test_force_refresh_ignores_fresh_cache(self, tmp_path):
        cache = tmp_path / "cache.json"
        _save_cache(cache, {self.TICKER: _cached_entry(self.TICKER, hours_ago=1)})

        with patch("shared.market_data.yf.Ticker") as mock_cls:
            mock_cls.return_value = _mock_yf_ticker(_make_info(price=1750.0))
            results = fetch_quotes(
                [self.TICKER], cache, cache_expiry_hours=24, force_refresh=True
            )

        mock_cls.assert_called_once()
        assert results[self.TICKER].price == pytest.approx(1750.0)

    def test_cache_written_after_fetch(self, tmp_path):
        cache = tmp_path / "cache.json"
        with patch("shared.market_data.yf.Ticker") as mock_cls:
            mock_cls.return_value = _mock_yf_ticker(_make_info())
            fetch_quotes([self.TICKER], cache, cache_expiry_hours=24)

        saved = _load_cache(cache)
        assert self.TICKER in saved
        assert saved[self.TICKER]["price"] == pytest.approx(1650.0)

    def test_empty_ticker_list_returns_empty(self, tmp_path):
        cache = tmp_path / "cache.json"
        with patch("shared.market_data.yf.Ticker") as mock_cls:
            results = fetch_quotes([], cache, cache_expiry_hours=24)

        mock_cls.assert_not_called()
        assert results == {}

    def test_mixed_fresh_and_stale(self, tmp_path):
        cache = tmp_path / "cache.json"
        fresh_ticker = "ITC.NS"
        stale_ticker = "COALINDIA.NS"
        _save_cache(cache, {
            fresh_ticker: _cached_entry(fresh_ticker, hours_ago=1),
            stale_ticker: _cached_entry(stale_ticker, hours_ago=25),
        })

        with patch("shared.market_data.yf.Ticker") as mock_cls:
            mock_cls.return_value = _mock_yf_ticker(_make_info(price=999.0))
            fetch_quotes([fresh_ticker, stale_ticker], cache, cache_expiry_hours=24)

        # Only the stale ticker should have triggered a fetch
        mock_cls.assert_called_once_with(stale_ticker)

    def test_on_fetch_callback_called_for_live_fetches(self, tmp_path):
        cache = tmp_path / "cache.json"
        fetched = []
        with patch("shared.market_data.yf.Ticker") as mock_cls:
            mock_cls.return_value = _mock_yf_ticker(_make_info())
            fetch_quotes(
                [self.TICKER], cache, cache_expiry_hours=24,
                on_fetch=fetched.append,
            )
        assert fetched == [self.TICKER]

    def test_on_fetch_not_called_for_cached(self, tmp_path):
        cache = tmp_path / "cache.json"
        _save_cache(cache, {self.TICKER: _cached_entry(self.TICKER, hours_ago=1)})
        fetched = []
        with patch("shared.market_data.yf.Ticker"):
            fetch_quotes(
                [self.TICKER], cache, cache_expiry_hours=24,
                on_fetch=fetched.append,
            )
        assert fetched == []


# ---------------------------------------------------------------------------
# fetch_quotes — data correctness
# ---------------------------------------------------------------------------

class TestFetchQuotesData:
    TICKER = "HDFCBANK.NS"

    def _fetch(self, info: dict, tmp_path: Path) -> QuoteResult:
        with patch("shared.market_data.yf.Ticker") as mock_cls:
            mock_cls.return_value = _mock_yf_ticker(info)
            results = fetch_quotes([self.TICKER], tmp_path / "c.json", 24)
        return results[self.TICKER]

    def test_price_extracted_from_currentPrice(self, tmp_path):
        r = self._fetch(_make_info(price=1650.0), tmp_path)
        assert r.price == pytest.approx(1650.0)

    def test_price_falls_back_to_regularMarketPrice(self, tmp_path):
        info = _make_info()
        del info["currentPrice"]
        info["regularMarketPrice"] = 1620.0
        r = self._fetch(info, tmp_path)
        assert r.price == pytest.approx(1620.0)

    def test_yield_pct_converted_from_decimal(self, tmp_path):
        r = self._fetch(_make_info(yield_=0.012), tmp_path)
        assert r.yield_pct == pytest.approx(1.2)

    def test_payout_ratio_converted_from_decimal(self, tmp_path):
        r = self._fetch(_make_info(payout=0.15), tmp_path)
        assert r.payout_ratio_pct == pytest.approx(15.0)

    def test_52w_high_and_low_present(self, tmp_path):
        r = self._fetch(_make_info(high=1800.0, low=1400.0), tmp_path)
        assert r.fifty_two_week_high == pytest.approx(1800.0)
        assert r.fifty_two_week_low == pytest.approx(1400.0)

    def test_company_name_from_longName(self, tmp_path):
        r = self._fetch(_make_info(name="HDFC Bank Limited"), tmp_path)
        assert r.company_name == "HDFC Bank Limited"

    def test_company_name_falls_back_to_shortName(self, tmp_path):
        info = _make_info()
        del info["longName"]
        info["shortName"] = "HDFCBANK"
        r = self._fetch(info, tmp_path)
        assert r.company_name == "HDFCBANK"

    def test_missing_price_returns_error_result(self, tmp_path):
        info = _make_info()
        info["currentPrice"] = None
        info.pop("regularMarketPrice", None)
        r = self._fetch(info, tmp_path)
        assert not r.is_valid
        assert r.error is not None
        assert r.price is None

    def test_yfinance_exception_returns_error_result(self, tmp_path):
        with patch("shared.market_data.yf.Ticker") as mock_cls:
            mock_cls.side_effect = Exception("connection timeout")
            results = fetch_quotes([self.TICKER], tmp_path / "c.json", 24)
        r = results[self.TICKER]
        assert not r.is_valid
        assert "connection timeout" in r.error

    def test_zero_yield_handled(self, tmp_path):
        r = self._fetch(_make_info(yield_=0.0), tmp_path)
        assert r.yield_pct == pytest.approx(0.0)
        assert r.is_valid  # valid even with no dividend

    def test_none_yield_handled(self, tmp_path):
        info = _make_info()
        info["trailingAnnualDividendYield"] = None
        r = self._fetch(info, tmp_path)
        assert r.yield_pct == pytest.approx(0.0)
        assert r.is_valid

    def test_multiple_tickers_returned(self, tmp_path):
        tickers = ["HDFCBANK.NS", "ITC.NS"]
        with patch("shared.market_data.yf.Ticker") as mock_cls:
            mock_cls.return_value = _mock_yf_ticker(_make_info())
            results = fetch_quotes(tickers, tmp_path / "c.json", 24)
        assert set(results.keys()) == set(tickers)
