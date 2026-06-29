"""dividend buy — record a buy you executed via your broker app."""
from __future__ import annotations

from datetime import date

import click

from ..config import Config
from ..md_io import (
    Holding, Transaction,
    read_portfolio, write_portfolio,
    read_watchlist,
    append_transaction,
)
from shared.market_data import fetch_quotes


@click.command("buy")
@click.option("--ticker", required=True, help="NSE ticker symbol, e.g. HDFCBANK")
@click.option("--shares", required=True, type=float, help="Number of shares purchased")
@click.option("--price", required=True, type=float, help="Price per share in ₹")
@click.option(
    "--investable-amount", "investable_amount",
    type=float, default=0.0, show_default=False,
    help="Total cash you had available at buy time (audit trail only, optional)",
)
@click.option("--company", default="", help="Company name — for new holdings not in watchlist")
@click.option("--sector", default="", help="Sector — for new holdings not in watchlist")
@click.option("--notes", default="", help="Optional free-text notes")
@click.pass_context
def buy_cmd(
    ctx: click.Context,
    ticker: str,
    shares: float,
    price: float,
    investable_amount: float,
    company: str,
    sector: str,
    notes: str,
) -> None:
    """Record a buy transaction in portfolio.md and transactions.md.

    \b
    For new holdings the tool auto-populates company/sector from the watchlist.
    If the ticker isn't in your watchlist either, pass --company and --sector
    explicitly, or it will fall back to a yfinance lookup.
    """
    cfg: Config = ctx.obj["config"]

    if shares <= 0:
        raise click.BadParameter("must be > 0", param_hint="'--shares'")
    if price <= 0:
        raise click.BadParameter("must be > 0", param_hint="'--price'")

    ticker = ticker.upper().strip()
    amount = round(shares * price, 2)
    today = date.today().isoformat()

    holdings = read_portfolio(cfg.portfolio_path)
    watchlist = read_watchlist(cfg.watchlist_path)
    existing = next((h for h in holdings if h.ticker.upper() == ticker), None)

    # Pre-compute top-up values so both branches can reference them after confirm
    new_total = new_shares = new_avg = 0.0
    final_company = final_sector = ""
    final_entry_yield = 0.0

    if existing:
        new_total = round(existing.total_invested + amount, 2)
        new_shares = existing.shares + shares
        new_avg = round(new_total / new_shares, 2)
        final_company = existing.company
        final_sector = existing.sector

        click.echo("\nAbout to record:\n")
        click.echo(f"  TOP-UP: {ticker} — {existing.company}")
        click.echo(f"  +{shares:g} shares @ ₹{price:,.2f} = ₹{amount:,.2f}")
        click.echo(f"  Shares         : {existing.shares:g} → {new_shares:g}")
        click.echo(f"  Avg buy price  : ₹{existing.avg_buy_price:,.2f} → ₹{new_avg:,.2f}")
        click.echo(f"  Total invested : ₹{existing.total_invested:,.2f} → ₹{new_total:,.2f}")
    else:
        final_company, final_sector, final_entry_yield = _resolve_metadata(
            ticker, company, sector, watchlist, cfg
        )

        click.echo("\nAbout to record:\n")
        click.echo(f"  NEW HOLDING: {ticker} — {final_company} ({final_sector})")
        click.echo(f"  {shares:g} shares @ ₹{price:,.2f} = ₹{amount:,.2f}")

    click.echo()
    if not click.confirm("Proceed?", default=False):
        click.echo("Cancelled.")
        return

    # Apply
    if existing:
        idx = next(i for i, h in enumerate(holdings) if h.ticker.upper() == ticker)
        holdings[idx] = Holding(
            ticker=existing.ticker,
            company=existing.company,
            sector=existing.sector,
            shares=new_shares,
            avg_buy_price=new_avg,
            total_invested=new_total,
            date_added=existing.date_added,
            last_reviewed=existing.last_reviewed,
            notes=notes or existing.notes,
            entry_yield_pct=existing.entry_yield_pct,  # preserve original entry yield
        )
    else:
        holdings.append(Holding(
            ticker=ticker,
            company=final_company,
            sector=final_sector,
            shares=shares,
            avg_buy_price=price,
            total_invested=amount,
            date_added=today,
            last_reviewed="",
            notes=notes,
            entry_yield_pct=final_entry_yield,
        ))

    write_portfolio(cfg.portfolio_path, holdings)
    append_transaction(
        cfg.transactions_path,
        Transaction(
            date=today,
            type="BUY",
            ticker=ticker,
            company=final_company,
            shares=shares,
            price=price,
            amount=amount,
            investable_amount=investable_amount,
            notes=notes,
        ),
    )

    click.echo(f"\n✓  Recorded. portfolio.md and transactions.md updated.")


def _resolve_metadata(
    ticker: str,
    company_arg: str,
    sector_arg: str,
    watchlist: list,
    cfg: Config,
) -> tuple[str, str, float]:
    """Resolve company name, sector, and entry yield for a new holding.

    Priority for company/sector:
      1. Explicit --company / --sector CLI args
      2. Matching row in watchlist.md
      3. yfinance lookup
      4. Fallback: company = ticker, sector = "Unknown"

    Entry yield is fetched from yfinance (using cache when fresh), falling
    back to watchlist yield, then 0.0 if both fail.

    Returns: (company, sector, entry_yield_pct)
    """
    company = company_arg.strip()
    sector = sector_arg.strip()
    watchlist_yield = 0.0

    if not company or not sector:
        watch = next(
            (w for w in watchlist if w.ticker.upper() == ticker), None
        )
        if watch:
            company = company or watch.company
            sector = sector or watch.sector
            watchlist_yield = watch.yield_pct

    # Fetch from yfinance to get current yield as entry yield.
    # Result is cached, so this is fast on repeat runs.
    entry_yield = watchlist_yield
    ns_ticker = f"{ticker}.NS" if "." not in ticker else ticker
    try:
        results = fetch_quotes([ns_ticker], cfg.cache_path, cfg.cache_expiry_hours)
        r = results.get(ns_ticker)
        if r and r.is_valid:
            company = company or r.company_name or ""
            if r.yield_pct:
                entry_yield = r.yield_pct
    except Exception:
        pass

    return company or ticker, sector or "Unknown", entry_yield
