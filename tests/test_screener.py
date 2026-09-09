"""Tests for shared.screener — screener.in scraper."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shared.screener import ScreenerQuote, fetch_quote, fetch_sector


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _html(
    company: str = "Infosys Ltd",
    price: str = "1,500",
    high_low: str = "1,800 / 1,200",
    yield_pct: str = "3.50",
    payout: str = "45%",
    sector_href: str = "/market/IT/",
    sector_label: str = "Information Technology",
) -> str:
    return f"""
    <html><body>
      <h1>{company}</h1>
      <ul id="top-ratios">
        <li><span class="name">Market Cap</span><span class="number">7,00,000</span></li>
        <li><span class="name">Current Price</span><span class="number">{price}</span></li>
        <li>
          <span class="name">High / Low</span>
          <span class="value">₹ {high_low}</span>
        </li>
        <li><span class="name">Dividend Yield</span><span class="number">{yield_pct}</span></li>
      </ul>
      <table>
        <tr><td>Revenue</td><td>100</td><td>200</td></tr>
        <tr><td>Dividend Payout %</td><td>{payout}</td><td>40%</td></tr>
      </table>
      <section id="peers">
        <a href="{sector_href}">{sector_label}</a>
        <a href="/market/IT/IT01/">IT - Software</a>
      </section>
    </body></html>
    """


def _mock_response(html: str, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = html
    r.raise_for_status = MagicMock()
    if status >= 400:
        import requests
        r.raise_for_status.side_effect = requests.HTTPError(response=r)
    return r


# ---------------------------------------------------------------------------
# fetch_quote
# ---------------------------------------------------------------------------

class TestFetchQuote:
    def test_returns_screener_quote_on_success(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(_html())
            result = fetch_quote("INFY")
        assert isinstance(result, ScreenerQuote)

    def test_parses_company_name(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(_html(company="Infosys Ltd"))
            result = fetch_quote("INFY")
        assert result.company_name == "Infosys Ltd"

    def test_parses_price(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(_html(price="1,500"))
            result = fetch_quote("INFY")
        assert result.price == pytest.approx(1500.0)

    def test_parses_yield(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(_html(yield_pct="3.50"))
            result = fetch_quote("INFY")
        assert result.yield_pct == pytest.approx(3.5)

    def test_parses_52w_high(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(_html(high_low="1,800 / 1,200"))
            result = fetch_quote("INFY")
        assert result.fifty_two_week_high == pytest.approx(1800.0)

    def test_parses_52w_low(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(_html(high_low="1,800 / 1,200"))
            result = fetch_quote("INFY")
        assert result.fifty_two_week_low == pytest.approx(1200.0)

    def test_parses_payout_ratio(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(_html(payout="45%"))
            result = fetch_quote("INFY")
        assert result.payout_ratio_pct == pytest.approx(45.0)

    def test_parses_sector(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(
                _html(sector_href="/market/IT/", sector_label="Information Technology")
            )
            result = fetch_quote("INFY")
        assert result.sector == "Information Technology"

    def test_strips_exchange_suffix_from_url(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(_html())
            fetch_quote("INFY.NS")
            url = mock_get.call_args[0][0]
        assert "INFY.NS" not in url
        assert "INFY" in url

    def test_returns_none_on_network_error(self):
        import requests as req
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.side_effect = req.RequestException("timeout")
            result = fetch_quote("INFY")
        assert result is None

    def test_returns_none_on_http_error(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response("", status=404)
            result = fetch_quote("BADTICKER")
        assert result is None

    def test_fields_are_none_when_elements_missing(self):
        html = "<html><body><h1>Some Co</h1></body></html>"
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(html)
            result = fetch_quote("INFY")
        assert result is not None
        assert result.price is None
        assert result.yield_pct is None
        assert result.sector is None
        assert result.payout_ratio_pct is None

    def test_ticker_normalised_to_uppercase(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(_html())
            fetch_quote("infy")
            url = mock_get.call_args[0][0]
        assert "INFY" in url


# ---------------------------------------------------------------------------
# fetch_sector (convenience wrapper)
# ---------------------------------------------------------------------------

class TestFetchSector:
    def test_returns_sector_string(self):
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(
                _html(sector_label="Information Technology")
            )
            result = fetch_sector("INFY")
        assert result == "Information Technology"

    def test_returns_none_on_network_error(self):
        import requests as req
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.side_effect = req.RequestException("timeout")
            result = fetch_sector("INFY")
        assert result is None

    def test_returns_none_when_no_peers_section(self):
        html = "<html><body><p>No peers here</p></body></html>"
        with patch("shared.screener.requests.get") as mock_get:
            mock_get.return_value = _mock_response(html)
            result = fetch_sector("INFY")
        assert result is None
