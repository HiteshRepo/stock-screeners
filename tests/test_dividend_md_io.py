"""Tests for dividend.md_io — portfolio, watchlist, and transaction I/O."""
import pytest
from pathlib import Path

from dividend.md_io import (
    Holding, WatchlistItem, Transaction,
    read_portfolio, write_portfolio,
    read_watchlist, write_watchlist,
    read_transactions, append_transaction,
    ensure_data_files,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _holding(ticker="HDFCBANK", company="HDFC Bank", sector="Banking",
             shares=10.0, avg_buy_price=1650.0, total_invested=16500.0,
             date_added="2024-01-15", last_reviewed="2024-03-01", notes="") -> Holding:
    return Holding(ticker, company, sector, shares, avg_buy_price,
                   total_invested, date_added, last_reviewed, notes)


def _watchlist_item(ticker="ITC", company="ITC Ltd", sector="FMCG",
                    yield_pct=3.4, payout_ratio_pct=80.0,
                    notes="Consistent payer", date_added="2024-01-01") -> WatchlistItem:
    return WatchlistItem(ticker, company, sector, yield_pct, payout_ratio_pct,
                         notes, date_added)


def _transaction(date="2024-01-15", type_="BUY", ticker="HDFCBANK",
                 company="HDFC Bank", shares=10.0, price=1650.0,
                 amount=16500.0, investable_amount=20000.0, notes="") -> Transaction:
    return Transaction(date, type_, ticker, company, shares, price,
                       amount, investable_amount, notes)


# ---------------------------------------------------------------------------
# Holding.ns_ticker
# ---------------------------------------------------------------------------

class TestNsTicker:
    def test_plain_nse_ticker(self):
        h = _holding(ticker="HDFCBANK")
        assert h.ns_ticker == "HDFCBANK.NS"

    def test_already_ns_suffixed(self):
        h = _holding(ticker="HDFCBANK.NS")
        assert h.ns_ticker == "HDFCBANK.NS"

    def test_bse_suffix_preserved(self):
        h = _holding(ticker="COALINDIA.BO")
        assert h.ns_ticker == "COALINDIA.BO"

    def test_lowercase_normalised(self):
        h = _holding(ticker="hdfcbank")
        assert h.ns_ticker == "HDFCBANK.NS"


# ---------------------------------------------------------------------------
# Portfolio roundtrip
# ---------------------------------------------------------------------------

class TestPortfolioIO:
    def test_write_then_read(self, tmp_path):
        p = tmp_path / "portfolio.md"
        holdings = [_holding()]
        write_portfolio(p, holdings)
        result = read_portfolio(p)

        assert len(result) == 1
        h = result[0]
        assert h.ticker == "HDFCBANK"
        assert h.company == "HDFC Bank"
        assert h.sector == "Banking"
        assert h.shares == 10.0
        assert h.avg_buy_price == pytest.approx(1650.0)
        assert h.total_invested == pytest.approx(16500.0)
        assert h.date_added == "2024-01-15"
        assert h.last_reviewed == "2024-03-01"

    def test_multiple_holdings(self, tmp_path):
        p = tmp_path / "portfolio.md"
        holdings = [
            _holding("HDFCBANK", shares=10.0),
            _holding("ITC", company="ITC Ltd", sector="FMCG", shares=50.0,
                     avg_buy_price=400.0, total_invested=20000.0),
        ]
        write_portfolio(p, holdings)
        result = read_portfolio(p)
        assert len(result) == 2
        assert result[1].ticker == "ITC"

    def test_read_missing_file(self, tmp_path):
        result = read_portfolio(tmp_path / "nonexistent.md")
        assert result == []

    def test_read_empty_table(self, tmp_path):
        p = tmp_path / "portfolio.md"
        p.write_text(
            "# Portfolio\n\n"
            "| Ticker | Company | Sector | Shares | Avg Buy Price (₹) "
            "| Total Invested (₹) | Date Added | Last Reviewed | Notes |\n"
            "|--------|---------|--------|--------|-------------------"
            "|--------------------|------------|---------------|-------|\n",
            encoding="utf-8",
        )
        result = read_portfolio(p)
        assert result == []

    def test_skips_malformed_row(self, tmp_path):
        p = tmp_path / "portfolio.md"
        p.write_text(
            "# Portfolio\n\n"
            "| Ticker | Company | Sector | Shares | Avg Buy Price (₹) | Total Invested (₹) | Date Added | Last Reviewed | Notes |\n"
            "|--------|---------|--------|--------|-------------------|--------------------|------------|---------------|-------|\n"
            "| HDFCBANK | HDFC Bank | Banking | NOT_A_NUMBER | 1650 | 16500 | 2024-01-01 |  |  |\n"
            "| ITC | ITC Ltd | FMCG | 50 | 400 | 20000 | 2024-01-01 |  |  |\n",
            encoding="utf-8",
        )
        result = read_portfolio(p)
        # Malformed row skipped, valid row retained
        assert len(result) == 1
        assert result[0].ticker == "ITC"

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "dir" / "portfolio.md"
        write_portfolio(p, [_holding()])
        assert p.exists()

    def test_write_produces_valid_markdown(self, tmp_path):
        p = tmp_path / "portfolio.md"
        write_portfolio(p, [_holding()])
        content = p.read_text(encoding="utf-8")
        assert content.startswith("# Portfolio")
        assert "|" in content
        assert "HDFCBANK" in content


# ---------------------------------------------------------------------------
# Watchlist roundtrip
# ---------------------------------------------------------------------------

class TestWatchlistIO:
    def test_write_then_read(self, tmp_path):
        p = tmp_path / "watchlist.md"
        items = [_watchlist_item()]
        write_watchlist(p, items)
        result = read_watchlist(p)

        assert len(result) == 1
        item = result[0]
        assert item.ticker == "ITC"
        assert item.yield_pct == pytest.approx(3.4)
        assert item.payout_ratio_pct == pytest.approx(80.0)

    def test_read_missing_file(self, tmp_path):
        assert read_watchlist(tmp_path / "nonexistent.md") == []


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

class TestTransactionIO:
    def test_append_single(self, tmp_path):
        p = tmp_path / "transactions.md"
        append_transaction(p, _transaction())
        result = read_transactions(p)

        assert len(result) == 1
        t = result[0]
        assert t.ticker == "HDFCBANK"
        assert t.type == "BUY"
        assert t.shares == 10.0
        assert t.price == pytest.approx(1650.0)
        assert t.amount == pytest.approx(16500.0)
        assert t.investable_amount == pytest.approx(20000.0)

    def test_append_multiple_preserves_order(self, tmp_path):
        p = tmp_path / "transactions.md"
        for i in range(1, 4):
            append_transaction(p, _transaction(date=f"2024-01-{i:02d}", shares=float(i)))
        result = read_transactions(p)
        assert len(result) == 3
        assert [t.shares for t in result] == [1.0, 2.0, 3.0]

    def test_sell_type_roundtrip(self, tmp_path):
        p = tmp_path / "transactions.md"
        append_transaction(p, _transaction(type_="SELL"))
        result = read_transactions(p)
        assert result[0].type == "SELL"

    def test_empty_investable_amount(self, tmp_path):
        p = tmp_path / "transactions.md"
        txn = _transaction(investable_amount=0.0)
        append_transaction(p, txn)
        result = read_transactions(p)
        assert result[0].investable_amount == 0.0

    def test_read_missing_file(self, tmp_path):
        assert read_transactions(tmp_path / "nonexistent.md") == []


# ---------------------------------------------------------------------------
# ensure_data_files
# ---------------------------------------------------------------------------

class TestEnsureDataFiles:
    def test_creates_all_three_files(self, tmp_path):
        portfolio = tmp_path / "portfolio.md"
        watchlist = tmp_path / "watchlist.md"
        transactions = tmp_path / "transactions.md"

        ensure_data_files(portfolio, watchlist, transactions)

        assert portfolio.exists()
        assert watchlist.exists()
        assert transactions.exists()

    def test_does_not_overwrite_existing(self, tmp_path):
        portfolio = tmp_path / "portfolio.md"
        portfolio.write_text("# My existing content\n", encoding="utf-8")
        watchlist = tmp_path / "watchlist.md"
        transactions = tmp_path / "transactions.md"

        ensure_data_files(portfolio, watchlist, transactions)

        # Existing file must be untouched
        assert portfolio.read_text(encoding="utf-8") == "# My existing content\n"

    def test_creates_nested_dirs(self, tmp_path):
        portfolio = tmp_path / "deep" / "nested" / "portfolio.md"
        watchlist = tmp_path / "deep" / "nested" / "watchlist.md"
        transactions = tmp_path / "deep" / "nested" / "transactions.md"

        ensure_data_files(portfolio, watchlist, transactions)

        assert portfolio.exists()
