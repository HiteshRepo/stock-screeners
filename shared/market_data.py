"""
shared.market_data — yfinance-backed market data fetching with local JSON cache.

Public API:
    fetch_quotes(tickers, cache_path, expiry_hours) -> dict[str, QuoteResult]

Cache strategy:
    Results are stored in a single JSON file keyed by ticker symbol.
    Entries younger than `cache_expiry_hours` are served from cache;
    older or missing entries are re-fetched and the file is updated.
    A corrupt or missing cache is treated as empty (no crash).

Graceful degradation:
    If a ticker fails to fetch (network error, invalid symbol, etc.)
    the result is a QuoteResult with `error` set and all price fields
    as None. Callers check `result.is_valid` before using numeric fields.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import yfinance as yf


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class QuoteResult:
    ticker: str
    price: float | None           # current market price (₹)
    yield_pct: float | None       # trailing annual dividend yield (%)
    fifty_two_week_high: float | None
    fifty_two_week_low: float | None
    company_name: str | None
    payout_ratio_pct: float | None
    error: str | None             # None when fetch succeeded
    fetched_at: str               # ISO-8601 datetime string

    @property
    def is_valid(self) -> bool:
        """True when price data is available and no error occurred."""
        return self.error is None and self.price is not None

    @property
    def pct_below_52w_high(self) -> float | None:
        """How far current price is below the 52-week high, as a positive %."""
        if self.price and self.fifty_two_week_high and self.fifty_two_week_high > 0:
            return round((self.fifty_two_week_high - self.price) / self.fifty_two_week_high * 100, 2)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_quotes(
    tickers: list[str],
    cache_path: Path,
    cache_expiry_hours: int,
    force_refresh: bool = False,
    on_fetch: Callable[[str], None] | None = None,
) -> dict[str, QuoteResult]:
    """
    Return a QuoteResult for each ticker in *tickers*.

    Fresh cache entries are returned immediately; stale or absent entries
    are fetched from Yahoo Finance, stored in the cache, and returned.

    Args:
        tickers:            yfinance ticker strings, e.g. ["HDFCBANK.NS", "ITC.NS"]
        cache_path:         Path to the JSON cache file (created if absent)
        cache_expiry_hours: How long a cached entry stays valid
        force_refresh:      Skip the cache entirely and re-fetch everything
        on_fetch:           Optional callback(ticker) called before each live fetch —
                            use for CLI progress messages
    """
    if not tickers:
        return {}

    raw_cache = _load_cache(cache_path)
    results: dict[str, QuoteResult] = {}
    cache_updated = False

    for ticker in tickers:
        cached = raw_cache.get(ticker)
        if (
            not force_refresh
            and cached is not None
            and not _is_stale(cached, cache_expiry_hours)
        ):
            results[ticker] = QuoteResult(**cached)
            continue

        if on_fetch:
            on_fetch(ticker)

        result = _fetch_single(ticker)
        results[ticker] = result
        raw_cache[ticker] = asdict(result)
        cache_updated = True

    if cache_updated:
        _save_cache(cache_path, raw_cache)

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_single(ns_ticker: str) -> QuoteResult:
    """Fetch price + fundamentals for one ticker from Yahoo Finance."""
    now = datetime.now().isoformat()
    _empty = dict(
        ticker=ns_ticker,
        price=None,
        yield_pct=None,
        fifty_two_week_high=None,
        fifty_two_week_low=None,
        company_name=None,
        payout_ratio_pct=None,
        fetched_at=now,
    )
    try:
        info = yf.Ticker(ns_ticker).info

        price = _to_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        if price is None:
            return QuoteResult(
                **_empty,
                error="No price data returned by Yahoo Finance — "
                      "ticker may be invalid or delisted",
            )

        raw_yield = info.get("trailingAnnualDividendYield") or 0.0
        raw_payout = info.get("payoutRatio") or 0.0

        return QuoteResult(
            ticker=ns_ticker,
            price=price,
            yield_pct=round(float(raw_yield) * 100, 4),
            fifty_two_week_high=_to_float(info.get("fiftyTwoWeekHigh")),
            fifty_two_week_low=_to_float(info.get("fiftyTwoWeekLow")),
            company_name=info.get("longName") or info.get("shortName"),
            payout_ratio_pct=round(float(raw_payout) * 100, 2),
            error=None,
            fetched_at=now,
        )
    except Exception as exc:  # network error, yfinance internal error, etc.
        return QuoteResult(**_empty, error=str(exc))


def _to_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _load_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}  # corrupt cache → treat as empty, will be overwritten


def _save_cache(cache_path: Path, data: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _is_stale(entry: dict, expiry_hours: int) -> bool:
    fetched_at_str = entry.get("fetched_at", "")
    if not fetched_at_str:
        return True
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str)
        return (datetime.now() - fetched_at).total_seconds() > expiry_hours * 3600
    except ValueError:
        return True


# ---------------------------------------------------------------------------
# Manual test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import sys

    raw_tickers = sys.argv[1:] or ["HDFCBANK", "ITC", "COALINDIA"]
    ns_tickers = [t if ("." in t) else f"{t}.NS" for t in raw_tickers]

    print(f"Fetching {len(ns_tickers)} ticker(s)…\n")
    results = fetch_quotes(
        ns_tickers,
        cache_path=Path(".cache/market_data.json"),
        cache_expiry_hours=1,
        force_refresh=True,
        on_fetch=lambda t: print(f"  → {t}", flush=True),
    )
    print()
    for t, r in results.items():
        if r.is_valid:
            below = f"  ({r.pct_below_52w_high:.1f}% below 52w high)" if r.pct_below_52w_high else ""
            print(
                f"  {t:25s}  ₹{r.price:>10.2f}  "
                f"yield={r.yield_pct:.2f}%  "
                f"52w_high={r.fifty_two_week_high}{below}"
            )
        else:
            print(f"  {t:25s}  ERROR: {r.error}")
