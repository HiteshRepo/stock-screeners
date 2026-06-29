"""Tests for dividend.scoring — candidate scoring and rationale."""
from __future__ import annotations

from datetime import datetime

import pytest

from dividend.md_io import Holding, WatchlistItem
from dividend.scoring import CandidateScore, build_rationale, score_candidates
from shared.market_data import QuoteResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _holding(ticker="HDFCBANK", sector="Banking", total_invested=16500.0) -> Holding:
    return Holding(ticker, "HDFC Bank", sector, 10.0, 1650.0, total_invested,
                   "2024-01-01", "", "", 1.2)


def _item(ticker="ITC", sector="FMCG", yield_pct=3.4) -> WatchlistItem:
    return WatchlistItem(ticker, "ITC Ltd", sector, yield_pct, 80.0, "", "2024-01-01")


def _quote(ticker, price=420.0, yield_pct=3.4, high=500.0, low=350.0) -> QuoteResult:
    return QuoteResult(
        ticker=ticker,
        price=price,
        yield_pct=yield_pct,
        fifty_two_week_high=high,
        fifty_two_week_low=low,
        company_name="ITC Ltd",
        payout_ratio_pct=80.0,
        error=None,
        fetched_at=datetime.now().isoformat(),
    )


def _error_quote(ticker) -> QuoteResult:
    return QuoteResult(ticker, None, None, None, None, None, None,
                       "No price data", datetime.now().isoformat())


# ---------------------------------------------------------------------------
# score_candidates — filtering
# ---------------------------------------------------------------------------

class TestScoreCandidatesFiltering:
    def test_empty_watchlist_returns_empty(self):
        assert score_candidates([], {}, [], budget=25000) == []

    def test_excludes_invalid_quotes(self):
        item = _item()
        quotes = {item.ns_ticker: _error_quote(item.ns_ticker)}
        result = score_candidates([item], quotes, [], budget=25000)
        assert result == []

    def test_excludes_tickers_missing_from_quotes(self):
        item = _item()
        result = score_candidates([item], {}, [], budget=25000)
        assert result == []

    def test_excludes_items_above_budget(self):
        item = _item()
        quotes = {item.ns_ticker: _quote(item.ns_ticker, price=30000.0)}
        result = score_candidates([item], quotes, [], budget=25000)
        assert result == []

    def test_includes_item_exactly_at_budget(self):
        item = _item()
        quotes = {item.ns_ticker: _quote(item.ns_ticker, price=25000.0)}
        result = score_candidates([item], quotes, [], budget=25000)
        assert len(result) == 1

    def test_multiple_items_only_affordable_included(self):
        cheap = _item("ITC", "FMCG", 3.4)
        expensive = _item("MRF", "Auto", 1.0)
        quotes = {
            cheap.ns_ticker: _quote(cheap.ns_ticker, price=420.0),
            expensive.ns_ticker: _quote(expensive.ns_ticker, price=100000.0),
        }
        result = score_candidates([cheap, expensive], quotes, [], budget=5000)
        assert len(result) == 1
        assert result[0].item.ticker == "ITC"


# ---------------------------------------------------------------------------
# score_candidates — scoring correctness
# ---------------------------------------------------------------------------

class TestScoreCandidatesScoring:
    def test_sorted_by_total_score_descending(self):
        items = [_item("A", "FMCG", 1.0), _item("B", "Mining", 5.0)]
        quotes = {
            "A.NS": _quote("A.NS", price=100.0, yield_pct=1.0),
            "B.NS": _quote("B.NS", price=100.0, yield_pct=5.0),
        }
        result = score_candidates(items, quotes, [], budget=10000)
        assert result[0].total_score >= result[1].total_score

    def test_higher_yield_gets_higher_yield_score(self):
        items = [_item("LOW", "FMCG", 1.0), _item("HIGH", "FMCG", 5.0)]
        quotes = {
            "LOW.NS": _quote("LOW.NS", price=100.0, yield_pct=1.0),
            "HIGH.NS": _quote("HIGH.NS", price=100.0, yield_pct=5.0),
        }
        result_map = {r.item.ticker: r for r in score_candidates(items, quotes, [], 10000)}
        assert result_map["HIGH"].yield_score > result_map["LOW"].yield_score

    def test_max_yield_item_gets_yield_score_1(self):
        items = [_item("A", "FMCG", 2.0), _item("B", "FMCG", 8.0)]
        quotes = {
            "A.NS": _quote("A.NS", price=100.0, yield_pct=2.0),
            "B.NS": _quote("B.NS", price=100.0, yield_pct=8.0),
        }
        result_map = {r.item.ticker: r for r in score_candidates(items, quotes, [], 10000)}
        assert result_map["B"].yield_score == pytest.approx(1.0)

    def test_sector_not_in_portfolio_gets_max_div_score(self):
        item = _item("ITC", "FMCG")
        holdings = [_holding("HDFCBANK", "Banking", 16500.0)]
        quotes = {"ITC.NS": _quote("ITC.NS")}
        result = score_candidates([item], quotes, holdings, 10000)
        # FMCG not in portfolio (only Banking) → div_score = 1.0
        assert result[0].div_score == pytest.approx(1.0)

    def test_sector_100pct_of_portfolio_gets_zero_div_score(self):
        item = _item("ITC2", "Banking")  # same sector as only holding
        holdings = [_holding("HDFCBANK", "Banking", 16500.0)]  # 100% Banking
        quotes = {"ITC2.NS": _quote("ITC2.NS")}
        result = score_candidates([item], quotes, holdings, 10000)
        assert result[0].div_score == pytest.approx(0.0)

    def test_empty_portfolio_all_sectors_get_max_div_score(self):
        item = _item()
        quotes = {"ITC.NS": _quote("ITC.NS")}
        result = score_candidates([item], quotes, holdings=[], budget=10000)
        assert result[0].div_score == pytest.approx(1.0)

    def test_deeper_52w_discount_gets_higher_value_score(self):
        items = [_item("A", "FMCG"), _item("B", "FMCG")]
        # A is 5% below 52w high, B is 25% below
        quotes = {
            "A.NS": _quote("A.NS", price=475.0, yield_pct=3.4, high=500.0),
            "B.NS": _quote("B.NS", price=375.0, yield_pct=3.4, high=500.0),
        }
        result_map = {r.item.ticker: r for r in score_candidates(items, quotes, [], 10000)}
        assert result_map["B"].value_score > result_map["A"].value_score

    def test_max_affordable_shares_calculated(self):
        item = _item()
        quotes = {"ITC.NS": _quote("ITC.NS", price=420.0)}
        result = score_candidates([item], quotes, [], budget=5000)
        assert result[0].max_shares == 11  # floor(5000/420) = 11

    def test_already_held_shares_populated(self):
        item = _item("HDFCBANK", "Banking")
        holdings = [_holding("HDFCBANK", "Banking")]
        quotes = {"HDFCBANK.NS": _quote("HDFCBANK.NS")}
        result = score_candidates([item], quotes, holdings, 25000)
        assert result[0].already_held_shares == 10.0

    def test_not_held_shows_zero_already_held(self):
        item = _item("ITC", "FMCG")
        holdings = [_holding("HDFCBANK", "Banking")]
        quotes = {"ITC.NS": _quote("ITC.NS")}
        result = score_candidates([item], quotes, holdings, 25000)
        assert result[0].already_held_shares == 0.0

    def test_total_score_is_weighted_sum(self):
        item = _item()
        quotes = {"ITC.NS": _quote("ITC.NS", price=420.0, yield_pct=3.4)}
        result = score_candidates([item], quotes, holdings=[], budget=10000)
        sc = result[0]
        expected = 0.40 * sc.yield_score + 0.35 * sc.div_score + 0.25 * sc.value_score
        assert sc.total_score == pytest.approx(expected, abs=0.001)

    def test_custom_weights_applied(self):
        item = _item()
        quotes = {"ITC.NS": _quote("ITC.NS")}
        result = score_candidates(
            [item], quotes, [], 10000,
            yield_weight=1.0, div_weight=0.0, value_weight=0.0
        )
        # With 100% yield weight and only one candidate, yield_score = 1.0
        assert result[0].total_score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# build_rationale
# ---------------------------------------------------------------------------

class TestBuildRationale:
    def _score(self, yield_pct=3.4, below_52w=15.0, sector="FMCG",
               div_s=0.8, yield_s=0.6, val_s=0.5) -> CandidateScore:
        item = _item(sector=sector)
        q = _quote("ITC.NS", yield_pct=yield_pct,
                   price=425.0, high=500.0 if below_52w else None)
        if below_52w is None:
            q = _quote("ITC.NS", yield_pct=yield_pct, price=500.0, high=500.0)
        return CandidateScore(
            item=item, quote=q,
            max_shares=50, cost_for_max_shares=21250.0,
            yield_score=yield_s, div_score=div_s, value_score=val_s,
            total_score=0.65, already_held_shares=0.0,
        )

    def test_high_yield_mentioned(self):
        sc = self._score(yield_pct=5.5)
        r = build_rationale(sc, {}, 0)
        assert "high yield" in r.lower()

    def test_decent_yield_mentioned(self):
        sc = self._score(yield_pct=3.4)
        r = build_rationale(sc, {}, 0)
        assert "yield" in r.lower()

    def test_sector_not_in_portfolio_mentioned(self):
        sc = self._score(sector="FMCG")
        r = build_rationale(sc, {}, portfolio_total=10000)
        assert "fmcg" in r.lower() or "sector" in r.lower()

    def test_deep_discount_mentioned(self):
        sc = self._score(below_52w=30.0)
        # Need a quote that reflects this discount
        sc.quote = _quote("ITC.NS", price=350.0, high=500.0)  # 30% below
        r = build_rationale(sc, {}, 0)
        assert "discount" in r.lower() or "52w" in r.lower()

    def test_returns_non_empty_string(self):
        sc = self._score()
        r = build_rationale(sc, {}, 0)
        assert len(r) > 0
