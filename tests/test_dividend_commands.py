"""
Tests for dividend buy, sell, and status commands.

Uses click.testing.CliRunner to invoke the full CLI stack so that config
loading, file I/O, and command logic are all exercised together.
Market data (yfinance) is mocked throughout — no network required.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from dividend.cli import cli
from dividend.md_io import (
    Holding, WatchlistItem,
    read_portfolio, write_portfolio,
    read_watchlist, write_watchlist,
    read_transactions,
    ensure_data_files,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path):
    """
    Full CLI test environment: config.yaml pointing to tmp_path data files.
    Returns a dict with runner, config_file path, and individual data paths.
    """
    portfolio_path = tmp_path / "portfolio.md"
    watchlist_path = tmp_path / "watchlist.md"
    transactions_path = tmp_path / "transactions.md"
    cache_path = tmp_path / ".cache" / "market_data.json"

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"files:\n"
        f"  portfolio: {portfolio_path}\n"
        f"  watchlist: {watchlist_path}\n"
        f"  transactions: {transactions_path}\n"
        f"  cache: {cache_path}\n"
        f"goals:\n"
        f"  test-goal: 1000000\n",
        encoding="utf-8",
    )
    ensure_data_files(portfolio_path, watchlist_path, transactions_path)

    return {
        "runner": CliRunner(),
        "config_file": str(config_path),
        "portfolio_path": portfolio_path,
        "watchlist_path": watchlist_path,
        "transactions_path": transactions_path,
    }


def _invoke(env, args, *, input="y\n"):
    """Shorthand to invoke the CLI with the test config file."""
    return env["runner"].invoke(
        cli,
        ["--config-file", env["config_file"]] + args,
        input=input,
        catch_exceptions=False,
    )


def _add_holding(env, ticker="HDFCBANK", company="HDFC Bank", sector="Banking",
                 shares=10.0, avg_buy_price=1650.0, total_invested=16500.0):
    h = Holding(ticker, company, sector, shares, avg_buy_price, total_invested,
                "2024-01-15", "", "")
    write_portfolio(env["portfolio_path"], [h])
    return h


def _add_watchlist_item(env, ticker="ITC", company="ITC Ltd", sector="FMCG",
                        yield_pct=3.4, payout_ratio_pct=80.0):
    item = WatchlistItem(ticker, company, sector, yield_pct, payout_ratio_pct, "", "2024-01-01")
    write_watchlist(env["watchlist_path"], [item])
    return item


def _mock_quote(ticker, price=1720.0, yield_pct=1.2, high=1800.0, low=1400.0):
    from shared.market_data import QuoteResult
    return QuoteResult(
        ticker=ticker,
        price=price,
        yield_pct=yield_pct,
        fifty_two_week_high=high,
        fifty_two_week_low=low,
        company_name="HDFC Bank Limited",
        payout_ratio_pct=15.0,
        error=None,
        fetched_at=datetime.now().isoformat(),
    )


def _error_quote(ticker, error="No price data returned by Yahoo Finance"):
    from shared.market_data import QuoteResult
    return QuoteResult(
        ticker=ticker,
        price=None,
        yield_pct=None,
        fifty_two_week_high=None,
        fifty_two_week_low=None,
        company_name=None,
        payout_ratio_pct=None,
        error=error,
        fetched_at=datetime.now().isoformat(),
    )


# ---------------------------------------------------------------------------
# buy command
# ---------------------------------------------------------------------------

class TestBuyCommand:
    def test_buy_new_holding_creates_row(self, env):
        result = _invoke(env, [
            "buy", "--ticker", "HDFCBANK",
            "--shares", "10", "--price", "1650",
            "--company", "HDFC Bank", "--sector", "Banking",
        ])
        assert result.exit_code == 0, result.output
        assert "Recorded" in result.output

        holdings = read_portfolio(env["portfolio_path"])
        assert len(holdings) == 1
        h = holdings[0]
        assert h.ticker == "HDFCBANK"
        assert h.shares == 10.0
        assert h.avg_buy_price == pytest.approx(1650.0)
        assert h.total_invested == pytest.approx(16500.0)
        assert h.company == "HDFC Bank"
        assert h.sector == "Banking"

    def test_buy_new_holding_appends_transaction(self, env):
        _invoke(env, [
            "buy", "--ticker", "HDFCBANK",
            "--shares", "10", "--price", "1650",
            "--company", "HDFC Bank", "--sector", "Banking",
        ])
        txns = read_transactions(env["transactions_path"])
        assert len(txns) == 1
        t = txns[0]
        assert t.ticker == "HDFCBANK"
        assert t.type == "BUY"
        assert t.shares == 10.0
        assert t.price == pytest.approx(1650.0)
        assert t.amount == pytest.approx(16500.0)

    def test_buy_topup_updates_weighted_avg_price(self, env):
        _add_holding(env, shares=10.0, avg_buy_price=1650.0, total_invested=16500.0)

        result = _invoke(env, [
            "buy", "--ticker", "HDFCBANK",
            "--shares", "10", "--price", "1750",
        ])
        assert result.exit_code == 0, result.output

        holdings = read_portfolio(env["portfolio_path"])
        assert len(holdings) == 1
        h = holdings[0]
        assert h.shares == 20.0
        # 16500 + 10×1750 = 16500 + 17500 = 34000
        assert h.total_invested == pytest.approx(34000.0)
        # Weighted avg: 34000 / 20 = 1700
        assert h.avg_buy_price == pytest.approx(1700.0)

    def test_buy_topup_appends_second_transaction(self, env):
        _add_holding(env)
        _invoke(env, ["buy", "--ticker", "HDFCBANK", "--shares", "5", "--price", "1750"])
        txns = read_transactions(env["transactions_path"])
        assert len(txns) == 1
        assert txns[0].shares == 5.0

    def test_buy_uses_watchlist_for_company_sector(self, env):
        _add_watchlist_item(env, ticker="ITC", company="ITC Ltd", sector="FMCG")
        with patch("dividend.commands.buy.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"ITC.NS": _mock_quote("ITC.NS", price=400.0, yield_pct=3.4)}
            _invoke(env, ["buy", "--ticker", "ITC", "--shares", "50", "--price", "400"])

        holdings = read_portfolio(env["portfolio_path"])
        assert holdings[0].company == "ITC Ltd"
        assert holdings[0].sector == "FMCG"

    def test_buy_cancelled_makes_no_changes(self, env):
        result = _invoke(env, [
            "buy", "--ticker", "HDFCBANK",
            "--shares", "10", "--price", "1650",
            "--company", "HDFC Bank", "--sector", "Banking",
        ], input="n\n")
        assert "Cancelled" in result.output
        assert read_portfolio(env["portfolio_path"]) == []

    def test_buy_shows_preview_before_confirming(self, env):
        result = _invoke(env, [
            "buy", "--ticker", "HDFCBANK",
            "--shares", "10", "--price", "1650",
            "--company", "HDFC Bank", "--sector", "Banking",
        ])
        assert "NEW HOLDING" in result.output
        assert "1,650.00" in result.output

    def test_buy_topup_shows_avg_price_change(self, env):
        _add_holding(env, shares=10.0, avg_buy_price=1650.0)
        result = _invoke(env, [
            "buy", "--ticker", "HDFCBANK", "--shares", "10", "--price", "1750",
        ])
        assert "TOP-UP" in result.output
        assert "→" in result.output

    def test_buy_rejects_zero_shares(self, env):
        result = env["runner"].invoke(
            cli,
            ["--config-file", env["config_file"],
             "buy", "--ticker", "HDFCBANK", "--shares", "0", "--price", "1650"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "must be > 0" in result.output

    def test_buy_rejects_zero_price(self, env):
        result = env["runner"].invoke(
            cli,
            ["--config-file", env["config_file"],
             "buy", "--ticker", "HDFCBANK", "--shares", "10", "--price", "0"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "must be > 0" in result.output

    def test_buy_investable_amount_logged(self, env):
        _invoke(env, [
            "buy", "--ticker", "HDFCBANK",
            "--shares", "10", "--price", "1650",
            "--company", "HDFC Bank", "--sector", "Banking",
            "--investable-amount", "25000",
        ])
        txns = read_transactions(env["transactions_path"])
        assert txns[0].investable_amount == pytest.approx(25000.0)

    def test_buy_ticker_normalised_to_uppercase(self, env):
        _invoke(env, [
            "buy", "--ticker", "hdfcbank",
            "--shares", "10", "--price", "1650",
            "--company", "HDFC Bank", "--sector", "Banking",
        ])
        holdings = read_portfolio(env["portfolio_path"])
        assert holdings[0].ticker == "HDFCBANK"


# ---------------------------------------------------------------------------
# sell command
# ---------------------------------------------------------------------------

class TestSellCommand:
    def test_sell_full_removes_holding(self, env):
        _add_holding(env, shares=10.0)
        result = _invoke(env, ["sell", "--ticker", "HDFCBANK", "--shares", "10", "--price", "1800"])
        assert result.exit_code == 0, result.output
        assert read_portfolio(env["portfolio_path"]) == []

    def test_sell_full_appends_transaction(self, env):
        _add_holding(env, shares=10.0)
        _invoke(env, ["sell", "--ticker", "HDFCBANK", "--shares", "10", "--price", "1800"])
        txns = read_transactions(env["transactions_path"])
        assert len(txns) == 1
        t = txns[0]
        assert t.type == "SELL"
        assert t.shares == 10.0
        assert t.price == pytest.approx(1800.0)
        assert t.amount == pytest.approx(18000.0)

    def test_sell_partial_reduces_shares(self, env):
        _add_holding(env, shares=20.0, avg_buy_price=1650.0, total_invested=33000.0)
        _invoke(env, ["sell", "--ticker", "HDFCBANK", "--shares", "5", "--price", "1800"])

        holdings = read_portfolio(env["portfolio_path"])
        assert len(holdings) == 1
        h = holdings[0]
        assert h.shares == 15.0
        assert h.avg_buy_price == pytest.approx(1650.0)
        assert h.total_invested == pytest.approx(15 * 1650.0)

    def test_sell_shows_realized_pnl(self, env):
        _add_holding(env, shares=10.0, avg_buy_price=1650.0, total_invested=16500.0)
        result = _invoke(env, ["sell", "--ticker", "HDFCBANK", "--shares", "10", "--price", "1800"])
        # proceeds = 18000, cost = 16500, P&L = +1500
        assert "+1,500" in result.output or "+1500" in result.output

    def test_sell_ticker_not_found_aborts(self, env):
        result = env["runner"].invoke(
            cli,
            ["--config-file", env["config_file"],
             "sell", "--ticker", "BADTICK", "--shares", "5", "--price", "100"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_sell_oversell_aborts(self, env):
        _add_holding(env, shares=10.0)
        result = env["runner"].invoke(
            cli,
            ["--config-file", env["config_file"],
             "sell", "--ticker", "HDFCBANK", "--shares", "15", "--price", "1800"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "cannot sell" in result.output.lower() or "cannot sell" in result.output

    def test_sell_cancelled_makes_no_changes(self, env):
        _add_holding(env, shares=10.0)
        result = _invoke(env, [
            "sell", "--ticker", "HDFCBANK", "--shares", "10", "--price", "1800"
        ], input="n\n")
        assert "Cancelled" in result.output
        # Holding must still be there
        assert len(read_portfolio(env["portfolio_path"])) == 1

    def test_sell_rejects_zero_shares(self, env):
        _add_holding(env)
        result = env["runner"].invoke(
            cli,
            ["--config-file", env["config_file"],
             "sell", "--ticker", "HDFCBANK", "--shares", "0", "--price", "1800"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0

    def test_sell_preview_shows_remaining_shares(self, env):
        _add_holding(env, shares=20.0)
        result = _invoke(env, ["sell", "--ticker", "HDFCBANK", "--shares", "5", "--price", "1800"])
        assert "15" in result.output  # remaining shares


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------

class TestStatusCommand:
    def _mock_quotes(self, holdings):
        """Return a mocked fetch_quotes that returns valid quotes for each holding."""
        def _fetch(tickers, *args, **kwargs):
            return {t: _mock_quote(t) for t in tickers}
        return _fetch

    def test_status_empty_portfolio(self, env):
        result = _invoke(env, ["status"])
        assert result.exit_code == 0, result.output
        assert "empty" in result.output.lower()

    def test_status_shows_holdings_table(self, env):
        _add_holding(env)
        with patch("dividend.commands.status.fetch_quotes", side_effect=self._mock_quotes(None)):
            result = _invoke(env, ["status"])
        assert result.exit_code == 0, result.output
        assert "HDFCBANK" in result.output
        assert "Holdings" in result.output

    def test_status_shows_market_value(self, env):
        # 10 shares, avg 1650, current price 1720 → value = 17200
        _add_holding(env, shares=10.0, avg_buy_price=1650.0, total_invested=16500.0)
        with patch("dividend.commands.status.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"HDFCBANK.NS": _mock_quote("HDFCBANK.NS", price=1720.0)}
            result = _invoke(env, ["status"])
        assert "17,200" in result.output

    def test_status_shows_positive_pnl(self, env):
        _add_holding(env, shares=10.0, avg_buy_price=1650.0, total_invested=16500.0)
        with patch("dividend.commands.status.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"HDFCBANK.NS": _mock_quote("HDFCBANK.NS", price=1720.0)}
            result = _invoke(env, ["status"])
        assert "+" in result.output

    def test_status_shows_sector_allocation(self, env):
        _add_holding(env)
        with patch("dividend.commands.status.fetch_quotes", side_effect=self._mock_quotes(None)):
            result = _invoke(env, ["status"])
        assert "Sector allocation" in result.output
        assert "Banking" in result.output

    def test_status_shows_goal_progress(self, env):
        _add_holding(env)
        with patch("dividend.commands.status.fetch_quotes", side_effect=self._mock_quotes(None)):
            result = _invoke(env, ["status"])
        assert "Goals" in result.output
        assert "test-goal" in result.output

    def test_status_handles_fetch_error_gracefully(self, env):
        _add_holding(env)
        with patch("dividend.commands.status.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {
                "HDFCBANK.NS": _error_quote("HDFCBANK.NS")
            }
            result = _invoke(env, ["status"])
        assert result.exit_code == 0, result.output
        assert "⚠" in result.output

    def test_status_excludes_failed_tickers_from_totals(self, env):
        # Two holdings — one valid, one error
        holdings = [
            Holding("HDFCBANK", "HDFC Bank", "Banking", 10, 1650, 16500, "2024-01-15", "", ""),
            Holding("BADTICK", "Bad Co", "Unknown", 5, 100, 500, "2024-01-15", "", ""),
        ]
        write_portfolio(env["portfolio_path"], holdings)

        with patch("dividend.commands.status.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {
                "HDFCBANK.NS": _mock_quote("HDFCBANK.NS", price=1720.0),
                "BADTICK.NS": _error_quote("BADTICK.NS"),
            }
            result = _invoke(env, ["status"])

        assert result.exit_code == 0, result.output
        assert "BADTICK" in result.output
        assert "excluded" in result.output.lower() or "⚠" in result.output

    def test_status_annual_income_calculated(self, env):
        # 10 shares, price 1720, yield 1.2% → income = 10 * 1720 * 0.012 = 206.4
        _add_holding(env)
        with patch("dividend.commands.status.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {
                "HDFCBANK.NS": _mock_quote("HDFCBANK.NS", price=1720.0, yield_pct=1.2)
            }
            result = _invoke(env, ["status"])
        assert "206" in result.output

    def test_status_multiple_sectors_shown(self, env):
        holdings = [
            Holding("HDFCBANK", "HDFC Bank", "Banking", 10, 1650, 16500, "2024-01-15", "", ""),
            Holding("ITC", "ITC Ltd", "FMCG", 50, 400, 20000, "2024-01-15", "", ""),
        ]
        write_portfolio(env["portfolio_path"], holdings)

        with patch("dividend.commands.status.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {
                "HDFCBANK.NS": _mock_quote("HDFCBANK.NS", price=1720.0),
                "ITC.NS": _mock_quote("ITC.NS", price=420.0),
            }
            result = _invoke(env, ["status"])

        assert "Banking" in result.output
        assert "FMCG" in result.output

    def test_status_refresh_flag_passes_force_refresh(self, env):
        _add_holding(env)
        with patch("dividend.commands.status.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"HDFCBANK.NS": _mock_quote("HDFCBANK.NS")}
            _invoke(env, ["status", "--refresh"])
        _, kwargs = mock_fetch.call_args
        assert kwargs.get("force_refresh") is True


# ---------------------------------------------------------------------------
# review command
# ---------------------------------------------------------------------------

class TestReviewCommand:
    def test_review_empty_portfolio(self, env):
        result = _invoke(env, ["review"])
        assert result.exit_code == 0, result.output
        assert "empty" in result.output.lower()

    def test_review_shows_ok_for_healthy_holding(self, env):
        # Price 1720 vs avg buy 1650 → only +4.2% → no flag
        _add_holding(env, avg_buy_price=1650.0, total_invested=16500.0)
        with patch("dividend.commands.review.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"HDFCBANK.NS": _mock_quote("HDFCBANK.NS", price=1720.0)}
            result = _invoke(env, ["review"])
        assert result.exit_code == 0, result.output
        assert "✅" in result.output

    def test_review_flags_price_drop(self, env):
        # Avg buy 2000, current price 1650 → drop = 17.5% > default 15%
        _add_holding(env, avg_buy_price=2000.0, total_invested=20000.0)
        with patch("dividend.commands.review.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"HDFCBANK.NS": _mock_quote("HDFCBANK.NS", price=1650.0)}
            result = _invoke(env, ["review"])
        assert "⚠" in result.output
        assert "below avg buy" in result.output.lower()

    def test_review_flags_yield_drop(self, env):
        # Entry yield 3.0%, current yield 1.5% → 50% relative drop > default 20%
        h = Holding("HDFCBANK", "HDFC Bank", "Banking", 10, 1650, 16500,
                    "2024-01-15", "", "", entry_yield_pct=3.0)
        from dividend.md_io import write_portfolio
        write_portfolio(env["portfolio_path"], [h])

        with patch("dividend.commands.review.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {
                "HDFCBANK.NS": _mock_quote("HDFCBANK.NS", price=1720.0, yield_pct=1.5)
            }
            result = _invoke(env, ["review"])
        assert "⚠" in result.output
        assert "yield fell" in result.output.lower()

    def test_review_no_yield_flag_when_entry_yield_not_recorded(self, env):
        # entry_yield_pct = 0.0 → yield check skipped
        _add_holding(env, avg_buy_price=1650.0)
        with patch("dividend.commands.review.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {
                "HDFCBANK.NS": _mock_quote("HDFCBANK.NS", price=1720.0, yield_pct=0.5)
            }
            result = _invoke(env, ["review"])
        assert "yield fell" not in result.output.lower()

    def test_review_shows_error_for_failed_fetch(self, env):
        _add_holding(env)
        with patch("dividend.commands.review.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"HDFCBANK.NS": _error_quote("HDFCBANK.NS")}
            result = _invoke(env, ["review"])
        assert result.exit_code == 0, result.output
        assert "❌" in result.output

    def test_review_updates_last_reviewed_date(self, env):
        _add_holding(env)
        with patch("dividend.commands.review.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"HDFCBANK.NS": _mock_quote("HDFCBANK.NS")}
            _invoke(env, ["review"])
        from dividend.md_io import read_portfolio
        from datetime import date
        holdings = read_portfolio(env["portfolio_path"])
        assert holdings[0].last_reviewed == date.today().isoformat()

    def test_review_does_not_update_last_reviewed_for_fetch_errors(self, env):
        _add_holding(env)
        with patch("dividend.commands.review.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"HDFCBANK.NS": _error_quote("HDFCBANK.NS")}
            _invoke(env, ["review"])
        from dividend.md_io import read_portfolio
        holdings = read_portfolio(env["portfolio_path"])
        assert holdings[0].last_reviewed == ""  # unchanged

    def test_review_shows_summary_counts(self, env):
        _add_holding(env)
        with patch("dividend.commands.review.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"HDFCBANK.NS": _mock_quote("HDFCBANK.NS")}
            result = _invoke(env, ["review"])
        assert "reviewed" in result.output.lower()


# ---------------------------------------------------------------------------
# recommend command
# ---------------------------------------------------------------------------

class TestRecommendCommand:
    def _watchlist_item(self, env, ticker="ITC", company="ITC Ltd",
                        sector="FMCG", yield_pct=3.4):
        from dividend.md_io import WatchlistItem, write_watchlist
        item = WatchlistItem(ticker, company, sector, yield_pct, 80.0, "", "2024-01-01")
        write_watchlist(env["watchlist_path"], [item])
        return item

    def test_recommend_empty_watchlist(self, env):
        result = _invoke(env, ["recommend", "--amount", "25000"])
        assert result.exit_code == 0, result.output
        assert "empty" in result.output.lower()

    def test_recommend_shows_top_candidates(self, env):
        self._watchlist_item(env)
        with patch("dividend.commands.recommend.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"ITC.NS": _mock_quote("ITC.NS", price=420.0)}
            result = _invoke(env, ["recommend", "--amount", "25000"])
        assert result.exit_code == 0, result.output
        assert "#1" in result.output
        assert "ITC" in result.output

    def test_recommend_shows_advisory_footer(self, env):
        self._watchlist_item(env)
        with patch("dividend.commands.recommend.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"ITC.NS": _mock_quote("ITC.NS", price=420.0)}
            result = _invoke(env, ["recommend", "--amount", "25000"])
        assert "Advisory only" in result.output

    def test_recommend_excludes_unaffordable_stocks(self, env):
        self._watchlist_item(env, ticker="MRF", yield_pct=1.0)
        with patch("dividend.commands.recommend.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {
                "MRF.NS": _mock_quote("MRF.NS", price=100000.0)
            }
            result = _invoke(env, ["recommend", "--amount", "5000"])
        assert result.exit_code == 0, result.output
        assert "No affordable" in result.output

    def test_recommend_rejects_zero_amount(self, env):
        result = env["runner"].invoke(
            cli,
            ["--config-file", env["config_file"], "recommend", "--amount", "0"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0

    def test_recommend_shows_shares_can_buy(self, env):
        self._watchlist_item(env)
        with patch("dividend.commands.recommend.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"ITC.NS": _mock_quote("ITC.NS", price=420.0)}
            result = _invoke(env, ["recommend", "--amount", "25000"])
        # floor(25000/420) = 59 shares
        assert "59" in result.output

    def test_recommend_shows_score(self, env):
        self._watchlist_item(env)
        with patch("dividend.commands.recommend.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"ITC.NS": _mock_quote("ITC.NS", price=420.0)}
            result = _invoke(env, ["recommend", "--amount", "25000"])
        assert "Score:" in result.output

    def test_recommend_shows_rationale(self, env):
        self._watchlist_item(env)
        with patch("dividend.commands.recommend.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = {"ITC.NS": _mock_quote("ITC.NS", price=420.0)}
            result = _invoke(env, ["recommend", "--amount", "25000"])
        assert "Why:" in result.output

    def test_recommend_top_flag_limits_results(self, env):
        from dividend.md_io import WatchlistItem, write_watchlist
        items = [
            WatchlistItem(f"TICK{i}", f"Co {i}", "FMCG", 3.0, 70.0, "", "2024-01-01")
            for i in range(5)
        ]
        write_watchlist(env["watchlist_path"], items)
        quotes = {
            f"TICK{i}.NS": _mock_quote(f"TICK{i}.NS", price=100.0 + i)
            for i in range(5)
        }
        with patch("dividend.commands.recommend.fetch_quotes") as mock_fetch:
            mock_fetch.return_value = quotes
            result = _invoke(env, ["recommend", "--amount", "10000", "--top", "2"])
        assert "#1" in result.output
        assert "#2" in result.output
        assert "#3" not in result.output
