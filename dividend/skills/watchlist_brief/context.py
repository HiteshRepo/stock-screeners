"""
Context gatherer for the watchlist_brief skill.

Reads watchlist.md + portfolio.md + live market data for the target ticker,
then returns the template variables that prompt.md expects.
"""
from __future__ import annotations

import json
from datetime import date

from dividend.config import Config
from dividend.md_io import read_portfolio, read_watchlist
from shared.market_data import fetch_quotes


def gather(cfg: Config, ticker: str = "", **kwargs) -> dict:
    """
    Build the context dict for the watchlist_brief prompt.

    Args:
        cfg:     loaded Config
        ticker:  NSE ticker to research (required)

    Returns template variables expected by watchlist_brief/prompt.md.
    Raises ValueError if ticker is not provided.
    """
    if not ticker:
        raise ValueError("--ticker is required for the watchlist-brief skill.")

    ticker = ticker.upper().strip()
    ns_ticker = f"{ticker}.NS" if "." not in ticker else ticker

    watchlist = read_watchlist(cfg.watchlist_path)
    holdings = read_portfolio(cfg.portfolio_path)

    # Watchlist entry (may not exist — user can research arbitrary tickers)
    item = next((w for w in watchlist if w.ticker.upper() == ticker), None)

    # Live market data
    quotes = fetch_quotes(
        [ns_ticker],
        cfg.cache_path,
        cfg.cache_expiry_hours,
        on_fetch=lambda t: None,
    )
    q = quotes.get(ns_ticker)

    market_data: dict = {}
    if q and q.is_valid:
        market_data = {
            "current_price": q.price,
            "trailing_yield_pct": q.yield_pct,
            "52w_high": q.fifty_two_week_high,
            "52w_low": q.fifty_two_week_low,
            "pct_below_52w_high": q.pct_below_52w_high,
            "payout_ratio_pct": q.payout_ratio_pct,
        }
    else:
        market_data["fetch_error"] = q.error if q else "no data returned"

    # Current portfolio sector allocation (% of cost basis)
    portfolio_total = sum(h.total_invested for h in holdings)
    sector_totals: dict[str, float] = {}
    for h in holdings:
        sector_totals[h.sector] = sector_totals.get(h.sector, 0) + h.total_invested

    sector_allocation = {
        s: round(v / portfolio_total * 100, 1) if portfolio_total > 0 else 0.0
        for s, v in sorted(sector_totals.items(), key=lambda x: -x[1])
    }

    return {
        "ticker": ticker,
        "company": item.company if item else ticker,
        "sector": item.sector if item else "Unknown",
        "watchlist_notes": item.notes if item else "",
        "market_data": json.dumps(market_data, indent=2, ensure_ascii=False),
        "portfolio_sectors": json.dumps(sector_allocation, indent=2, ensure_ascii=False),
        "portfolio_total_invested": f"₹{portfolio_total:,.0f}",
        "today": date.today().strftime("%d %b %Y"),
    }
