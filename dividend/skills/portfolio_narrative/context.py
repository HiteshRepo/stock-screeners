"""
Context gatherer for the portfolio_narrative skill.

Reads portfolio.md + live market data, then returns the template
variables that prompt.md expects.
"""
from __future__ import annotations

import json
from datetime import date

from dividend.config import Config
from dividend.md_io import read_portfolio
from shared.market_data import fetch_quotes


def gather(cfg: Config, **kwargs) -> dict:
    """
    Build the context dict for the portfolio_narrative prompt.

    Returns:
        holdings          — JSON string of enriched holding rows
        total_invested    — formatted ₹ string
        total_value       — formatted ₹ string (valid quotes only)
        goals             — JSON string of {goal: target}
        today             — formatted date string
    """
    holdings = read_portfolio(cfg.portfolio_path)
    if not holdings:
        raise ValueError("Portfolio is empty — nothing to narrate.")

    tickers = [h.ns_ticker for h in holdings]
    quotes = fetch_quotes(
        tickers,
        cfg.cache_path,
        cfg.cache_expiry_hours,
        on_fetch=lambda t: None,  # silent fetch for AI command
    )

    rows = []
    total_value = 0.0
    for h in holdings:
        q = quotes.get(h.ns_ticker)
        row: dict = {
            "ticker": h.ticker,
            "company": h.company,
            "sector": h.sector,
            "shares": h.shares,
            "avg_buy_price": h.avg_buy_price,
            "total_invested": h.total_invested,
            "entry_yield_pct": h.entry_yield_pct or None,
        }
        if q and q.is_valid:
            value = round(h.shares * q.price, 2)
            total_value += value
            row.update({
                "current_price": q.price,
                "current_yield_pct": q.yield_pct,
                "current_value": value,
                "unrealized_pnl": round(value - h.total_invested, 2),
                "pct_change": round(
                    (q.price - h.avg_buy_price) / h.avg_buy_price * 100, 1
                ) if h.avg_buy_price else None,
            })
        else:
            row["fetch_error"] = (q.error if q else "price not available")
        rows.append(row)

    total_invested = sum(h.total_invested for h in holdings)

    return {
        "holdings": json.dumps(rows, indent=2, ensure_ascii=False),
        "total_invested": f"₹{total_invested:,.0f}",
        "total_value": f"₹{total_value:,.0f}" if total_value else "unavailable",
        "goals": json.dumps(
            {k: f"₹{v:,}" for k, v in cfg.goals.items()},
            indent=2,
            ensure_ascii=False,
        ),
        "today": date.today().strftime("%d %b %Y"),
    }
