"""
Momentum scoring — rank NSE stocks by trailing momentum with optional secondary filters.

Core signal: 12-month return, excluding the most recent month.
  - Lookback window: [as_of - skip_months - lookback_months,  as_of - skip_months]
  - Skipping the most recent month avoids short-term reversal noise.

Secondary filters (each toggleable via ScoringConfig):
  - pct_positive_days  : fraction of trading days with positive daily return
  - dist_from_52w_high : (last_close / 52w_high) - 1  (0 = at high, negative = below)
  - sharpe_ratio       : annualised mean/std of daily returns (0 risk-free rate)

Composite score = weighted average of rank-normalised components.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import ScoringConfig
from .store import PriceStore


@dataclass
class MomentumScore:
    symbol: str
    rank: int
    momentum_return: float           # e.g. 0.35 = 35% gain over the lookback window
    avg_traded_value_cr: float       # average daily traded value in ₹ crore
    pct_positive_days: float | None  # fraction of days with positive daily return
    dist_from_52w_high: float | None # (close / 52w_high) - 1
    sharpe_ratio: float | None       # annualised Sharpe (0 risk-free)
    composite_score: float           # final ranking score (higher = better)
    has_corporate_action: bool       # suspicious single-day move detected
    data_quality: str                # "ok" | "sparse" | "corporate_action"


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _subtract_months(d: date, n: int) -> date:
    """Return d minus n calendar months, clamped to the last day of the target month."""
    month = d.month - n
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _last_on_or_before(
    dt_index: pd.DatetimeIndex, target: pd.Timestamp
) -> pd.Timestamp | None:
    """Latest entry in dt_index that is <= target, or None."""
    candidates = dt_index[dt_index <= target]
    return candidates[-1] if not candidates.empty else None


# ---------------------------------------------------------------------------
# Individual metric calculators
# All accept a Series with string date index (YYYY-MM-DD) and float values.
# ---------------------------------------------------------------------------

def _detect_corporate_action(prices: pd.Series, threshold: float) -> bool:
    """True if any single-day return exceeds threshold in absolute value."""
    daily_ret = prices.pct_change().dropna()
    return bool((daily_ret.abs() > threshold).any())


def _momentum_return(
    prices: pd.Series,
    config: ScoringConfig,
    as_of: date,
) -> float | None:
    """
    Compute (end_price / start_price) - 1.

    end_date   = last trading day on or before (as_of - skip_months)
    start_date = last trading day on or before (as_of - skip_months - lookback_months)
    """
    if prices.empty:
        return None

    dt_idx = pd.to_datetime(prices.index)
    prices_dt = prices.copy()
    prices_dt.index = dt_idx

    end_target = pd.Timestamp(_subtract_months(as_of, config.skip_recent_months))
    start_target = pd.Timestamp(
        _subtract_months(as_of, config.skip_recent_months + config.lookback_months)
    )

    end_ts = _last_on_or_before(dt_idx, end_target)
    start_ts = _last_on_or_before(dt_idx, start_target)

    if end_ts is None or start_ts is None or end_ts <= start_ts:
        return None

    end_p = float(prices_dt[end_ts])
    start_p = float(prices_dt[start_ts])

    if start_p <= 0:
        return None
    return (end_p / start_p) - 1.0


def _pct_positive_days(
    prices: pd.Series,
    window_months: int,
    as_of: date,
) -> float | None:
    """Fraction of trading days with a positive daily return in the last window_months."""
    if prices.empty:
        return None

    dt_idx = pd.to_datetime(prices.index)
    prices_dt = prices.copy()
    prices_dt.index = dt_idx

    cutoff = pd.Timestamp(_subtract_months(as_of, window_months))
    as_of_ts = pd.Timestamp(as_of)
    window = prices_dt[(prices_dt.index >= cutoff) & (prices_dt.index <= as_of_ts)]

    if len(window) < 10:
        return None
    daily_ret = window.pct_change().dropna()
    return float((daily_ret > 0).mean())


def _dist_from_52w_high(prices: pd.Series, as_of: date) -> float | None:
    """
    (last_close / 52w_high) - 1.
    0 = at the 52-week high.  Negative = below the high.
    """
    if prices.empty:
        return None

    dt_idx = pd.to_datetime(prices.index)
    prices_dt = prices.copy()
    prices_dt.index = dt_idx

    as_of_ts = pd.Timestamp(as_of)
    cutoff = pd.Timestamp(_subtract_months(as_of, 12))
    window = prices_dt[(prices_dt.index >= cutoff) & (prices_dt.index <= as_of_ts)]

    if window.empty:
        return None

    high_52w = float(window.max())
    last_close = float(prices_dt[prices_dt.index <= as_of_ts].iloc[-1])

    if high_52w <= 0:
        return None
    return (last_close / high_52w) - 1.0


def _sharpe_ratio(
    prices: pd.Series,
    lookback_months: int,
    as_of: date,
) -> float | None:
    """Annualised Sharpe ratio (risk-free rate = 0) over the last lookback_months."""
    if prices.empty:
        return None

    dt_idx = pd.to_datetime(prices.index)
    prices_dt = prices.copy()
    prices_dt.index = dt_idx

    cutoff = pd.Timestamp(_subtract_months(as_of, lookback_months))
    as_of_ts = pd.Timestamp(as_of)
    window = prices_dt[(prices_dt.index >= cutoff) & (prices_dt.index <= as_of_ts)]

    if len(window) < 20:
        return None
    daily_ret = window.pct_change().dropna()
    std = float(daily_ret.std())
    if std == 0:
        return None
    return float(daily_ret.mean() / std * np.sqrt(252))


def _rank_normalize(s: pd.Series) -> pd.Series:
    """Rank-normalize to [0, 1] (higher = better rank). NaNs rank at the bottom."""
    return s.rank(pct=True, na_option="bottom")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score_universe(
    store: PriceStore,
    symbols: list[str],
    as_of_date: date,
    config: ScoringConfig,
) -> list[MomentumScore]:
    """
    Score and rank the given symbols as of as_of_date.

    Returns a list sorted by rank (rank 1 = strongest composite score).
    Symbols with insufficient history or below the liquidity filter are excluded.
    Corporate-action suspects are flagged but not excluded (caller can filter them).
    """
    # Calendar days of history needed (conservative: 2 months buffer)
    total_months = config.lookback_months + config.skip_recent_months + 2
    lookback_days = total_months * 32
    start_date = as_of_date - timedelta(days=lookback_days)

    close_df = store.get_close_prices(symbols, start_date, as_of_date)
    avg_tv = store.get_avg_traded_value_cr(symbols, as_of_date, lookback_days=60)

    rows: list[dict] = []

    for sym in symbols:
        if sym not in close_df.columns:
            continue
        prices = close_df[sym].dropna()
        if len(prices) < 30:
            continue

        ca = _detect_corporate_action(prices, config.corporate_action_threshold)

        mom = _momentum_return(prices, config, as_of_date)
        if mom is None:
            continue

        tv = avg_tv.get(sym, 0.0)

        pct_pos: float | None = None
        if config.use_pct_positive_days:
            pct_pos = _pct_positive_days(
                prices, config.pct_positive_days_window_months, as_of_date
            )

        sharpe: float | None = None
        if config.use_sharpe_ratio:
            sharpe = _sharpe_ratio(prices, config.lookback_months, as_of_date)

        dist_high: float | None = None
        if config.use_dist_from_52w_high:
            dist_high = _dist_from_52w_high(prices, as_of_date)

        quality = (
            "corporate_action" if ca
            else ("sparse" if len(prices) < 100 else "ok")
        )

        rows.append({
            "symbol": sym,
            "momentum_return": mom,
            "avg_traded_value_cr": tv,
            "pct_positive_days": pct_pos,
            "dist_from_52w_high": dist_high,
            "sharpe_ratio": sharpe,
            "has_corporate_action": ca,
            "data_quality": quality,
        })

    if not rows:
        return []

    df = pd.DataFrame(rows)

    # Liquidity filter
    df = df[df["avg_traded_value_cr"] >= config.min_daily_traded_value_cr].copy()
    if df.empty:
        return []

    # --- Build composite score ---
    df["_mom_score"] = _rank_normalize(df["momentum_return"])
    composite = df["_mom_score"].copy()
    total_weight = 1.0

    def _add_secondary(col: str, weight: float) -> None:
        nonlocal composite, total_weight
        valid = df[col].notna() if col in df.columns else pd.Series(False, index=df.index)
        if not valid.any():
            return
        score_col = f"_{col}_score"
        df[score_col] = _rank_normalize(df[col]).fillna(0.5)
        composite.update(composite + df[score_col] * weight)
        nonlocal total_weight
        total_weight += weight

    # Rebind composite as a mutable local so _add_secondary can update it
    composite = composite.copy()
    if config.use_pct_positive_days:
        _add_secondary("pct_positive_days", config.pct_positive_days_weight)
    if config.use_dist_from_52w_high:
        _add_secondary("dist_from_52w_high", config.dist_from_52w_high_weight)
    if config.use_sharpe_ratio:
        _add_secondary("sharpe_ratio", config.sharpe_ratio_weight)

    df["composite_score"] = composite / total_weight
    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    result: list[MomentumScore] = []
    for _, row in df.iterrows():
        def _opt(k: str) -> float | None:
            v = row.get(k)
            if v is None:
                return None
            try:
                f = float(v)
                return None if np.isnan(f) else f
            except (TypeError, ValueError):
                return None

        result.append(MomentumScore(
            symbol=str(row["symbol"]),
            rank=int(row["rank"]),
            momentum_return=float(row["momentum_return"]),
            avg_traded_value_cr=float(row["avg_traded_value_cr"]),
            pct_positive_days=_opt("pct_positive_days"),
            dist_from_52w_high=_opt("dist_from_52w_high"),
            sharpe_ratio=_opt("sharpe_ratio"),
            composite_score=float(row["composite_score"]),
            has_corporate_action=bool(row["has_corporate_action"]),
            data_quality=str(row["data_quality"]),
        ))

    return result
