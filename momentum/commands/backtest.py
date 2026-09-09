"""momentum backtest — simulate monthly rebalancing and report CAGR / drawdown / turnover."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import click

from ..backtest import BacktestResult, run_backtest
from ..config import MomentumConfig
from ..store import PriceStore
from ..universe import get_symbols


def _pct(v: float) -> str:
    return f"{v * 100:+.1f}%"


def _print_report(result: BacktestResult, verbose: bool) -> None:
    first = result.monthly_results[0].rebalance_date
    last = result.monthly_results[-1].rebalance_date

    click.echo()
    click.echo("=" * 62)
    click.echo("  BACKTEST REPORT")
    click.echo("=" * 62)
    click.echo(f"  Period           {first}  →  {last}")
    click.echo(f"  Months           {result.total_months}")
    click.echo(f"  Total return     {_pct(result.total_return)}")
    click.echo(f"  CAGR             {_pct(result.cagr)}")
    click.echo(f"  Max drawdown     {_pct(result.max_drawdown)}")
    click.echo(f"  Sharpe (annual)  {result.sharpe_ratio:.2f}")
    click.echo(f"  Avg turnover/mo  {result.avg_monthly_turnover * 100:.1f}%")
    click.echo()
    click.echo(result.survivorship_bias_note)

    if verbose:
        click.echo()
        click.echo(f"  {'Date':<12}  {'Return':>8}  {'Turnover':>9}  {'Scored':>7}")
        click.echo("  " + "-" * 44)
        for r in result.monthly_results:
            click.echo(
                f"  {r.rebalance_date!s:<12}  "
                f"{_pct(r.month_return):>8}  "
                f"{r.turnover * 100:>8.1f}%  "
                f"{r.n_scored:>7}"
            )


def _write_md(path: Path, result: BacktestResult) -> None:
    first = result.monthly_results[0].rebalance_date
    last = result.monthly_results[-1].rebalance_date

    lines = [
        "# Momentum Backtest Report",
        "",
        f"**Period**: {first} → {last}  ",
        f"**Months**: {result.total_months}  ",
        f"**CAGR**: {_pct(result.cagr)}  ",
        f"**Max Drawdown**: {_pct(result.max_drawdown)}  ",
        f"**Sharpe**: {result.sharpe_ratio:.2f}  ",
        f"**Avg Turnover/mo**: {result.avg_monthly_turnover * 100:.1f}%  ",
        f"**Total Return**: {_pct(result.total_return)}  ",
        "",
        result.survivorship_bias_note,
        "",
        "## Monthly Results",
        "",
        "| Date | Return | Turnover | N Scored | Additions | Removals |",
        "|------|--------|----------|----------|-----------|---------|",
    ]
    for r in result.monthly_results:
        adds = ", ".join(r.additions[:5]) + ("…" if len(r.additions) > 5 else "")
        rems = ", ".join(r.removals[:5]) + ("…" if len(r.removals) > 5 else "")
        lines.append(
            f"| {r.rebalance_date} "
            f"| {_pct(r.month_return)} "
            f"| {r.turnover * 100:.1f}% "
            f"| {r.n_scored} "
            f"| {adds} "
            f"| {rems} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


@click.command("backtest")
@click.option("--start", required=True, metavar="YYYY-MM-DD", help="Backtest start date.")
@click.option(
    "--end", default=None, metavar="YYYY-MM-DD",
    help="Backtest end date.  Defaults to today.",
)
@click.option("--top-n", default=None, type=int, help="Override portfolio size.")
@click.option(
    "--secondary", is_flag=True, default=False,
    help=(
        "Enable all secondary filters (pct-positive-days, dist-52w-high, Sharpe).  "
        "Compare results with and without this flag to see what each filter adds."
    ),
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Print monthly breakdown.")
@click.option(
    "--output", default=None, type=click.Path(),
    help="Write a markdown report to this file path.",
)
@click.pass_context
def backtest_cmd(
    ctx: click.Context,
    start: str,
    end: str | None,
    top_n: int | None,
    secondary: bool,
    verbose: bool,
    output: str | None,
) -> None:
    """
    Simulate monthly momentum rebalancing and report performance.

    Run baseline first (no --secondary), then with --secondary to see what each
    filter contributes before deciding whether to include it in the live strategy.

    Example — 5-year baseline backtest:

      momo backtest --start 2020-01-01 --end 2024-12-31 -v

    Example — with all secondary filters:

      momo backtest --start 2020-01-01 --end 2024-12-31 --secondary --output report.md
    """
    cfg: MomentumConfig = ctx.obj["config"]

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError as e:
        raise click.BadParameter(str(e))

    symbols = get_symbols(cfg.universe_path)
    if not symbols:
        raise click.UsageError(
            f"Universe file is empty or missing: {cfg.universe_path}\n"
            "Populate momentum/data/nifty500.csv with NSE symbols, then run:\n"
            "  momo fetch --start YYYY-MM-DD --end YYYY-MM-DD"
        )

    scoring = cfg.scoring
    if top_n is not None:
        scoring = replace(scoring, top_n=top_n)
    if secondary:
        scoring = replace(
            scoring,
            use_pct_positive_days=True,
            use_dist_from_52w_high=True,
            use_sharpe_ratio=True,
        )

    click.echo(f"Backtesting  {start_date} → {end_date}")
    click.echo(f"Universe:    {len(symbols)} symbols")
    click.echo(
        f"Strategy:    top {scoring.top_n}, "
        f"{scoring.lookback_months}m excl last {scoring.skip_recent_months}m, "
        f"min TV ₹{scoring.min_daily_traded_value_cr:.0f}cr"
    )
    if secondary:
        click.echo("Filters:     pct-positive-days + dist-52w-high + Sharpe")

    store = PriceStore(cfg.db_path)
    result = run_backtest(store, symbols, start_date, end_date, scoring)
    store.close()

    _print_report(result, verbose=verbose)

    if output:
        _write_md(Path(output), result)
        click.echo(f"\nReport written to: {output}")
