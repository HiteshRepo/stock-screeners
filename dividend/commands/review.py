"""dividend review — flag holdings that may need attention."""
from __future__ import annotations

from datetime import date

import click

from ..config import Config
from ..md_io import Holding, read_portfolio, write_portfolio
from shared.market_data import QuoteResult, fetch_quotes


# Symbols used in output
_OK = "✅"
_WARN = "⚠ "
_ERR = "❌"


@click.command("review")
@click.option(
    "--refresh", is_flag=True, default=False,
    help="Force-refresh cached market data before reviewing",
)
@click.pass_context
def review_cmd(ctx: click.Context, refresh: bool) -> None:
    """Fetch latest prices and flag holdings with yield or price drops.

    \b
    Flags triggered by thresholds in config.yaml:
      price_drop_pct  — flag if current price is this % below avg buy price
      yield_drop_pct  — flag if yield dropped this % relative to entry yield
                        (requires entry_yield_pct to have been recorded at buy time)

    The command is read-only for investment decisions: it updates only the
    'Last Reviewed' date in portfolio.md, not any share counts or prices.
    """
    cfg: Config = ctx.obj["config"]
    holdings = read_portfolio(cfg.portfolio_path)

    if not holdings:
        click.echo("Portfolio is empty. Nothing to review.")
        return

    tickers = [h.ns_ticker for h in holdings]
    click.echo(f"Fetching prices for {len(tickers)} holding(s)…\n")
    quotes = fetch_quotes(
        tickers,
        cfg.cache_path,
        cfg.cache_expiry_hours,
        force_refresh=refresh,
        on_fetch=lambda t: click.echo(f"  ↓ {t}", err=True),
    )

    today = date.today().isoformat()
    n_ok = n_warn = n_err = 0
    updated_holdings: list[Holding] = []

    _print_header()

    for h in holdings:
        q = quotes.get(h.ns_ticker)

        if not q or not q.is_valid:
            error_msg = (q.error if q else "not fetched") or "unknown error"
            click.echo(f"{_ERR}  {h.ticker:<12} {h.company:<28} ({h.sector})")
            click.echo(f"     Fetch failed: {error_msg}")
            click.echo()
            n_err += 1
            updated_holdings.append(h)  # unchanged — can't assess
            continue

        flags = _check_flags(h, q, cfg)
        assessed_holding = _replace(h, last_reviewed=today)

        if flags:
            n_warn += 1
            click.echo(f"{_WARN} {h.ticker:<12} {h.company:<28} ({h.sector})")
        else:
            n_ok += 1
            click.echo(f"{_OK}  {h.ticker:<12} {h.company:<28} ({h.sector})")

        _print_holding_detail(h, q, flags)
        click.echo()
        updated_holdings.append(assessed_holding)

    _print_footer(n_ok, n_warn, n_err)

    # Write back only the last_reviewed dates — no investment data changed
    write_portfolio(cfg.portfolio_path, updated_holdings)
    assessed = n_ok + n_warn
    click.echo(f"  last_reviewed updated for {assessed} holding(s) in portfolio.md.")


# ---------------------------------------------------------------------------
# Flag checks
# ---------------------------------------------------------------------------

def _check_flags(h: Holding, q: QuoteResult, cfg: Config) -> list[str]:
    """Return a list of human-readable flag strings (empty = no issues)."""
    flags: list[str] = []

    # Price drop check
    if h.avg_buy_price > 0:
        price_change_pct = (q.price - h.avg_buy_price) / h.avg_buy_price * 100
        if price_change_pct < -cfg.price_drop_pct:
            flags.append(
                f"price ₹{q.price:,.2f} is {abs(price_change_pct):.1f}% below "
                f"avg buy ₹{h.avg_buy_price:,.2f} (threshold: {cfg.price_drop_pct:.0f}%)"
            )

    # Yield drop check (only if we recorded entry yield at buy time)
    current_yield = q.yield_pct or 0.0
    if h.entry_yield_pct > 0:
        relative_drop = (current_yield - h.entry_yield_pct) / h.entry_yield_pct * 100
        if relative_drop < -cfg.yield_drop_pct:
            flags.append(
                f"yield fell from {h.entry_yield_pct:.2f}% → {current_yield:.2f}% "
                f"({abs(relative_drop):.1f}% relative drop, threshold: {cfg.yield_drop_pct:.0f}%)"
            )

    return flags


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_header() -> None:
    today = date.today().strftime("%d %b %Y")
    click.echo(f"Divvy — Portfolio Review  ({today})")
    click.echo("─" * 70)
    click.echo()


def _print_footer(n_ok: int, n_warn: int, n_err: int) -> None:
    total = n_ok + n_warn + n_err
    click.echo("─" * 70)
    parts = [f"{total} holding(s) reviewed"]
    if n_ok:
        parts.append(f"{_OK} {n_ok} fine")
    if n_warn:
        parts.append(f"{_WARN}{n_warn} need review")
    if n_err:
        parts.append(f"{_ERR} {n_err} fetch error")
    click.echo("  " + "  |  ".join(parts))
    click.echo()


def _print_holding_detail(h: Holding, q: QuoteResult, flags: list[str]) -> None:
    price_chg = (q.price - h.avg_buy_price) / h.avg_buy_price * 100 if h.avg_buy_price else 0
    sign = "+" if price_chg >= 0 else ""
    current_yield = q.yield_pct or 0.0

    price_line = (
        f"     ₹{q.price:,.2f}  (avg buy ₹{h.avg_buy_price:,.2f}  |  "
        f"{sign}{price_chg:.1f}%)"
    )
    if h.entry_yield_pct > 0:
        yield_chg = (current_yield - h.entry_yield_pct) / h.entry_yield_pct * 100
        y_sign = "+" if yield_chg >= 0 else ""
        price_line += (
            f"  |  yield {current_yield:.2f}%  "
            f"(entry {h.entry_yield_pct:.2f}%  |  {y_sign}{yield_chg:.1f}%)"
        )
    else:
        price_line += f"  |  yield {current_yield:.2f}%  (no entry yield recorded)"

    click.echo(price_line)

    for flag in flags:
        click.echo(f"     ↳ {flag}")


def _replace(h: Holding, **kwargs) -> Holding:
    """Return a new Holding with the given fields replaced (immutable update)."""
    from dataclasses import asdict
    data = asdict(h)
    data.update(kwargs)
    return Holding(**data)
