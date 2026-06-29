"""dividend sell — record a sell you executed via your broker app."""
from __future__ import annotations

from datetime import date

import click

from ..config import Config
from ..md_io import (
    Holding, Transaction,
    read_portfolio, write_portfolio,
    append_transaction,
)


@click.command("sell")
@click.option("--ticker", required=True, help="NSE ticker symbol, e.g. HDFCBANK")
@click.option("--shares", required=True, type=float, help="Number of shares sold")
@click.option("--price", required=True, type=float, help="Sale price per share in ₹")
@click.option("--notes", default="", help="Optional free-text notes, e.g. reason for exit")
@click.pass_context
def sell_cmd(
    ctx: click.Context,
    ticker: str,
    shares: float,
    price: float,
    notes: str,
) -> None:
    """Record a sell transaction — reduces or removes a holding.

    Partial sells reduce the share count (avg buy price is preserved).
    Full sells remove the row from portfolio.md entirely.
    Both cases append an entry to transactions.md.
    """
    cfg: Config = ctx.obj["config"]

    if shares <= 0:
        raise click.BadParameter("must be > 0", param_hint="'--shares'")
    if price <= 0:
        raise click.BadParameter("must be > 0", param_hint="'--price'")

    ticker = ticker.upper().strip()
    holdings = read_portfolio(cfg.portfolio_path)
    existing = next((h for h in holdings if h.ticker.upper() == ticker), None)

    if existing is None:
        click.echo(f"Error: {ticker} not found in portfolio.", err=True)
        raise click.Abort()

    if shares > existing.shares:
        click.echo(
            f"Error: cannot sell {shares:g} shares — only {existing.shares:g} held.",
            err=True,
        )
        raise click.Abort()

    proceeds = round(shares * price, 2)
    cost_basis = round(shares * existing.avg_buy_price, 2)
    realized_pnl = round(proceeds - cost_basis, 2)
    pnl_pct = (realized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0
    remaining = existing.shares - shares

    click.echo("\nAbout to record:\n")
    click.echo(f"  SELL: {ticker} — {existing.company}")
    click.echo(f"  {shares:g} shares @ ₹{price:,.2f} = ₹{proceeds:,.2f}")
    click.echo(f"  Cost basis     : ₹{cost_basis:,.2f}")
    click.echo(f"  Realized P&L   : ₹{realized_pnl:+,.2f}  ({pnl_pct:+.1f}%)")
    if remaining == 0:
        click.echo(f"  After sell     : position closed (removed from portfolio)")
    else:
        new_invested = round(remaining * existing.avg_buy_price, 2)
        click.echo(f"  Remaining      : {remaining:g} shares  (₹{new_invested:,.2f} at cost)")

    click.echo()
    if not click.confirm("Proceed?", default=False):
        click.echo("Cancelled.")
        return

    today = date.today().isoformat()

    if remaining == 0:
        updated_holdings = [h for h in holdings if h.ticker.upper() != ticker]
    else:
        idx = next(i for i, h in enumerate(holdings) if h.ticker.upper() == ticker)
        updated_holdings = list(holdings)
        updated_holdings[idx] = Holding(
            ticker=existing.ticker,
            company=existing.company,
            sector=existing.sector,
            shares=remaining,
            avg_buy_price=existing.avg_buy_price,
            total_invested=round(remaining * existing.avg_buy_price, 2),
            date_added=existing.date_added,
            last_reviewed=existing.last_reviewed,
            notes=notes or existing.notes,
        )

    write_portfolio(cfg.portfolio_path, updated_holdings)
    append_transaction(
        cfg.transactions_path,
        Transaction(
            date=today,
            type="SELL",
            ticker=ticker,
            company=existing.company,
            shares=shares,
            price=price,
            amount=proceeds,
            investable_amount=0.0,
            notes=notes,
        ),
    )

    click.echo(f"\n✓  Recorded. portfolio.md and transactions.md updated.")
