"""
dividend.md_io — data models and markdown I/O for the dividend tool.

Relies on shared.md_table for the generic parse/format helpers so that
only the domain models (Holding, WatchlistItem, Transaction) live here.

File schema
-----------
portfolio.md     — one row per current holding
watchlist.md     — candidate stocks not yet purchased
transactions.md  — append-only audit log of every buy and sell
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from shared.md_table import parse_table, format_table


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Holding:
    ticker: str           # plain NSE ticker, e.g. HDFCBANK (no .NS suffix)
    company: str
    sector: str
    shares: float
    avg_buy_price: float  # weighted average cost basis
    total_invested: float
    date_added: str       # YYYY-MM-DD
    last_reviewed: str    # YYYY-MM-DD or ""
    notes: str
    entry_yield_pct: float = 0.0  # trailing yield at time of first buy; 0 = not recorded

    @property
    def ns_ticker(self) -> str:
        """Ticker with exchange suffix for yfinance. Defaults to .NS (NSE).
        If you explicitly stored TICKER.BO, the .BO suffix is preserved."""
        t = self.ticker.upper()
        if t.endswith(".NS") or t.endswith(".BO"):
            return t
        return f"{t}.NS"


@dataclass
class WatchlistItem:
    ticker: str
    company: str
    sector: str
    yield_pct: float          # last known trailing yield %
    payout_ratio_pct: float   # last known payout ratio %
    notes: str
    date_added: str           # YYYY-MM-DD

    @property
    def ns_ticker(self) -> str:
        t = self.ticker.upper()
        if t.endswith(".NS") or t.endswith(".BO"):
            return t
        return f"{t}.NS"


@dataclass
class Transaction:
    date: str                        # YYYY-MM-DD
    type: Literal["BUY", "SELL"]
    ticker: str
    company: str
    shares: float
    price: float                     # per-share price
    amount: float                    # total = shares × price
    investable_amount: float         # cash available at time of action (audit field, 0 if unknown)
    notes: str


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

_PORTFOLIO_HEADERS = [
    "Ticker", "Company", "Sector", "Shares",
    "Avg Buy Price (₹)", "Total Invested (₹)",
    "Date Added", "Last Reviewed", "Notes", "Entry Yield %",
]

_PORTFOLIO_TEMPLATE = (
    "# Portfolio\n\n"
    "| Ticker | Company | Sector | Shares | Avg Buy Price (₹) | Total Invested (₹) "
    "| Date Added | Last Reviewed | Notes | Entry Yield % |\n"
    "|--------|---------|--------|--------|-------------------|--------------------|"
    "------------|---------------|-------|---------------|\n"
)


def read_portfolio(path: Path) -> list[Holding]:
    """Return all holdings from *path*. Returns [] if file does not exist."""
    if not path.exists():
        return []
    rows = parse_table(path.read_text(encoding="utf-8"))
    result: list[Holding] = []
    for row in rows:
        try:
            h = Holding(
                ticker=row["Ticker"],
                company=row["Company"],
                sector=row["Sector"],
                shares=float(row["Shares"] or 0),
                avg_buy_price=float(row["Avg Buy Price (₹)"] or 0),
                total_invested=float(row["Total Invested (₹)"] or 0),
                date_added=row["Date Added"],
                last_reviewed=row.get("Last Reviewed", ""),
                notes=row.get("Notes", ""),
                # Optional column — defaults to 0 so old portfolio.md files parse fine
                entry_yield_pct=float(row.get("Entry Yield %") or 0),
            )
            if h.ticker:
                result.append(h)
        except (KeyError, ValueError):
            continue  # skip malformed rows without crashing
    return result


def write_portfolio(path: Path, holdings: list[Holding]) -> None:
    """Overwrite *path* with a clean markdown table from *holdings*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        [
            h.ticker, h.company, h.sector,
            f"{h.shares:g}",
            f"{h.avg_buy_price:.2f}",
            f"{h.total_invested:.2f}",
            h.date_added, h.last_reviewed, h.notes,
            f"{h.entry_yield_pct:.2f}" if h.entry_yield_pct else "",
        ]
        for h in holdings
    ]
    path.write_text(
        f"# Portfolio\n\n{format_table(_PORTFOLIO_HEADERS, rows)}\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

_WATCHLIST_HEADERS = [
    "Ticker", "Company", "Sector",
    "Yield %", "Payout Ratio %", "Notes", "Date Added",
]

_WATCHLIST_TEMPLATE = (
    "# Watchlist\n\n"
    "| Ticker | Company | Sector | Yield % | Payout Ratio % | Notes | Date Added |\n"
    "|--------|---------|--------|---------|----------------|-------|------------|\n"
)


def read_watchlist(path: Path) -> list[WatchlistItem]:
    if not path.exists():
        return []
    rows = parse_table(path.read_text(encoding="utf-8"))
    result: list[WatchlistItem] = []
    for row in rows:
        try:
            item = WatchlistItem(
                ticker=row["Ticker"],
                company=row["Company"],
                sector=row["Sector"],
                yield_pct=float(row["Yield %"] or 0),
                payout_ratio_pct=float(row["Payout Ratio %"] or 0),
                notes=row.get("Notes", ""),
                date_added=row["Date Added"],
            )
            if item.ticker:
                result.append(item)
        except (KeyError, ValueError):
            continue
    return result


def write_watchlist(path: Path, items: list[WatchlistItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        [
            item.ticker, item.company, item.sector,
            f"{item.yield_pct:.2f}",
            f"{item.payout_ratio_pct:.2f}",
            item.notes, item.date_added,
        ]
        for item in items
    ]
    path.write_text(
        f"# Watchlist\n\n{format_table(_WATCHLIST_HEADERS, rows)}\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Transactions (append-only audit log)
# ---------------------------------------------------------------------------

_TRANSACTION_HEADERS = [
    "Date", "Type", "Ticker", "Company", "Shares",
    "Price (₹)", "Amount (₹)", "Investable Amount (₹)", "Notes",
]

_TRANSACTIONS_TEMPLATE = (
    "# Transactions\n\n"
    "| Date | Type | Ticker | Company | Shares | Price (₹) | Amount (₹) "
    "| Investable Amount (₹) | Notes |\n"
    "|------|------|--------|---------|--------|-----------|------------"
    "|----------------------|-------|\n"
)


def read_transactions(path: Path) -> list[Transaction]:
    if not path.exists():
        return []
    rows = parse_table(path.read_text(encoding="utf-8"))
    result: list[Transaction] = []
    for row in rows:
        try:
            t = Transaction(
                date=row["Date"],
                type=row.get("Type", "BUY").upper(),  # type: ignore[arg-type]
                ticker=row["Ticker"],
                company=row["Company"],
                shares=float(row["Shares"] or 0),
                price=float(row["Price (₹)"] or 0),
                amount=float(row["Amount (₹)"] or 0),
                investable_amount=float(row.get("Investable Amount (₹)") or 0),
                notes=row.get("Notes", ""),
            )
            if t.ticker:
                result.append(t)
        except (KeyError, ValueError):
            continue
    return result


def append_transaction(path: Path, txn: Transaction) -> None:
    """Append *txn* to the transactions log, rewriting the full file."""
    existing = read_transactions(path)
    existing.append(txn)
    _write_transactions(path, existing)


def _write_transactions(path: Path, transactions: list[Transaction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        [
            t.date, t.type, t.ticker, t.company,
            f"{t.shares:g}",
            f"{t.price:.2f}",
            f"{t.amount:.2f}",
            f"{t.investable_amount:.2f}" if t.investable_amount else "",
            t.notes,
        ]
        for t in transactions
    ]
    path.write_text(
        f"# Transactions\n\n{format_table(_TRANSACTION_HEADERS, rows)}\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Bootstrap helper
# ---------------------------------------------------------------------------

def ensure_data_files(
    portfolio_path: Path,
    watchlist_path: Path,
    transactions_path: Path,
) -> None:
    """Create data files with empty table templates if they don't exist yet.
    Called at CLI startup so every command can assume the files are present."""
    for path, template in [
        (portfolio_path, _PORTFOLIO_TEMPLATE),
        (watchlist_path, _WATCHLIST_TEMPLATE),
        (transactions_path, _TRANSACTIONS_TEMPLATE),
    ]:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template, encoding="utf-8")
