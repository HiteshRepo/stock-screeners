"""dividend status — portfolio dashboard."""
from __future__ import annotations

from datetime import date

import click

from ..config import Config
from ..md_io import Holding, read_portfolio
from shared.market_data import QuoteResult, fetch_quotes


@click.command("status")
@click.option(
    "--refresh", is_flag=True, default=False,
    help="Force-refresh cached market data (ignores cache expiry)",
)
@click.pass_context
def status_cmd(ctx: click.Context, refresh: bool) -> None:
    """Show portfolio dashboard: value, income, sector allocation, goal progress."""
    cfg: Config = ctx.obj["config"]
    holdings = read_portfolio(cfg.portfolio_path)

    if not holdings:
        click.echo(
            "Portfolio is empty. Use `divvy buy --ticker <TICKER> --shares <N> --price <PRICE>` "
            "to add your first holding."
        )
        return

    # Fetch market data
    tickers = [h.ns_ticker for h in holdings]
    stale_hint = "" if refresh else " (use --refresh to force update)"
    click.echo(f"Fetching prices for {len(tickers)} holding(s){stale_hint}…\n")
    quotes = fetch_quotes(
        tickers,
        cfg.cache_path,
        cfg.cache_expiry_hours,
        force_refresh=refresh,
        on_fetch=lambda t: click.echo(f"  ↓ {t}", err=True),
    )

    # Enrich holdings
    valid_rows: list[tuple[Holding, QuoteResult]] = []
    error_rows: list[tuple[Holding, str]] = []

    for h in holdings:
        q = quotes.get(h.ns_ticker)
        if q and q.is_valid:
            valid_rows.append((h, q))
        else:
            error_msg = (q.error if q else "not fetched") or "unknown error"
            error_rows.append((h, error_msg))

    _print_holdings_table(valid_rows, error_rows)
    _print_summary(valid_rows, error_rows)
    _print_sector_allocation(valid_rows)
    _print_goals(valid_rows, cfg.goals)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_holdings_table(
    valid_rows: list[tuple[Holding, QuoteResult]],
    error_rows: list[tuple[Holding, str]],
) -> None:
    headers = ["Ticker", "Company", "Sector", "Shs", "Avg Buy", "Curr", "Value", "P&L"]

    # Build display rows
    rows: list[list[str]] = []
    for h, q in valid_rows:
        value = h.shares * q.price
        pnl = value - h.total_invested
        pnl_pct = (pnl / h.total_invested * 100) if h.total_invested > 0 else 0.0
        pnl_sign = "+" if pnl >= 0 else ""
        rows.append([
            h.ticker,
            _truncate(h.company, 24),
            _truncate(h.sector, 12),
            f"{h.shares:g}",
            f"{h.avg_buy_price:,.2f}",
            f"{q.price:,.2f}",
            f"{value:,.2f}",
            f"{pnl_sign}{pnl:,.0f} ({pnl_sign}{pnl_pct:.1f}%)",
        ])
    for h, err in error_rows:
        rows.append([
            h.ticker,
            _truncate(h.company, 24),
            _truncate(h.sector, 12),
            f"{h.shares:g}",
            f"{h.avg_buy_price:,.2f}",
            f"⚠ {_truncate(err, 22)}",
            "—",
            "—",
        ])

    widths = [
        max(len(str(r[i])) for r in ([headers] + rows))
        for i in range(len(headers))
    ]

    def fmt(cells: list[str]) -> str:
        return "  " + "  ".join(f"{c:<{widths[i]}}" for i, c in enumerate(cells))

    sep = "  " + "  ".join("─" * w for w in widths)

    total = len(valid_rows) + len(error_rows)
    click.echo(f"Holdings ({total})")
    click.echo(fmt(headers))
    click.echo(sep)
    for row in rows:
        click.echo(fmt(row))
    click.echo(sep)


def _print_summary(
    valid_rows: list[tuple[Holding, QuoteResult]],
    error_rows: list[tuple[Holding, str]],
) -> None:
    total_invested = sum(h.total_invested for h, _ in valid_rows)
    total_invested += sum(h.total_invested for h, _ in error_rows)

    market_value = sum(h.shares * q.price for h, q in valid_rows)
    pnl = market_value - sum(h.total_invested for h, _ in valid_rows)
    pnl_pct = (pnl / sum(h.total_invested for h, _ in valid_rows) * 100) if valid_rows else 0.0

    annual_income = sum(
        h.shares * q.price * (q.yield_pct or 0) / 100
        for h, q in valid_rows
    )
    yield_on_cost = (annual_income / total_invested * 100) if total_invested > 0 else 0.0

    click.echo()
    click.echo("Summary")
    click.echo(f"  Total invested     ₹{total_invested:>14,.2f}")
    if valid_rows:
        pnl_sign = "+" if pnl >= 0 else ""
        click.echo(
            f"  Market value       ₹{market_value:>14,.2f}"
            f"    {pnl_sign}₹{pnl:,.2f} ({pnl_sign}{pnl_pct:.1f}%)"
        )
        click.echo(
            f"  Annual div income  ₹{annual_income:>14,.0f} est."
            f"    ({yield_on_cost:.1f}% yield on cost)"
        )
    if error_rows:
        click.echo(
            f"\n  ⚠  {len(error_rows)} holding(s) excluded from totals "
            f"(price fetch failed): "
            + ", ".join(h.ticker for h, _ in error_rows)
        )


def _print_sector_allocation(valid_rows: list[tuple[Holding, QuoteResult]]) -> None:
    if not valid_rows:
        return

    sector_values: dict[str, float] = {}
    for h, q in valid_rows:
        sector_values[h.sector] = sector_values.get(h.sector, 0) + h.shares * q.price

    total_value = sum(sector_values.values())
    if total_value == 0:
        return

    click.echo()
    click.echo("Sector allocation  (by current value)")

    # Sort descending by value
    sorted_sectors = sorted(sector_values.items(), key=lambda x: x[1], reverse=True)
    label_width = max(len(s) for s, _ in sorted_sectors)

    for sector, value in sorted_sectors:
        pct = value / total_value * 100
        bar = _bar(pct, width=28)
        click.echo(f"  {sector:<{label_width}}  {pct:5.1f}%  {bar}  ₹{value:,.0f}")


def _print_goals(valid_rows: list[tuple[Holding, QuoteResult]], goals: dict[str, int]) -> None:
    if not goals or not valid_rows:
        return

    total_market_value = sum(h.shares * q.price for h, q in valid_rows)

    click.echo()
    click.echo("Goals  (progress = current portfolio value / target)")

    for name, target in goals.items():
        pct = min(total_market_value / target * 100, 100) if target > 0 else 0.0
        bar = _bar(pct, width=28)
        click.echo(
            f"  {name}    ₹{total_market_value:,.0f} / ₹{target:,.0f}"
            f"    {bar}  {pct:.1f}%"
        )


# ---------------------------------------------------------------------------
# Formatting utilities
# ---------------------------------------------------------------------------

def _bar(pct: float, width: int = 28) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"
