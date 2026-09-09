"""Tests for momentum.scoring — momentum score calculation."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from momentum.config import ScoringConfig
from momentum.scoring import (
    MomentumScore,
    _detect_corporate_action,
    _dist_from_52w_high,
    _momentum_return,
    _pct_positive_days,
    _sharpe_ratio,
    _subtract_months,
    score_universe,
)
from momentum.store import DailyBar, PriceStore


# ---------------------------------------------------------------------------
# _subtract_months
# ---------------------------------------------------------------------------

class TestSubtractMonths:
    def test_basic_subtraction(self):
        assert _subtract_months(date(2025, 6, 15), 3) == date(2025, 3, 15)

    def test_crosses_year_boundary(self):
        assert _subtract_months(date(2025, 2, 28), 3) == date(2024, 11, 28)

    def test_clamps_to_end_of_month(self):
        # March 31 minus 1 month → Feb 28 (non-leap year)
        assert _subtract_months(date(2025, 3, 31), 1) == date(2025, 2, 28)

    def test_subtracts_twelve_months(self):
        assert _subtract_months(date(2025, 9, 30), 12) == date(2024, 9, 30)


# ---------------------------------------------------------------------------
# _detect_corporate_action
# ---------------------------------------------------------------------------

def _make_prices(closes: list[float], start: date | None = None) -> pd.Series:
    d = start or date(2024, 1, 2)
    idx = [d + timedelta(days=i) for i in range(len(closes))]
    return pd.Series(closes, index=[x.isoformat() for x in idx])


class TestDetectCorporateAction:
    def test_steady_uptrend_returns_false(self):
        closes = [100.0 + i * 0.3 for i in range(60)]
        assert not _detect_corporate_action(_make_prices(closes), 0.30)

    def test_35pct_jump_triggers_flag(self):
        closes = [100.0] * 30 + [135.0] + [135.0] * 29
        assert _detect_corporate_action(_make_prices(closes), 0.30)

    def test_35pct_drop_triggers_flag(self):
        closes = [100.0] * 30 + [65.0] + [65.0] * 29
        assert _detect_corporate_action(_make_prices(closes), 0.30)

    def test_below_threshold_does_not_trigger(self):
        # A 20% move should not trigger the 30% threshold
        closes = [100.0] * 30 + [120.0] + [120.0] * 29
        assert not _detect_corporate_action(_make_prices(closes), 0.30)


# ---------------------------------------------------------------------------
# _momentum_return
# ---------------------------------------------------------------------------

class TestMomentumReturn:
    def _cfg(self) -> ScoringConfig:
        return ScoringConfig(lookback_months=12, skip_recent_months=1)

    def _trending_prices(self, growth: float, n_months: int = 15) -> pd.Series:
        """n_months of daily prices starting from (today - n_months)."""
        start = _subtract_months(date(2025, 9, 30), n_months)
        closes = [100.0 * (1 + growth) ** i for i in range(n_months * 22)]
        return _make_prices(closes, start)

    def test_positive_trend_gives_positive_return(self):
        prices = self._trending_prices(0.001)
        result = _momentum_return(prices, self._cfg(), date(2025, 9, 30))
        assert result is not None
        assert result > 0

    def test_negative_trend_gives_negative_return(self):
        prices = self._trending_prices(-0.001)
        result = _momentum_return(prices, self._cfg(), date(2025, 9, 30))
        assert result is not None
        assert result < 0

    def test_insufficient_history_returns_none(self):
        prices = _make_prices([100.0, 101.0, 102.0])  # only 3 points
        result = _momentum_return(prices, self._cfg(), date(2025, 9, 30))
        assert result is None

    def test_empty_series_returns_none(self):
        prices = pd.Series([], dtype=float)
        assert _momentum_return(prices, self._cfg(), date(2025, 9, 30)) is None


# ---------------------------------------------------------------------------
# _pct_positive_days
# ---------------------------------------------------------------------------

class TestPctPositiveDays:
    def test_all_up_days_returns_near_one(self):
        closes = [100.0 + i for i in range(200)]
        prices = _make_prices(closes)
        result = _pct_positive_days(prices, 6, date(2024, 7, 20))
        assert result is not None
        assert result > 0.9

    def test_all_down_days_returns_near_zero(self):
        closes = [300.0 - i for i in range(200)]
        prices = _make_prices(closes)
        result = _pct_positive_days(prices, 6, date(2024, 7, 20))
        assert result is not None
        assert result < 0.1

    def test_insufficient_data_returns_none(self):
        prices = _make_prices([100.0, 101.0])  # < 10 points
        result = _pct_positive_days(prices, 6, date(2024, 1, 10))
        assert result is None


# ---------------------------------------------------------------------------
# _dist_from_52w_high
# ---------------------------------------------------------------------------

class TestDistFrom52wHigh:
    def test_at_all_time_high_returns_zero(self):
        # Price never falls — last close equals the 52w high
        closes = [100.0 + i for i in range(260)]
        prices = _make_prices(closes)
        as_of = date(2024, 1, 2) + timedelta(days=259)
        result = _dist_from_52w_high(prices, as_of)
        assert result is not None
        assert result == pytest.approx(0.0, abs=0.01)

    def test_below_high_returns_negative(self):
        closes = [100.0] * 130 + [80.0] * 130  # 20% below high
        prices = _make_prices(closes)
        as_of = date(2024, 1, 2) + timedelta(days=259)
        result = _dist_from_52w_high(prices, as_of)
        assert result is not None
        assert result < 0


# ---------------------------------------------------------------------------
# score_universe integration
# ---------------------------------------------------------------------------

@pytest.fixture
def populated_store(tmp_path):
    """PriceStore with 15 months of data for 3 symbols with different trends."""
    s = PriceStore(tmp_path / "scoring.db")

    growth = {"RELIANCE": 0.0015, "TCS": 0.0005, "INFY": -0.0002}
    prices = {sym: 1000.0 for sym in growth}

    start = date(2024, 1, 2)
    for i in range(400):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        bars = [
            DailyBar(
                symbol=sym, date=d,
                open=prices[sym], high=prices[sym] * 1.005,
                low=prices[sym] * 0.995, close=prices[sym],
                volume=1_000_000, traded_value_cr=10.0, series="EQ",
            )
            for sym in growth
        ]
        s.insert_daily(bars)
        s.mark_date_fetched(d, len(bars))
        for sym, g in growth.items():
            prices[sym] *= (1 + g)

    yield s
    s.close()


class TestScoreUniverse:
    def test_scores_known_symbols(self, populated_store):
        cfg = ScoringConfig(top_n=5, min_daily_traded_value_cr=5.0)
        scores = score_universe(
            populated_store, ["RELIANCE", "TCS", "INFY"],
            date(2025, 3, 31), cfg,
        )
        assert len(scores) >= 1
        assert all(isinstance(s, MomentumScore) for s in scores)

    def test_rank_1_has_highest_composite_score(self, populated_store):
        cfg = ScoringConfig(top_n=5, min_daily_traded_value_cr=5.0)
        scores = score_universe(
            populated_store, ["RELIANCE", "TCS", "INFY"],
            date(2025, 3, 31), cfg,
        )
        if len(scores) >= 2:
            assert scores[0].composite_score >= scores[1].composite_score

    def test_liquidity_filter_excludes_low_tv_symbols(self, populated_store):
        cfg = ScoringConfig(min_daily_traded_value_cr=999_999.0)
        scores = score_universe(
            populated_store, ["RELIANCE", "TCS"],
            date(2025, 3, 31), cfg,
        )
        assert scores == []

    def test_missing_symbol_skipped_gracefully(self, populated_store):
        cfg = ScoringConfig(top_n=5, min_daily_traded_value_cr=5.0)
        scores = score_universe(
            populated_store, ["RELIANCE", "NOSUCHSYMBOL"],
            date(2025, 3, 31), cfg,
        )
        syms = {s.symbol for s in scores}
        assert "NOSUCHSYMBOL" not in syms

    def test_secondary_filters_enabled(self, populated_store):
        cfg = ScoringConfig(
            top_n=5,
            min_daily_traded_value_cr=5.0,
            use_pct_positive_days=True,
            use_dist_from_52w_high=True,
            use_sharpe_ratio=True,
        )
        scores = score_universe(
            populated_store, ["RELIANCE", "TCS", "INFY"],
            date(2025, 3, 31), cfg,
        )
        # With secondary filters enabled, at least one result should populate them
        if scores:
            # Scores still have valid composite_score
            assert all(isinstance(s.composite_score, float) for s in scores)

    def test_scores_have_ranks_starting_at_1(self, populated_store):
        cfg = ScoringConfig(top_n=5, min_daily_traded_value_cr=5.0)
        scores = score_universe(
            populated_store, ["RELIANCE", "TCS", "INFY"],
            date(2025, 3, 31), cfg,
        )
        if scores:
            assert scores[0].rank == 1
            for i, s in enumerate(scores):
                assert s.rank == i + 1
