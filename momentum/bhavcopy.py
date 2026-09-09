"""
NSE bhavcopy downloader.

Downloads daily OHLCV data from the NSE equity archive and stores it in the
local SQLite PriceStore.  Each bhavcopy is a zipped CSV covering all EQ-series
listed securities for one trading day.

URL pattern:
  https://archives.nseindia.com/content/historical/EQUITIES/{YYYY}/{MMM}/cm{DD}{MMM}{YYYY}bhav.csv.zip

NSE returns 404 for market holidays and future dates.  We treat 404 as a
holiday and mark the date as fetched with 0 rows so we don't retry it.
"""
from __future__ import annotations

import io
import time
import zipfile
from datetime import date, timedelta
from typing import Callable

import pandas as pd
import requests

from .store import DailyBar, PriceStore

_ARCHIVE_BASE = "https://archives.nseindia.com"
_BHAVCOPY_PATH = (
    "/content/historical/EQUITIES/{year}/{month}"
    "/cm{dd}{month}{year}bhav.csv.zip"
)
_NSE_HOME = "https://www.nseindia.com/"

# Module-level session — reused across calls to share NSE cookies
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Return a cached session primed with NSE cookies."""
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": _NSE_HOME,
        })
        try:
            # Warm-up: fetch NSE home to acquire session cookies
            s.get(_NSE_HOME, timeout=15)
        except Exception:
            pass
        _session = s
    return _session


def _url_for(d: date) -> str:
    month = d.strftime("%b").upper()   # JAN, FEB, …, DEC
    return _ARCHIVE_BASE + _BHAVCOPY_PATH.format(
        year=d.year,
        month=month,
        dd=d.strftime("%d"),
    )


def _parse_csv(raw: bytes, d: date) -> list[DailyBar]:
    """
    Parse raw bhavcopy CSV bytes into DailyBar objects.

    NSE CSV columns (EQ bhavcopy):
      SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE,
      TOTTRDQTY, TOTTRDVAL, TIMESTAMP, TOTALTRADES, ISIN

    TOTTRDVAL is in ₹ — divide by 1e7 to get ₹ crore.
    """
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [c.strip() for c in df.columns]
    df = df[df["SERIES"].str.strip() == "EQ"].copy()

    bars: list[DailyBar] = []
    for _, row in df.iterrows():
        try:
            bars.append(DailyBar(
                symbol=str(row["SYMBOL"]).strip(),
                date=d,
                open=float(row["OPEN"]),
                high=float(row["HIGH"]),
                low=float(row["LOW"]),
                close=float(row["CLOSE"]),
                volume=float(row.get("TOTTRDQTY", 0)),
                traded_value_cr=float(row.get("TOTTRDVAL", 0)) / 1e7,
                series="EQ",
            ))
        except (ValueError, KeyError):
            continue
    return bars


def is_trading_day(d: date) -> bool:
    """
    Heuristic: weekdays only.

    NSE holidays are detected at download time (404 response) rather than
    maintained as a local holiday list.
    """
    return d.weekday() < 5   # Mon = 0, Fri = 4


def fetch_bhavcopy(
    d: date,
    store: PriceStore,
    force: bool = False,
) -> tuple[int, str | None]:
    """
    Download and store the NSE equity bhavcopy for date d.

    Returns (rows_inserted, error_message).
    - error_message is None on success.
    - "cached"      — date already in store (force=False).
    - "weekend"     — d is Saturday or Sunday.
    - "holiday:…"   — NSE returned 404 (no trading that day).
    - Other string  — network or parse error.
    """
    if not force and store.has_date(d):
        return 0, "cached"
    if not is_trading_day(d):
        return 0, "weekend"

    url = _url_for(d)
    session = _get_session()

    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as e:
        return 0, f"request error: {e}"

    if resp.status_code == 404:
        # Treat as holiday — mark so we don't retry
        store.mark_date_fetched(d, 0)
        return 0, f"holiday:{d}"

    if resp.status_code != 200:
        return 0, f"HTTP {resp.status_code}"

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            raw = zf.read(zf.namelist()[0])
    except zipfile.BadZipFile as e:
        return 0, f"bad zip: {e}"

    bars = _parse_csv(raw, d)
    count = store.insert_daily(bars)
    store.mark_date_fetched(d, count)
    return count, None


def fetch_range(
    start_date: date,
    end_date: date,
    store: PriceStore,
    rate_limit_secs: float = 0.5,
    on_progress: Callable[[date, str], None] | None = None,
) -> dict:
    """
    Fetch all missing bhavcopy data in [start_date, end_date].

    Sleeps rate_limit_secs between successful downloads to avoid hammering NSE.
    Cached and holiday dates are not rate-limited.

    Returns {"fetched": N, "cached": N, "errors": [(date, msg), …]}.
    """
    fetched = 0
    cached = 0
    errors: list[tuple[date, str]] = []

    d = start_date
    while d <= end_date:
        if not is_trading_day(d):
            d += timedelta(days=1)
            continue

        count, err = fetch_bhavcopy(d, store)

        if err == "cached":
            cached += 1
            msg = "cached"
        elif err and err.startswith("holiday:"):
            msg = "holiday (skipped)"
        elif err == "weekend":
            d += timedelta(days=1)
            continue
        elif err:
            errors.append((d, err))
            msg = f"error: {err}"
        else:
            fetched += 1
            msg = f"ok ({count} EQ rows)"
            time.sleep(rate_limit_secs)

        if on_progress:
            on_progress(d, msg)

        d += timedelta(days=1)

    return {"fetched": fetched, "cached": cached, "errors": errors}
