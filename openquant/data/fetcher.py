"""
OpenQuant — data layer functional interface.

A thin, clean entry point over ``DataFetcher``: ask for a ticker, get back the
fundamentals, the prices, the current price, or a validation. This is the
contract a UI (or a future single cloud endpoint) calls, so callers depend on
four small functions instead of a class.
"""

from __future__ import annotations

from typing import Optional

from .data import DataFetcher
from .models import FinancialStatements, PriceData, TickerValidation

_fetcher: Optional[DataFetcher] = None


def _get() -> DataFetcher:
    """Lazily build a shared DataFetcher (keeps the EDGAR session warm)."""
    global _fetcher
    if _fetcher is None:
        _fetcher = DataFetcher()
    return _fetcher


def validate_ticker(ticker: str) -> TickerValidation:
    """Pre-flight check: is this a supported US ticker, with how much data."""
    return _get().validate_ticker(ticker)


def get_fundamentals(ticker: str) -> FinancialStatements:
    """Standardised financial statements for a ticker (source: SEC EDGAR)."""
    return _get().get_financial_statements(ticker)


def get_prices(ticker: str) -> PriceData:
    """Daily adjusted prices plus the market index (source: yfinance)."""
    return _get().get_prices(ticker)


def get_current_price(ticker: str) -> Optional[float]:
    """Latest available price, or None if unavailable."""
    return _get().get_current_price(ticker)
