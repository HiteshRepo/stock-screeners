"""
Monthly momentum backtest engine.

Simulates monthly rebalancing on the standard 12-month-skip-last-month
momentum factor over historical NSE bhavcopy data.

Key outputs:
  - CAGR, max drawdown, Sharpe ratio
  - Monthly turnover (proxy for STCG-taxable churn)
  - Per-month portfolio, additions, removals

Survivorship bias warning
-------------------------
This backtest uses whatever symbols are in the universe list at run time.
If that list only contains currently-listed stocks, results for earlier
periods will be upward-biased because companies that were delisted, went
bankrupt, or were removed from the index are absent.
To reduce bias: archive monthly index constituent snapshots and build a
point-in-time universe before re-running.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import ScoringConfig
from .scoring import score_universe
from .store import PriceStore


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class MonthlyResult:
    rebalance_date: date
    portfolio: list[str]
    month_return: float     # Equal-weight portfolio return for the next month
    turnover: float         # Fraction of portfolio positions changed vs prior month
    additions: list[str]
    removals: list[str]
    n_scored: int           # How many symbols had sufficient data to score


@dataclass
class BacktestResult:
    monthly_results: list[MonthlyResult]
    cagr: float
    max_drawdown: float
    avg_monthly_turnover: float
    sharpe_ratio: float
    total_months: int
    total_return: float
    portfolio_values: list[float]   # Normalised NAV starting at 1.0
    survivorship_bias_note: str
    config_used: ScoringConfig


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _end_of_month(d: date) -> date:
    """Last calendar day of the month containing d."""
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _rebalance_dates(start_date: date, end_date: date) -> list[date]:
    """
    Generate end-of-month dates spanning [start_date, end_date].

    The first date is the end of start_date's month; subsequent dates
    advance one month at a time.
    """
    dates: list[date] = []
    d = _end_of_month(start_date)
    while d <= end_date:
        dates.append(d)
        # Advance to end of next month
        year = d.year + (1 if d.month == 12 else 0)
        month = d.month % 12 + 1
        d = _end_of_month(date(year, month, 1))
    return dates


# ---------------------------------------------------------------------------
# Portfolio return
# ---------------------------------------------------------------------------

def _portfolio_return(
    store: PriceStore,
    symbols: list[str],
    from_date: date,
    to_date: date,
) -> float:
    """
    Compute the equal-weight return of symbols from from_date to to_date.

    Uses the last available close price on or before each date (within
    a 10-day search window to handle market holidays at month boundaries).
    Returns 0.0 if prices cannot be found for either date.
    """
    if not symbols:
        return 0.0

    buffer = timedelta(days=10)
    close_df = store.get_close_prices(symbols, from_date - buffer, to_date + buffer)
    if close_df.empty:
        return 0.0

    # Index is string dates YYYY-MM-DD; convert to DatetimeIndex for comparison
    dt_idx = pd.to_datetime(close_df.index)
    from_ts = pd.Timestamp(from_date)
    to_ts = pd.Timestamp(to_date)

    start_cands = dt_idx[dt_idx <= from_ts + timedelta(days=7)]
    end_cands = dt_idx[dt_idx <= to_ts + timedelta(days=7)]

    if start_cands.empty or end_cands.empty:
        return 0.0

    # Map back to original string labels for .loc access
    start_label = start_cands[-1].strftime("%Y-%m-%d")
    end_label = end_cands[-1].strftime("%Y-%m-%d")

    if start_label == end_label:
        return 0.0

    rets: list[float] = []
    for sym in symbols:
        if sym not in close_df.columns:
            continue
        sp = close_df.loc[start_label, sym] if start_label in close_df.index else None
        ep = close_df.loc[end_label, sym] if end_label in close_df.index else None
        if sp is None or ep is None:
            continue
        sp_f, ep_f = float(sp), float(ep)
        if np.isnan(sp_f) or np.isnan(ep_f) or sp_f <= 0:
            continue
        rets.append(ep_f / sp_f - 1.0)

    return float(np.mean(rets)) if rets else 0.0


# ---------------------------------------------------------------------------
# Main backtest
# ---------------------------------------------------------------------------

_SURVIVORSHIP_NOTE = (
    "⚠  Survivorship bias: this backtest uses only the symbols currently in the "
    "universe file.  Stocks that were delisted, went bankrupt, or were removed from "
    "the index during the backtest period are absent, which overstates historical "
    "returns — especially for periods more than 3–5 years ago.  To reduce bias, "
    "archive monthly index constituent snapshots and build a point-in-time universe."
)


def run_backtest(
    store: PriceStore,
    universe_symbols: list[str],
    start_date: date,
    end_date: date,
    config: ScoringConfig,
) -> BacktestResult:
    """
    Simulate monthly momentum rebalancing over [start_date, end_date].

    At each month-end rebalance date:
      1. Score all symbols with sufficient history.
      2. Select the top config.top_n by composite score.
      3. Hold equal-weight until the next rebalance date.
      4. Record return and turnover.

    Requires ≥2 rebalance dates in the range (i.e., at least one full month).
    """
    rebal_dates = _rebalance_dates(start_date, end_date)
    if len(rebal_dates) < 2:
        raise ValueError(
            f"Need ≥2 rebalance dates in range {start_date}–{end_date}; "
            f"got {len(rebal_dates)}.  Widen the date range."
        )

    monthly_results: list[MonthlyResult] = []
    portfolio_values: list[float] = [1.0]
    prev_portfolio: list[str] = []

    for i, rebal_date in enumerate(rebal_dates[:-1]):
        next_date = rebal_dates[i + 1]

        scored = score_universe(store, universe_symbols, rebal_date, config)

        # Prefer clean signals; fall back to all if nothing passes
        clean = [s for s in scored if not s.has_corporate_action]
        if not clean:
            clean = scored

        top_symbols = [s.symbol for s in clean[: config.top_n]]

        prev_set = set(prev_portfolio)
        curr_set = set(top_symbols)
        additions = sorted(curr_set - prev_set)
        removals = sorted(prev_set - curr_set)
        turnover = len(additions) / max(len(curr_set), 1)

        month_ret = _portfolio_return(store, top_symbols, rebal_date, next_date)
        portfolio_values.append(portfolio_values[-1] * (1.0 + month_ret))

        monthly_results.append(MonthlyResult(
            rebalance_date=rebal_date,
            portfolio=top_symbols,
            month_return=month_ret,
            turnover=turnover,
            additions=additions,
            removals=removals,
            n_scored=len(scored),
        ))

        prev_portfolio = top_symbols

    if not monthly_results:
        raise ValueError("No monthly results generated — check universe and date range.")

    rets = np.array([r.month_return for r in monthly_results])
    pv = np.array(portfolio_values)

    total_months = len(monthly_results)
    years = total_months / 12.0
    total_return = float(pv[-1] - 1.0)
    cagr = float(pv[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0

    rolling_max = np.maximum.accumulate(pv)
    drawdowns = (pv - rolling_max) / rolling_max
    max_drawdown = float(drawdowns.min())

    sharpe = 0.0
    if rets.std() > 0:
        sharpe = float(rets.mean() / rets.std() * np.sqrt(12))

    avg_turnover = float(np.mean([r.turnover for r in monthly_results]))

    return BacktestResult(
        monthly_results=monthly_results,
        cagr=cagr,
        max_drawdown=max_drawdown,
        avg_monthly_turnover=avg_turnover,
        sharpe_ratio=sharpe,
        total_months=total_months,
        total_return=total_return,
        portfolio_values=portfolio_values,
        survivorship_bias_note=_SURVIVORSHIP_NOTE,
        config_used=config,
    )
