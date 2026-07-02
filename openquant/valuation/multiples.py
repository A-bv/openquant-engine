"""
OpenQuant — Market multiples context.

NOT a primary valuation method. Context alongside DCF only.

Shows EV/EBITDA, P/E, FCF yield, EV/Sales so users can
sanity-check the DCF output against market-relative metrics.

Per spec: "DCF alone can look too academic. A CFA reviewer
would like seeing DCF-implied valuation compared with
market multiples."

Plain language interpretation always generated:
"DCF implies $X. Current EV/EBITDA of 24x compares to
sector median of 18x — market is pricing a premium."

Dependency rule: zero Streamlit imports. Pure Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd

from openquant.data import FinancialStatements
from openquant.valuation.dcf import DCFResult


@dataclass
class MultiplesResult:
    """Market multiples for one company."""
    ticker: str
    company_name: str
    current_price: float
    shares_outstanding: float

    # Computed multiples
    ev_ebitda: Optional[float]       # Enterprise Value / EBITDA
    pe_ratio: Optional[float]        # Price / Earnings
    fcf_yield: Optional[float]       # FCF per share / Price
    ev_sales: Optional[float]        # Enterprise Value / Revenue

    # Context
    market_cap: float
    enterprise_value: float
    ebitda_latest: Optional[float]
    earnings_per_share: Optional[float]
    fcf_per_share: Optional[float]
    revenue_latest: Optional[float]

    # DCF comparison
    dcf_implied_price: Optional[float]    # Base case IV per share
    dcf_vs_market_pct: Optional[float]   # (DCF - price) / price

    # Plain language
    interpretation: str

    # Warnings
    warnings: list[str] = field(default_factory=list)


class MultiplesAnalyser:
    """
    Computes market multiples for context alongside DCF.

    All multiples labeled as context, never as primary valuation.
    """

    def compute(
        self,
        statements: FinancialStatements,
        current_price: float,
        total_debt: float,
        cash: float,
        dcf_result: Optional[DCFResult] = None,
    ) -> MultiplesResult:
        """
        Compute multiples from financial statements.

        Args:
            statements: Financial statements.
            current_price: Current stock price.
            total_debt: Total debt (for EV).
            cash: Cash and equivalents (for EV).
            dcf_result: Optional DCF result for comparison.

        Returns:
            MultiplesResult with all available multiples.
        """
        warnings = []

        shares = statements.shares_outstanding.dropna()
        shares_latest = float(shares.iloc[-1]) if len(shares) > 0 else 0.0

        market_cap = shares_latest * current_price
        ev = market_cap + total_debt - cash

        # ── EV/EBITDA
        ebitda = statements.ebitda.dropna()
        ebitda_latest = float(ebitda.iloc[-1]) if len(ebitda) > 0 else None
        ev_ebitda = None
        if ebitda_latest is not None and ebitda_latest > 0 and ev > 0:
            ev_ebitda = ev / ebitda_latest
            if ev_ebitda > 100:
                warnings.append(f"EV/EBITDA of {ev_ebitda:.0f}x is very high.")

        # ── P/E ratio
        net_income = statements.net_income.dropna()
        net_income_latest = float(net_income.iloc[-1]) if len(net_income) > 0 else None
        pe_ratio = None
        eps = None
        if net_income_latest is not None and net_income_latest > 0 and shares_latest > 0:
            eps = net_income_latest / shares_latest
            pe_ratio = current_price / eps if eps > 0 else None

        # ── FCF yield
        fcf = statements.free_cash_flow.dropna()
        fcf_latest = float(fcf.iloc[-1]) if len(fcf) > 0 else None
        fcf_yield = None
        fcf_per_share = None
        if fcf_latest is not None and shares_latest > 0 and current_price > 0:
            fcf_per_share = fcf_latest / shares_latest
            fcf_yield = fcf_per_share / current_price

        # ── EV/Sales
        revenue = statements.revenue.dropna()
        revenue_latest = float(revenue.iloc[-1]) if len(revenue) > 0 else None
        ev_sales = None
        if revenue_latest is not None and revenue_latest > 0 and ev > 0:
            ev_sales = ev / revenue_latest

        # ── DCF comparison
        dcf_implied = None
        dcf_vs_mkt = None
        if dcf_result is not None:
            dcf_implied = dcf_result.base.intrinsic_value_per_share
            if current_price > 0:
                dcf_vs_mkt = (dcf_implied - current_price) / current_price

        # ── Plain language
        interpretation = self._interpret(
            ev_ebitda, pe_ratio, fcf_yield, ev_sales,
            dcf_implied, current_price,
        )

        return MultiplesResult(
            ticker=statements.ticker,
            company_name=statements.company_name,
            current_price=current_price,
            shares_outstanding=shares_latest,
            ev_ebitda=ev_ebitda,
            pe_ratio=pe_ratio,
            fcf_yield=fcf_yield,
            ev_sales=ev_sales,
            market_cap=market_cap,
            enterprise_value=ev,
            ebitda_latest=ebitda_latest,
            earnings_per_share=eps,
            fcf_per_share=fcf_per_share,
            revenue_latest=revenue_latest,
            dcf_implied_price=dcf_implied,
            dcf_vs_market_pct=dcf_vs_mkt,
            interpretation=interpretation,
            warnings=warnings,
        )

    def _interpret(
        self,
        ev_ebitda: Optional[float],
        pe_ratio: Optional[float],
        fcf_yield: Optional[float],
        ev_sales: Optional[float],
        dcf_implied: Optional[float],
        current_price: float,
    ) -> str:
        """Generate plain-language multiples interpretation."""
        parts = []

        if fcf_yield is not None:
            if fcf_yield > 0.05:
                parts.append(
                    f"FCF yield of {fcf_yield:.1%} is healthy — "
                    f"the stock generates meaningful cash relative to its price."
                )
            elif fcf_yield > 0.02:
                parts.append(f"FCF yield of {fcf_yield:.1%} is moderate.")
            else:
                parts.append(
                    f"FCF yield of {fcf_yield:.1%} is low — "
                    f"the stock is priced for significant future growth."
                )

        if ev_ebitda is not None:
            parts.append(f"EV/EBITDA of {ev_ebitda:.1f}x.")

        if pe_ratio is not None:
            parts.append(f"P/E ratio of {pe_ratio:.1f}x.")

        if dcf_implied is not None and current_price > 0:
            diff_pct = (dcf_implied - current_price) / current_price * 100
            if diff_pct > 10:
                parts.append(
                    f"DCF base case implies ${dcf_implied:.0f} — "
                    f"{abs(diff_pct):.0f}% above current price."
                )
            elif diff_pct < -10:
                parts.append(
                    f"DCF base case implies ${dcf_implied:.0f} — "
                    f"{abs(diff_pct):.0f}% below current price."
                )
            else:
                parts.append(
                    f"DCF base case implies ${dcf_implied:.0f} — "
                    f"approximately in line with current price."
                )

        if not parts:
            return "Insufficient data for multiples interpretation."

        return " ".join(parts)
