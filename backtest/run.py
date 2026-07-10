"""
Backtest pipeline — run the OpenQuant model "as of" a historical date and
record the verdict.

Usage:
    python -m backtest.run AAPL 2014-01-31

Produces a dict of model outputs + realized outcomes through 2024-01-31.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional

from backtest.edgar_historical import (
    fetch_prices_as_of,
    fetch_statements_as_of,
    get_price_on,
    realized_total_return,
)
from backtest.macro import get_macro
from openquant.valuation.dcf import DCFEngine
from openquant.valuation.fcf import FCFAnalyser
from openquant.valuation.reverse_dcf import ReverseDCFResult, ReverseDCFSolver
from openquant.valuation.suitability import SuitabilityChecker
from openquant.valuation.wacc import WACCBuilder


@dataclass
class BacktestRow:
    """One row of the backtest output."""
    ticker: str
    as_of: str
    company_name: str

    # As-of inputs
    market_price_as_of: float
    market_cap_as_of: float
    rf: float
    mrp: float
    beta: float
    wacc: float

    # Model outputs at as_of
    iv_conservative: Optional[float]
    iv_base: Optional[float]
    iv_optimistic: Optional[float]
    implied_growth: Optional[float]
    historical_median_growth: Optional[float]
    suitability_rating: str

    # Realized outcomes (filled in by `compute_realized()`)
    price_at_horizon: Optional[float] = None
    realized_total_return: Optional[float] = None
    realized_annualised_return: Optional[float] = None

    # Verdict bucket
    verdict: Optional[str] = None  # "overvalued" / "fairly_priced" / "undervalued"

    # Failures
    error: Optional[str] = None


def analyse_as_of(ticker: str, as_of: date) -> BacktestRow:
    """Run the full OpenQuant model as of `as_of` and return a BacktestRow."""
    try:
        statements = fetch_statements_as_of(ticker, as_of)
        price_data = fetch_prices_as_of(ticker, as_of)
        # Shares in `statements` are already split-adjusted by
        # fetch_statements_as_of, so they line up with yfinance's split-adjusted
        # closes without any further scaling here (see the note below).
        current_price = get_price_on(ticker, as_of, adjusted=True)
        macro = get_macro(as_of)

        fcf_a = FCFAnalyser().analyse(statements)

        wacc_r = WACCBuilder().compute_wacc(
            statements, price_data, current_price,
            risk_free_rate=macro.risk_free_rate,
            market_risk_premium=macro.market_risk_premium,
        )

        suit = SuitabilityChecker().check(
            statements,
            trading_days=len(price_data.prices),
            sector="",
            wacc_estimate=wacc_r.wacc,
            terminal_growth=macro.terminal_growth,
        )

        # Shares are already split-adjusted inside `statements` by
        # fetch_statements_as_of (so WACC's internal market-cap matches
        # the adjusted price). Use them as-is.
        shares = float(statements.shares_outstanding.dropna().iloc[-1])
        debt = float(statements.total_debt.dropna().iloc[-1]) if not statements.total_debt.dropna().empty else 0.0
        cash = float(statements.cash_and_equivalents.dropna().iloc[-1]) if not statements.cash_and_equivalents.dropna().empty else 0.0
        net_debt = debt - cash
        market_cap = current_price * shares

        row = BacktestRow(
            ticker=ticker,
            as_of=as_of.isoformat(),
            company_name=statements.company_name,
            market_price_as_of=current_price,
            market_cap_as_of=market_cap,
            rf=macro.risk_free_rate,
            mrp=macro.market_risk_premium,
            beta=wacc_r.beta,
            wacc=wacc_r.wacc,
            iv_conservative=None,
            iv_base=None,
            iv_optimistic=None,
            implied_growth=None,
            historical_median_growth=fcf_a.median_growth_rate,
            suitability_rating=suit.overall_rating.value,
        )

        if not suit.is_suitable:
            row.verdict = "model_inapplicable"
            return row

        dcf_r = DCFEngine().value(
            fcf_analysis=fcf_a,
            wacc_result=wacc_r,
            current_price=current_price,
            shares_outstanding=shares,
            net_debt=net_debt,
            terminal_growth_rate=macro.terminal_growth,
        )
        row.iv_conservative = dcf_r.conservative.intrinsic_value_per_share
        row.iv_base = dcf_r.base.intrinsic_value_per_share
        row.iv_optimistic = dcf_r.optimistic.intrinsic_value_per_share

        rev_r = ReverseDCFSolver().solve(
            fcf_analysis=fcf_a,
            wacc_result=wacc_r,
            current_price=current_price,
            shares_outstanding=shares,
            net_debt=net_debt,
            terminal_growth_rate=macro.terminal_growth,
        )
        if isinstance(rev_r, ReverseDCFResult):
            row.implied_growth = rev_r.implied_growth_rate

        # Bucket the verdict: vs base case IV
        if row.iv_base and row.iv_base > 0:
            gap = (row.iv_base - current_price) / current_price
            if gap > 0.20:
                row.verdict = "undervalued"
            elif gap < -0.20:
                row.verdict = "overvalued"
            else:
                row.verdict = "fairly_priced"

        return row

    except Exception as e:
        return BacktestRow(
            ticker=ticker, as_of=as_of.isoformat(), company_name="",
            market_price_as_of=float("nan"), market_cap_as_of=float("nan"),
            rf=float("nan"), mrp=float("nan"), beta=float("nan"), wacc=float("nan"),
            iv_conservative=None, iv_base=None, iv_optimistic=None,
            implied_growth=None, historical_median_growth=None,
            suitability_rating="error", error=f"{type(e).__name__}: {e}",
        )


def compute_realized(row: BacktestRow, horizon_date: date) -> BacktestRow:
    """
    Augment row with realized total return through horizon_date.

    Uses split- and dividend-adjusted prices for the return calculation
    (this is the correct TSR — investors got the splits and dividends).
    """
    if row.error is not None:
        return row
    try:
        as_of = date.fromisoformat(row.as_of)
        gross_multiple = realized_total_return(row.ticker, as_of, horizon_date)
        row.price_at_horizon = get_price_on(row.ticker, horizon_date, adjusted=False)
        row.realized_total_return = gross_multiple - 1.0
        years = (horizon_date - as_of).days / 365.25
        row.realized_annualised_return = gross_multiple ** (1.0 / years) - 1.0
    except Exception as e:
        row.error = f"realized: {type(e).__name__}: {e}"
    return row


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: python -m backtest.run <TICKER> <AS_OF_YYYY-MM-DD> [<HORIZON_YYYY-MM-DD>]")
        sys.exit(1)

    ticker = args[0].upper()
    as_of = date.fromisoformat(args[1])
    horizon = date.fromisoformat(args[2]) if len(args) >= 3 else date(2024, 1, 31)

    row = analyse_as_of(ticker, as_of)
    row = compute_realized(row, horizon)

    print(json.dumps(asdict(row), indent=2, default=str))
