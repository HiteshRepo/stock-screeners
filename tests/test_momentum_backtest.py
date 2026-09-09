"""Tests for momentum.backtest — monthly rebalancing simulation."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from momentum.backtest import (
    BacktestResult,
    MonthlyResult,
    _end_of_month,
    _portfolio_return,
    _rebalance_dates,
    run_backtest,
)
from momentum.config import ScoringConfig
from momentum.store import DailyBar, PriceStore


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

class TestDateHelpers:
    def test_end_of_month_january(self):
        assert _end_of_month(date(2025, 1, 15)) == date(2025, 1, 31)

    def test_end_of_month_feb_non_leap(self):
        assert _end_of_month(date(2025, 2, 1)) == date(2025, 2, 28)

    def test_end_of_month_feb_leap(self):
        assert _end_of_month(date(2024, 2, 1)) == date(2024, 2, 29)

    def test_end_of_month_december(self):
        assert _end_of_month(date(2025, 12, 1)) == date(2025, 12, 31)

    def test_rebalance_dates_includes_end_of_months(self):
        dates = _rebalance_dates(date(2025, 1, 1), date(2025, 3, 31))
        assert date(2025, 1, 31) in dates
        assert date(2025, 2, 28) in dates
        assert date(2025, 3, 31) in dates

    def test_rebalance_dates_end_date_inclusive(self):
        dates = _rebalance_dates(date(2025, 1, 1), date(2025, 1, 31))
        assert date(2025, 1, 31) in dates

    def test_rebalance_dates_excludes_dates_beyond_end(self):
        dates = _rebalance_dates(date(2025, 1, 1), date(2025, 2, 15))
        # Feb 28 is beyond end_date=Feb 15, so only Jan 31 should be present
        assert date(2025, 1, 31) in dates
        assert date(2025, 2, 28) not in dates

    def test_rebalance_dates_generates_sequential_months(self):
        dates = _rebalance_dates(date(2025, 1, 1), date(2025, 6, 30))
        assert len(dates) == 6


# ---------------------------------------------------------------------------
# Backtest fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def bt_store(tmp_path):
    """
    PriceStore with 24 months of daily data for 5 symbols.
    RELIANCE is the strongest trend, ICICIBANK has a slight downtrend.
    """
    s = PriceStore(tmp_path / "bt.db")

    symbol_growth = {
        "RELIANCE": 0.0015,
        "TCS": 0.0010,
        "INFY": 0.0008,
        "HDFCBANK": 0.0003,
        "ICICIBANK": -0.0002,
    }
    prices = {sym: 1000.0 for sym in symbol_growth}
    start = date(2023, 1, 2)

    for i in range(750):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        bars = [
            DailyBar(
                symbol=sym, date=d,
                open=prices[sym], high=prices[sym] * 1.005,
                low=prices[sym] * 0.995, close=prices[sym],
                volume=2_000_000, traded_value_cr=15.0, series="EQ",
            )
            for sym in symbol_growth
        ]
        s.insert_daily(bars)
        s.mark_date_fetched(d, len(bars))
        for sym, g in symbol_growth.items():
            prices[sym] *= (1 + g)

    yield s
    s.close()


# ---------------------------------------------------------------------------
# _portfolio_return
# ---------------------------------------------------------------------------

class TestPortfolioReturn:
    def test_equal_weight_positive_trend(self, bt_store):
        ret = _portfolio_return(
            bt_store,
            ["RELIANCE", "TCS"],
            date(2023, 6, 30),
            date(2023, 7, 31),
        )
        assert isinstance(ret, float)
        assert ret > 0  # Both symbols have positive growth

    def test_missing_symbols_returns_zero(self, bt_store):
        ret = _portfolio_return(
            bt_store, ["NOSUCH1", "NOSUCH2"],
            date(2023, 6, 30), date(2023, 7, 31),
        )
        assert ret == pytest.approx(0.0)

    def test_empty_symbols_returns_zero(self, bt_store):
        ret = _portfolio_return(bt_store, [], date(2023, 6, 30), date(2023, 7, 31))
        assert ret == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# run_backtest
# ---------------------------------------------------------------------------

class TestRunBacktest:
    def _cfg(self, top_n: int = 3) -> ScoringConfig:
        return ScoringConfig(top_n=top_n, min_daily_traded_value_cr=5.0)

    def test_produces_monthly_results(self, bt_store):
        result = run_backtest(
            bt_store,
            ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"],
            date(2023, 6, 1), date(2024, 12, 31),
            self._cfg(),
        )
        assert isinstance(result, BacktestResult)
        assert len(result.monthly_results) >= 1

    def test_cagr_is_finite(self, bt_store):
        result = run_backtest(
            bt_store,
            ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"],
            date(2023, 6, 1), date(2024, 12, 31),
            self._cfg(),
        )
        assert isinstance(result.cagr, float)
        assert -1.0 < result.cagr < 100.0

    def test_max_drawdown_is_non_positive(self, bt_store):
        result = run_backtest(
            bt_store,
            ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"],
            date(2023, 6, 1), date(2024, 12, 31),
            self._cfg(),
        )
        assert result.max_drawdown <= 0.0

    def test_turnover_in_unit_interval(self, bt_store):
        result = run_backtest(
            bt_store,
            ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"],
            date(2023, 6, 1), date(2024, 12, 31),
            self._cfg(),
        )
        for mr in result.monthly_results:
            assert 0.0 <= mr.turnover <= 1.0

    def test_portfolio_values_start_at_one(self, bt_store):
        result = run_backtest(
            bt_store,
            ["RELIANCE", "TCS", "INFY"],
            date(2023, 6, 1), date(2024, 6, 30),
            self._cfg(),
        )
        assert result.portfolio_values[0] == pytest.approx(1.0)

    def test_total_months_matches_monthly_results(self, bt_store):
        result = run_backtest(
            bt_store,
            ["RELIANCE", "TCS", "INFY"],
            date(2023, 6, 1), date(2024, 6, 30),
            self._cfg(),
        )
        assert result.total_months == len(result.monthly_results)

    def test_survivorship_bias_note_present(self, bt_store):
        result = run_backtest(
            bt_store,
            ["RELIANCE", "TCS", "INFY"],
            date(2023, 6, 1), date(2024, 6, 30),
            self._cfg(),
        )
        assert "survivorship" in result.survivorship_bias_note.lower()

    def test_raises_for_range_too_short(self, bt_store):
        with pytest.raises(ValueError, match="≥2 rebalance dates"):
            run_backtest(
                bt_store, ["RELIANCE"],
                date(2024, 1, 5), date(2024, 1, 20),  # < 1 month
                self._cfg(),
            )

    def test_additions_and_removals_are_disjoint(self, bt_store):
        result = run_backtest(
            bt_store,
            ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"],
            date(2023, 6, 1), date(2024, 12, 31),
            self._cfg(top_n=2),
        )
        for mr in result.monthly_results:
            assert set(mr.additions).isdisjoint(set(mr.removals))
