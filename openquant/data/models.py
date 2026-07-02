"""
OpenQuant — data layer models.

The standardised structures the data layer returns: financial statements,
price series, and ticker validation. Pure dataclasses with no I/O, so they
import with zero network or provider dependencies — which is what lets the
rest of the engine (and its tests) run fully offline.

Pulled out of ``openquant/data/data.py`` and re-exported by ``openquant.data`` for
backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd


@dataclass
class FinancialStatements:
    """
    Standardised financial statements for one company.
    All values in USD. Annual frequency.
    """
    ticker: str
    company_name: str
    cik: str
    source: str                          # "edgar" or "fmp"
    fetched_at: datetime

    # Income statement
    revenue: pd.Series                   # Annual revenue
    ebit: pd.Series                      # Earnings before interest and tax
    depreciation_amortisation: pd.Series # D&A
    interest_expense: pd.Series          # Interest expense
    tax_expense: pd.Series               # Income tax expense
    net_income: pd.Series                # Net income
    ebitda: pd.Series                    # EBITDA

    # Balance sheet
    total_assets: pd.Series
    total_debt: pd.Series                # Short + long term debt
    beginning_debt: pd.Series            # Prior year debt (for avg debt cost)
    cash_and_equivalents: pd.Series
    shares_outstanding: pd.Series        # Diluted
    net_working_capital: pd.Series       # Current assets - current liabilities

    # Cash flow statement
    operating_cash_flow: pd.Series
    capital_expenditure: pd.Series       # Always positive (outflow)
    free_cash_flow: pd.Series            # Computed: OCF - CapEx
    stock_based_compensation: pd.Series  # SBC — shown separately

    # Derived
    effective_tax_rate: pd.Series        # tax_expense / pretax_income
    fcf_margin: pd.Series                # FCF / revenue

    # Warnings
    data_warnings: list[str] = field(default_factory=list)


@dataclass
class PriceData:
    """Daily adjusted closing prices for beta computation."""
    ticker: str
    prices: pd.Series                    # Adjusted close, date-indexed
    market_prices: pd.Series             # Market index adjusted close
    source: str
    fetched_at: datetime


@dataclass
class TickerValidation:
    """Result of pre-flight ticker validation."""
    ticker: str
    is_valid: bool
    is_us_company: bool
    company_name: str
    sector: str
    cik: Optional[str]
    trading_days_available: int
    has_financial_statements: bool
    badge: str                           # "green", "amber", "red"
    message: str
