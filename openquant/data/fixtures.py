"""
OpenQuant — offline data fixtures and a self-check.

A network-free sample of exactly what the data layer returns, so the engine,
its tests, and the UI can run with no yfinance or EDGAR call. ``verify_financials``
checks that every field the UI consumes is present and non-empty.

Run the self-check from the command line:

    python -m openquant.data.fixtures
"""

from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from .models import FinancialStatements, PriceData

# Five fiscal-year-ends, the shape EDGAR returns.
_YEARS = pd.to_datetime(
    ["2020-12-31", "2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31"]
)


def _s(values: list[float]) -> pd.Series:
    return pd.Series(values, index=_YEARS)


# Every FinancialStatements series the valuation / UI layer reads. Keeping this
# list explicit is what lets verify_financials() prove nothing is missing.
REQUIRED_STATEMENT_FIELDS = [
    "revenue",
    "ebit",
    "depreciation_amortisation",
    "interest_expense",
    "tax_expense",
    "net_income",
    "ebitda",
    "total_assets",
    "total_debt",
    "beginning_debt",
    "cash_and_equivalents",
    "shares_outstanding",
    "net_working_capital",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
    "stock_based_compensation",
    "effective_tax_rate",
    "fcf_margin",
]


def sample_financials(ticker: str = "DEMO") -> FinancialStatements:
    """A complete, internally consistent set of statements, no network needed."""
    revenue = _s([100, 120, 140, 165, 190])
    ebit = _s([20, 25, 30, 36, 43])
    dna = _s([8, 9, 10, 11, 12])
    ocf = _s([25, 30, 35, 42, 50])
    capex = _s([7, 8, 9, 10, 11])
    fcf = ocf - capex
    return FinancialStatements(
        ticker=ticker,
        company_name="Demo Corp",
        cik="0000000000",
        source="fixtures",
        fetched_at=datetime(2025, 1, 1),
        revenue=revenue,
        ebit=ebit,
        depreciation_amortisation=dna,
        interest_expense=_s([2, 2, 3, 3, 4]),
        tax_expense=_s([4, 5, 6, 7, 8]),
        net_income=_s([14, 18, 21, 26, 31]),
        ebitda=ebit + dna,
        total_assets=_s([300, 330, 360, 400, 450]),
        total_debt=_s([50, 55, 60, 62, 65]),
        beginning_debt=_s([45, 50, 55, 60, 62]),
        cash_and_equivalents=_s([30, 35, 40, 48, 55]),
        shares_outstanding=_s([10.0, 10.0, 10.0, 9.8, 9.6]),
        net_working_capital=_s([20, 22, 25, 28, 30]),
        operating_cash_flow=ocf,
        capital_expenditure=capex,
        free_cash_flow=fcf,
        stock_based_compensation=_s([3, 3, 4, 4, 5]),
        effective_tax_rate=_s([0.22, 0.22, 0.22, 0.21, 0.21]),
        fcf_margin=fcf / revenue,
        data_warnings=[],
    )


def sample_prices(ticker: str = "DEMO") -> PriceData:
    """Two daily price series (stock + market index), no network needed."""
    idx = pd.bdate_range("2023-01-01", periods=504)
    stock = pd.Series(
        [100 + 12 * math.sin(i / 15) + i * 0.05 for i in range(len(idx))],
        index=idx,
        name=ticker,
    )
    market = pd.Series(
        [400 + 30 * math.sin(i / 15 + 0.3) + i * 0.04 for i in range(len(idx))],
        index=idx,
        name="^GSPC",
    )
    return PriceData(
        ticker=ticker,
        prices=stock,
        market_prices=market,
        source="fixtures",
        fetched_at=datetime(2025, 1, 1),
    )


def verify_financials(fs: FinancialStatements | None = None) -> dict[str, bool]:
    """Map each required field to whether it is present and non-empty."""
    fs = fs or sample_financials()
    report: dict[str, bool] = {}
    for name in REQUIRED_STATEMENT_FIELDS:
        value = getattr(fs, name, None)
        report[name] = isinstance(value, pd.Series) and len(value.dropna()) > 0
    return report


def main() -> int:
    fs = sample_financials()
    pr = sample_prices()
    report = verify_financials(fs)
    missing = [name for name, ok in report.items() if not ok]

    print("OpenQuant data module — offline self-check")
    print(f"  fundamentals: {sum(report.values())}/{len(report)} required fields present")
    for name, ok in report.items():
        print(f"    {'ok     ' if ok else 'MISSING'}  {name}")
    prices_ok = len(pr.prices.dropna()) > 0 and len(pr.market_prices.dropna()) > 0
    print(f"  prices: {len(pr.prices)} days, market index {len(pr.market_prices)} days "
          f"-> {'ok' if prices_ok else 'MISSING'}")

    ok = not missing and prices_ok
    print("RESULT:", "ALL DATA PRESENT" if ok else f"INCOMPLETE: {missing or 'prices'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
