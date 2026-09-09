"""dividend watch — add a stock to the watchlist, auto-populating data from yfinance
with screener.in as a fallback for missing or unavailable fields."""
from __future__ import annotations

from datetime import date

import click

from ..config import Config
from ..md_io import WatchlistItem, read_watchlist, write_watchlist
from shared.market_data import fetch_quotes
from shared.screener import fetch_quote as screener_fetch_quote


@click.command("watch")
@click.option("--ticker", required=True, help="NSE ticker symbol, e.g. HDFCBANK")
@click.option("--notes", default="", help="Optional free-text notes")
@click.pass_context
def watch_cmd(ctx: click.Context, ticker: str, notes: str) -> None:
    """Add a stock to watchlist.md, fetching fundamentals automatically.

    \b
    Data is fetched from yfinance first; screener.in fills in any missing
    fields (sector, payout ratio) and acts as a full fallback if yfinance
    fails entirely. Pass --notes for any personal annotation.
    """
    cfg: Config = ctx.obj["config"]
    ticker = ticker.upper().strip()

    watchlist = read_watchlist(cfg.watchlist_path)
    if any(w.ticker.upper() == ticker for w in watchlist):
        raise click.ClickException(f"{ticker} is already in your watchlist.")

    ns_ticker = f"{ticker}.NS" if "." not in ticker else ticker

    click.echo(f"Fetching data for {ticker}…")
    yf_results = fetch_quotes(
        [ns_ticker],
        cfg.cache_path,
        cfg.cache_expiry_hours,
        force_refresh=True,
    )
    yf = yf_results.get(ns_ticker)

    click.echo("Fetching data from screener.in…")
    sc = screener_fetch_quote(ticker)

    yf_ok = yf is not None and yf.is_valid

    if not yf_ok and sc is None:
        error = yf.error if yf else "No result returned"
        raise click.ClickException(
            f"Could not fetch data for {ticker} from yfinance ({error}) "
            "or screener.in."
        )

    # Merge: prefer yfinance, fill gaps from screener.in
    company = (yf.company_name if yf_ok else None) or (sc.company_name if sc else None) or ticker
    yield_pct = (yf.yield_pct if yf_ok else None) or (sc.yield_pct if sc else None) or 0.0
    payout_ratio_pct = (yf.payout_ratio_pct if yf_ok else None) or (sc.payout_ratio_pct if sc else None) or 0.0
    sector = (sc.sector if sc else None) or "Unknown"

    click.echo("\nAbout to add to watchlist:\n")
    click.echo(f"  Ticker         : {ticker}")
    click.echo(f"  Company        : {company}")
    click.echo(f"  Sector         : {sector}")
    click.echo(f"  Yield          : {yield_pct:.2f}%")
    click.echo(f"  Payout Ratio   : {payout_ratio_pct:.2f}%")
    if notes:
        click.echo(f"  Notes          : {notes}")
    click.echo()

    if not click.confirm("Proceed?", default=False):
        click.echo("Cancelled.")
        return

    watchlist.append(WatchlistItem(
        ticker=ticker,
        company=company,
        sector=sector,
        yield_pct=yield_pct,
        payout_ratio_pct=payout_ratio_pct,
        notes=notes,
        date_added=date.today().isoformat(),
    ))
    write_watchlist(cfg.watchlist_path, watchlist)
    click.echo(f"\n✓  {ticker} added to watchlist.")
