"""
OpenQuant — SEC EDGAR provider.

Fetches XBRL financial statements directly from the official SEC EDGAR API
(free, unlimited, US companies only). One module, one source. Pulled out of
``openquant/data/data.py``; re-exported by ``openquant.data`` for backward compatibility.
"""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import requests

from openquant.config import EDGAR_SUBMISSIONS_URL, EDGAR_FACTS_URL

from ..errors import DataFetchError


class EDGARClient:
    """
    SEC EDGAR API client.
    Fetches XBRL financial data directly from the official source.
    Unlimited, free, no API key required.
    US companies only.
    """

    BASE_URL = "https://data.sec.gov"
    TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    HEADERS = {
        "User-Agent": "OpenQuant educational-tool contact@openquant.dev",
        "Accept-Encoding": "gzip, deflate",
    }
    # Rate limit: EDGAR requests max 10/second
    REQUEST_DELAY = 0.12

    # XBRL tag mappings — companies use different tags for same concept
    TAG_MAPPINGS = {
        "revenue": [
            "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet", "SalesRevenueGoodsNet", "RevenueFromContractWithCustomer",
        ],
        "ebit": [
            "OperatingIncomeLoss",
        ],
        "depreciation_amortisation": [
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "Depreciation",
        ],
        "interest_expense": [
            "InterestExpense", "InterestAndDebtExpense",
        ],
        "net_income": [
            "NetIncomeLoss", "NetIncome",
        ],
        "capital_expenditure": [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "CapitalExpendituresIncurringObligation",
        ],
        "operating_cash_flow": [
            "NetCashProvidedByUsedInOperatingActivities",
        ],
        "total_debt": [
            "LongTermDebt",                              # Total LT debt incl. current maturities
            "LongTermDebtAndCapitalLeaseObligations",
            "DebtAndCapitalLeaseObligations",
            "LongTermDebtNoncurrent",                    # Fallback: non-current portion only
            "LongTermDebtCurrent",                       # Fallback: current maturities only
            "ShortTermBorrowings",
        ],
        "cash_and_equivalents": [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsAndShortTermInvestments",
        ],
        "shares_outstanding": [
            "CommonStockSharesOutstanding",
            "WeightedAverageNumberOfDilutedSharesOutstanding",
        ],
        "tax_expense": [
            "IncomeTaxExpenseBenefit",
        ],
        "stock_based_compensation": [
            "ShareBasedCompensation",
            "AllocatedShareBasedCompensationExpense",
        ],
        "current_assets": [
            "AssetsCurrent",
        ],
        "current_liabilities": [
            "LiabilitiesCurrent",
        ],
        "total_assets": [
            "Assets",
        ],
    }

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)

    def _get(self, url: str) -> dict:
        """Make a GET request with rate limiting and error handling."""
        time.sleep(self.REQUEST_DELAY)
        try:
            response = self._session.get(url, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise DataFetchError(f"EDGAR HTTP error: {e}")
        except requests.exceptions.ConnectionError:
            raise DataFetchError("Cannot connect to SEC EDGAR. Check your internet connection.")
        except requests.exceptions.Timeout:
            raise DataFetchError("SEC EDGAR request timed out.")

    def get_cik(self, ticker: str) -> Optional[str]:
        """
        Look up CIK (Central Index Key) for a ticker symbol.

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL").

        Returns:
            CIK as zero-padded 10-digit string, or None if not found.
        """
        try:
            data = self._get(self.TICKERS_URL)
            ticker_upper = ticker.upper()
            for _, company in data.items():
                if company.get("ticker", "").upper() == ticker_upper:
                    return str(company["cik_str"]).zfill(10)
            return None
        except DataFetchError:
            return None

    def get_company_info(self, cik: str) -> dict:
        """
        Get company metadata from EDGAR submissions.

        Args:
            cik: Zero-padded 10-digit CIK.

        Returns:
            Dict with name, sic, sector, exchanges.
        """
        url = EDGAR_SUBMISSIONS_URL.format(cik=int(cik))
        data = self._get(url)
        return {
            "name": data.get("name", ""),
            "sic": data.get("sic", ""),
            "sic_description": data.get("sicDescription", ""),
            "exchanges": data.get("exchanges", []),
            "tickers": data.get("tickers", []),
        }

    def get_facts(self, cik: str) -> dict:
        """
        Get all XBRL facts for a company.

        Args:
            cik: Zero-padded 10-digit CIK.

        Returns:
            Raw XBRL facts dict.
        """
        url = EDGAR_FACTS_URL.format(cik=int(cik))
        return self._get(url)

    def extract_annual_series(
        self,
        facts: dict,
        concept_tags: list[str],
        unit: str = "USD",
    ) -> Optional[pd.Series]:
        """
        Extract annual values for a concept from XBRL facts.

        Tries each tag in concept_tags in order — companies use
        different tag names for the same concept.

        Args:
            facts: Raw facts dict from get_facts().
            concept_tags: List of XBRL tags to try.
            unit: Unit of measurement. Default "USD".
                  Use "shares" for share count data.

        Returns:
            pd.Series indexed by fiscal year end date, or None if not found.
        """
        us_gaap = facts.get("facts", {}).get("us-gaap", {})

        candidates = []

        for tag in concept_tags:
            if tag not in us_gaap:
                continue

            tag_units = us_gaap[tag].get("units", {})

            # Try specified unit first, then any available unit — do not mutate `unit`
            unit_to_use = unit if unit in tag_units else next(iter(tag_units), None)
            if not unit_to_use:
                continue

            records = tag_units[unit_to_use]

            # Filter for annual 10-K filings only.
            # EDGAR sometimes tags sub-annual periods (quarters, half-years)
            # with fp="FY" inside 10-K filings (e.g. ASC 606 transition
            # comparatives). Guard with a duration check: require the period
            # to span at least 340 days so that 90-day and 180-day sub-periods
            # are always rejected regardless of the fp label.
            annual = [
                r for r in records
                if r.get("form") in ("10-K", "10-K/A")
                and r.get("fp") == "FY"
                and "end" in r
                and (
                    "start" not in r
                    or (
                        pd.Timestamp(r["end"]) - pd.Timestamp(r["start"])
                    ).days >= 340
                )
            ]

            if not annual:
                continue

            # Deduplicate by end date — keep most recently filed version
            by_date: dict = {}
            for r in annual:
                end = r["end"]
                if end not in by_date or r.get("filed", "") > by_date[end].get("filed", ""):
                    by_date[end] = r

            if not by_date:
                continue

            candidates.append(
                pd.Series(
                    {pd.Timestamp(end): r["val"] for end, r in by_date.items()}
                ).sort_index()
            )

        if not candidates:
            return None

        # Return the candidate whose most recent data point is latest.
        # Companies switch XBRL tags over time (e.g. AAPL moved from
        # "Revenues" to "RevenueFromContractWithCustomerExcludingAssessedTax"
        # in 2019). Always preferring the newest series avoids silently
        # returning stale data from a retired tag.
        return max(candidates, key=lambda s: s.index.max())
