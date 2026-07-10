"""
Live EDGAR connectivity tests.

These tests make real network calls — they are intentionally not mocked.
The goal is to catch URL changes like the data.sec.gov → www.sec.gov
migration that broke all CIK lookups in v1.0.0.

Run with:
    pytest -m live
Skip with:
    pytest -m "not live"
"""

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from openquant.data import EDGARClient

KNOWN_CIKS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "XOM":  "0000034088",
}


@pytest.mark.live
class TestEDGARLiveConnectivity:

    def test_tickers_url_returns_200(self):
        """www.sec.gov/files/company_tickers.json must be reachable."""
        r = requests.get(
            EDGARClient.TICKERS_URL,
            headers=EDGARClient.HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, (
            f"EDGAR tickers URL returned HTTP {r.status_code}. "
            f"The file may have moved from {EDGARClient.TICKERS_URL!r}. "
            "Update EDGARClient.TICKERS_URL."
        )

    def test_tickers_response_is_valid_json_dict(self):
        """Response must be a JSON object (not a list or error XML)."""
        r = requests.get(
            EDGARClient.TICKERS_URL,
            headers=EDGARClient.HEADERS,
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict), (
            f"Expected dict, got {type(data).__name__}. "
            "EDGAR may have changed the response format."
        )
        assert len(data) > 1000, (
            f"Only {len(data)} entries — response may be truncated or wrong endpoint."
        )

    def test_tickers_entries_have_required_fields(self):
        """Every entry must have 'ticker' and 'cik_str' keys."""
        r = requests.get(
            EDGARClient.TICKERS_URL,
            headers=EDGARClient.HEADERS,
            timeout=15,
        )
        data = r.json()
        sample = next(iter(data.values()))
        assert "ticker" in sample, (
            f"'ticker' key missing from entry: {sample}. "
            "EDGAR may have renamed the field."
        )
        assert "cik_str" in sample, (
            f"'cik_str' key missing from entry: {sample}. "
            "EDGAR may have renamed the field."
        )

    @pytest.mark.parametrize("ticker,expected_cik", list(KNOWN_CIKS.items()))
    def test_known_cik_resolves_correctly(self, ticker, expected_cik):
        """AAPL, MSFT, and XOM must resolve to their known stable CIKs."""
        client = EDGARClient()
        cik = client.get_cik(ticker)
        assert cik == expected_cik, (
            f"{ticker}: expected CIK {expected_cik!r}, got {cik!r}. "
            "The company may have been relisted or EDGAR data changed."
        )
