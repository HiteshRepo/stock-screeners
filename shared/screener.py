"""
shared.screener — scrape fundamentals from screener.in as a fallback
when yfinance doesn't return reliable data for Indian stocks.

Public API:
    fetch_quote(ticker)  -> ScreenerQuote | None
    fetch_sector(ticker) -> str | None          (convenience wrapper)

A single HTTP GET to screener.in/company/{TICKER}/ yields:
  - company name       (h1)
  - current price      (#top-ratios "Current Price")
  - dividend yield %   (#top-ratios "Dividend Yield")
  - 52-week high/low   (#top-ratios "High / Low")
  - payout ratio %     (financial table row "Dividend Payout %", most recent)
  - sector             (first /market/ link in #peers)

All fields are None if the element is missing or parsing fails.
Returns None for the whole object on network / HTTP errors.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

_BASE_URL = "https://www.screener.in/company"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}
_TIMEOUT = 10


@dataclass
class ScreenerQuote:
    ticker: str
    company_name: str | None
    price: float | None
    yield_pct: float | None
    fifty_two_week_high: float | None
    fifty_two_week_low: float | None
    payout_ratio_pct: float | None
    sector: str | None


def fetch_quote(ticker: str) -> ScreenerQuote | None:
    """Scrape all available fundamentals for *ticker* from screener.in.

    Returns None on network error or HTTP error so callers can fall through
    to their own defaults. Individual fields are None when not found on page.
    """
    plain = _plain_ticker(ticker)
    url = f"{_BASE_URL}/{plain}/"
    try:
        response = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    ratios = _parse_top_ratios(soup)

    return ScreenerQuote(
        ticker=plain,
        company_name=_parse_company_name(soup),
        price=_to_float(ratios.get("Current Price")),
        yield_pct=_to_float(ratios.get("Dividend Yield")),
        fifty_two_week_high=_parse_52w_high(ratios.get("High / Low")),
        fifty_two_week_low=_parse_52w_low(ratios.get("High / Low")),
        payout_ratio_pct=_parse_payout_ratio(soup),
        sector=_parse_sector(soup),
    )


def fetch_sector(ticker: str) -> str | None:
    """Convenience wrapper — return only the sector string for *ticker*.

    Calls fetch_quote internally (one HTTP request) and returns the sector
    field. Returns None on failure.
    """
    result = fetch_quote(ticker)
    return result.sector if result else None


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

def _plain_ticker(ticker: str) -> str:
    return ticker.upper().replace(".NS", "").replace(".BO", "")


def _parse_company_name(soup: BeautifulSoup) -> str | None:
    h1 = soup.select_one("h1")
    name = h1.get_text(strip=True) if h1 else None
    return name or None


def _parse_top_ratios(soup: BeautifulSoup) -> dict[str, str]:
    """Return {label: raw_value_text} for every item in #top-ratios."""
    ratios: dict[str, str] = {}
    for li in soup.select("#top-ratios li"):
        name_el = li.select_one(".name")
        # Prefer the .number span; fall back to full .value text for compound fields
        number_el = li.select_one(".number")
        value_el = li.select_one(".value")
        if not name_el:
            continue
        label = name_el.get_text(strip=True)
        if number_el:
            ratios[label] = number_el.get_text(strip=True)
        elif value_el:
            ratios[label] = value_el.get_text(strip=True)
    return ratios


def _parse_52w_high(raw: str | None) -> float | None:
    """Parse the high from 'High / Low' ratio value, e.g. '₹1,020 / 691'."""
    if not raw:
        return None
    # Take everything before the slash
    parts = re.split(r"[/\\]", raw)
    return _to_float(parts[0]) if parts else None


def _parse_52w_low(raw: str | None) -> float | None:
    """Parse the low from 'High / Low' ratio value."""
    if not raw:
        return None
    parts = re.split(r"[/\\]", raw)
    return _to_float(parts[1]) if len(parts) > 1 else None


def _parse_payout_ratio(soup: BeautifulSoup) -> float | None:
    """Find the 'Dividend Payout %' row in any financial table and return
    the most recent (leftmost data) value."""
    for table in soup.select("table"):
        for row in table.select("tr"):
            cells = row.select("td, th")
            if not cells:
                continue
            if "payout" in cells[0].get_text(strip=True).lower():
                # cells[1] is the most recent year/quarter
                for cell in cells[1:]:
                    val = _to_float(cell.get_text(strip=True))
                    if val is not None:
                        return val
    return None


def _parse_sector(soup: BeautifulSoup) -> str | None:
    """Return the top-level sector from the first /market/ link in #peers."""
    peers = soup.select_one("#peers")
    if peers is None:
        return None
    link = peers.select_one('a[href^="/market/"]')
    if link is None:
        return None
    sector = link.get_text(strip=True)
    return sector or None


def _to_float(value: str | None) -> float | None:
    """Strip currency symbols, commas, and % signs, then parse as float."""
    if not value:
        return None
    cleaned = re.sub(r"[₹,%\s]", "", value)
    try:
        return float(cleaned)
    except ValueError:
        return None
