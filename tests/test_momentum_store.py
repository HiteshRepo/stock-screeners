"""Tests for momentum.store — SQLite OHLCV warehouse."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from momentum.store import DailyBar, PriceStore


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    s = PriceStore(tmp_path / "test.db")
    yield s
    s.close()


def _bar(
    symbol: str,
    d: date,
    close: float = 100.0,
    tv_cr: float = 5.0,
    series: str = "EQ",
) -> DailyBar:
    return DailyBar(
        symbol=symbol, date=d,
        open=close, high=close * 1.01, low=close * 0.99,
        close=close, volume=1_000_000, traded_value_cr=tv_cr,
        series=series,
    )


# ---------------------------------------------------------------------------
# Insert / mark
# ---------------------------------------------------------------------------

class TestInsertAndMark:
    def test_insert_returns_input_count(self, store):
        bars = [_bar("RELIANCE", date(2025, 1, 2))]
        assert store.insert_daily(bars) == 1

    def test_duplicate_insert_silently_ignored(self, store):
        bar = _bar("RELIANCE", date(2025, 1, 2))
        store.insert_daily([bar])
        # OR IGNORE — second call returns len(input), not actual inserted rows
        assert store.insert_daily([bar]) == 1

    def test_has_date_false_before_mark(self, store):
        assert not store.has_date(date(2025, 1, 2))

    def test_has_date_true_after_mark(self, store):
        store.mark_date_fetched(date(2025, 1, 2), 1500)
        assert store.has_date(date(2025, 1, 2))

    def test_mark_date_idempotent(self, store):
        store.mark_date_fetched(date(2025, 1, 2), 1000)
        store.mark_date_fetched(date(2025, 1, 2), 1500)  # OR REPLACE — should not raise
        assert store.has_date(date(2025, 1, 2))


# ---------------------------------------------------------------------------
# get_close_prices
# ---------------------------------------------------------------------------

class TestGetClosePrices:
    def test_returns_pivot_with_correct_values(self, store):
        store.insert_daily([
            _bar("TCS", date(2025, 1, 2), close=3500.0),
            _bar("TCS", date(2025, 1, 3), close=3520.0),
            _bar("INFY", date(2025, 1, 2), close=1800.0),
        ])
        df = store.get_close_prices(["TCS", "INFY"], date(2025, 1, 1), date(2025, 1, 5))
        assert "TCS" in df.columns
        assert "INFY" in df.columns
        assert df.loc["2025-01-02", "TCS"] == pytest.approx(3500.0)
        assert df.loc["2025-01-02", "INFY"] == pytest.approx(1800.0)
        assert df.loc["2025-01-03", "TCS"] == pytest.approx(3520.0)

    def test_filters_non_eq_series(self, store):
        eq_bar = _bar("TCS", date(2025, 1, 2), close=3500.0, series="EQ")
        # Non-EQ row would conflict on PK due to OR IGNORE, so use different date
        be_bar = _bar("TCS", date(2025, 1, 3), close=3490.0, series="BE")
        store.insert_daily([eq_bar, be_bar])
        df = store.get_close_prices(["TCS"], date(2025, 1, 1), date(2025, 1, 5))
        # BE-series row (2025-01-03) should not appear
        assert "2025-01-03" not in df.index

    def test_empty_for_missing_symbol(self, store):
        df = store.get_close_prices(["NONEXISTENT"], date(2025, 1, 1), date(2025, 1, 5))
        assert df.empty

    def test_empty_symbols_returns_empty(self, store):
        df = store.get_close_prices([], date(2025, 1, 1), date(2025, 1, 5))
        assert df.empty

    def test_date_range_filtered(self, store):
        store.insert_daily([
            _bar("TCS", date(2025, 1, 2)),
            _bar("TCS", date(2025, 2, 3)),
        ])
        df = store.get_close_prices(["TCS"], date(2025, 1, 1), date(2025, 1, 31))
        assert "2025-01-02" in df.index
        assert "2025-02-03" not in df.index


# ---------------------------------------------------------------------------
# get_avg_traded_value_cr
# ---------------------------------------------------------------------------

class TestGetAvgTradedValue:
    def test_returns_average_for_symbol(self, store):
        bars = [
            _bar("RELIANCE", date(2025, 1, d), tv_cr=float(d * 5))
            for d in range(2, 12)
        ]
        store.insert_daily(bars)
        avgs = store.get_avg_traded_value_cr(["RELIANCE"], date(2025, 1, 12))
        assert "RELIANCE" in avgs
        assert avgs["RELIANCE"] > 0

    def test_returns_empty_for_missing_symbols(self, store):
        avgs = store.get_avg_traded_value_cr(["NOSUCHSYMBOL"], date(2025, 1, 10))
        assert avgs == {} or avgs.get("NOSUCHSYMBOL", 0) == 0

    def test_empty_symbols_returns_empty(self, store):
        assert store.get_avg_traded_value_cr([], date(2025, 1, 10)) == {}


# ---------------------------------------------------------------------------
# get_symbols_with_min_history
# ---------------------------------------------------------------------------

class TestGetSymbolsWithMinHistory:
    def test_symbol_with_enough_history_included(self, store):
        for i in range(30):
            store.insert_daily([_bar("TCS", date(2025, 1, 1) + timedelta(days=i))])
        result = store.get_symbols_with_min_history(30, date(2025, 2, 1))
        assert "TCS" in result

    def test_symbol_with_too_little_history_excluded(self, store):
        for i in range(5):
            store.insert_daily([_bar("INFY", date(2025, 1, 1) + timedelta(days=i))])
        result = store.get_symbols_with_min_history(30, date(2025, 2, 1))
        assert "INFY" not in result


# ---------------------------------------------------------------------------
# get_available_dates
# ---------------------------------------------------------------------------

class TestGetAvailableDates:
    def test_returns_fetched_dates_in_range(self, store):
        store.mark_date_fetched(date(2025, 1, 2), 1500)
        store.mark_date_fetched(date(2025, 1, 3), 1500)
        store.mark_date_fetched(date(2025, 2, 1), 1500)

        dates = store.get_available_dates(date(2025, 1, 1), date(2025, 1, 31))
        assert date(2025, 1, 2) in dates
        assert date(2025, 1, 3) in dates
        assert date(2025, 2, 1) not in dates
