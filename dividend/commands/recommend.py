"""dividend recommend — suggest stocks to buy given an investable amount."""
from __future__ import annotations

import click

from ..config import Config
from ..md_io import read_portfolio, read_watchlist
from ..scoring import CandidateScore, build_rationale, score_candidates
from shared.market_data import fetch_quotes


@click.command("recommend")
@click.option("--amount", required=True, type=float, help="Investable amount in ₹")
@click.option(
    "--top", default=3, show_default=True,
    help="Number of recommendations to show",
)
@click.option(
    "--refresh", is_flag=True, default=False,
    help="Force-refresh cached market data",
)
@click.pass_context
def recommend_cmd(ctx: click.Context, amount: float, top: int, refresh: bool) -> None:
    """Score watchlist candidates and print top-N buy recommendations.

    \b
    Scoring factors (weights configurable in config.yaml in a future release):
      40%  Dividend yield
      35%  Sector diversification vs. current portfolio
      25%  Entry point (distance from 52-week high)

    This command is advisory only — it makes no changes to any file.
    Use `divvy buy` to record an actual purchase.
    """
    cfg: Config = ctx.obj["config"]

    if amount <= 0:
        raise click.BadParameter("must be > 0", param_hint="'--amount'")

    watchlist = read_watchlist(cfg.watchlist_path)
    holdings = read_portfolio(cfg.portfolio_path)

    if not watchlist:
        click.echo(
            "Watchlist is empty. Add candidate stocks to "
            f"{cfg.watchlist_path} first."
        )
        return

    # Fetch quotes for all watchlist candidates
    tickers = [item.ns_ticker for item in watchlist]
    click.echo(
        f"\nFetching data for {len(tickers)} watchlist candidate(s)…\n"
    )
    quotes = fetch_quotes(
        tickers,
        cfg.cache_path,
        cfg.cache_expiry_hours,
        force_refresh=refresh,
        on_fetch=lambda t: click.echo(f"  ↓ {t}", err=True),
    )

    # Report fetch failures
    failed = [
        item for item in watchlist
        if not (q := quotes.get(item.ns_ticker)) or not q.is_valid
    ]
    if failed:
        click.echo(
            f"  ⚠  {len(failed)} ticker(s) skipped (fetch failed): "
            + ", ".join(i.ticker for i in failed)
        )
        click.echo()

    # Score
    ranked = score_candidates(watchlist, quotes, holdings, budget=amount)

    if not ranked:
        click.echo(
            f"No affordable watchlist candidates found for ₹{amount:,.0f}.\n"
            "All valid tickers may be priced above your budget, "
            "or the watchlist has no valid quotes."
        )
        return

    # Build sector_totals for rationale text
    sector_totals: dict[str, float] = {}
    portfolio_total = sum(h.total_invested for h in holdings)
    for h in holdings:
        sector_totals[h.sector] = sector_totals.get(h.sector, 0) + h.total_invested

    # Display
    _print_header(amount)
    for rank, sc in enumerate(ranked[:top], start=1):
        _print_candidate(rank, sc, sector_totals, portfolio_total)
    _print_footer()


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_header(amount: float) -> None:
    click.echo(f"Recommendations for ₹{amount:,.0f}")
    click.echo("═" * 60)
    click.echo()


def _print_candidate(
    rank: int,
    sc: CandidateScore,
    sector_totals: dict[str, float],
    portfolio_total: float,
) -> None:
    q = sc.quote
    item = sc.item

    already = (
        f"  (already holding {sc.already_held_shares:g} shares)"
        if sc.already_held_shares > 0
        else ""
    )

    below_str = (
        f"  ({q.pct_below_52w_high:.1f}% below 52w high)"
        if q.pct_below_52w_high is not None
        else ""
    )

    rationale = build_rationale(sc, sector_totals, portfolio_total)

    click.echo(f"  #{rank}  {item.company} ({item.ticker}){already}")
    click.echo(
        f"       Sector: {item.sector}  |  "
        f"Price: ₹{q.price:,.2f}  |  "
        f"Can buy: {sc.max_shares} shares @ ₹{sc.cost_for_max_shares:,.2f}"
    )
    if q.yield_pct is not None:
        click.echo(
            f"       Yield: {q.yield_pct:.2f}%"
            + (f"  |  52w high: ₹{q.fifty_two_week_high:,.2f}{below_str}" if q.fifty_two_week_high else "")
        )
    click.echo(
        f"       Score: {sc.total_score:.2f}  "
        f"(yield {sc.yield_score:.2f} × 0.40 + "
        f"div {sc.div_score:.2f} × 0.35 + "
        f"value {sc.value_score:.2f} × 0.25)"
    )
    click.echo(f"       Why: {rationale}")
    click.echo()


def _print_footer() -> None:
    click.echo("─" * 60)
    click.echo(
        "  Advisory only. Use `divvy buy --ticker <TICKER> "
        "--shares <N> --price <PRICE>` to record a purchase."
    )
