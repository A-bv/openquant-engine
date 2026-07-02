"""
OpenQuant — Reverse DCF engine.

The primary output of OpenQuant.

Instead of asking "what is this company worth?" — which requires
predicting the future — the reverse DCF asks:

    "What FCF growth rate does the current stock price imply
     over the next 10 years?"

This reframes the question from prediction to judgment:
    - The market has already set a price
    - That price implies certain assumptions about the future
    - Are those assumptions reasonable?

This is Warren Buffett's approach. It is more honest than
forward DCF because it does not pretend to know the future.

Implementation:
    scipy.optimize.brentq finds g* such that:
    Current Price = DCF(FCF_series(g*), WACC, terminal_growth) / shares

Formula chain:
    f(g) = IV_per_share(g) - current_price = 0
    IV_per_share(g) = [Σ FCF_t(g)/(1+WACC)^t + TV(g)/(1+WACC)^n
                       - net_debt] / shares

Framing shown in UI (per CFA feedback):
    "This is the constant FCF growth rate required over 10 years
     under the current WACC and terminal growth assumptions —
     holding all other variables fixed. It is one interpretation
     of market expectations, not a complete picture."

Dependency rule: zero Streamlit imports. Pure Python. Fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import brentq, OptimizeResult

from openquant.config import (
    FORECAST_HORIZON_YEARS,
    DEFAULT_TERMINAL_GROWTH_RATE,
    MAX_TERMINAL_GROWTH_RATE,
    DEFAULT_RISK_FREE_RATE,
)
from openquant.valuation.fcf import FCFAnalysis
from openquant.valuation.wacc import WACCResult


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ReverseDCFResult:
    """
    Result of reverse DCF computation.

    Primary output of OpenQuant — shows what the market is
    betting on, not what we think the company is worth.
    """
    ticker: str
    company_name: str

    # The answer
    implied_growth_rate: float           # g* that justifies current price

    # Context for judgment
    historical_median_growth: float      # Historical FCF median growth
    historical_mean_growth: float        # Historical FCF mean growth
    revenue_cagr: float                  # Revenue CAGR as alternative anchor
    damodaran_industry_growth: Optional[float]  # Industry benchmark if available

    # Inputs used
    current_price: float
    wacc: float
    terminal_growth_rate: float
    horizon: int
    net_debt: float
    shares_outstanding: float
    base_fcf: float                      # Starting FCF for the computation

    # Solver diagnostics
    solver_converged: bool
    solver_iterations: int
    residual: float                      # How close f(g*) is to 0

    # Plain language interpretation
    verdict: str                         # Generated automatically
    framing_note: str                    # Always shown — CFA-honest framing

    # Warnings
    warnings: list[str] = field(default_factory=list)

    @property
    def growth_vs_history(self) -> float:
        """Implied growth minus historical median."""
        return self.implied_growth_rate - self.historical_median_growth

    @property
    def market_expects_above_average(self) -> bool:
        """True if implied growth > historical median."""
        return self.implied_growth_rate > self.historical_median_growth

    @property
    def implied_vs_historical_ratio(self) -> float:
        """Implied growth / historical median. >1 means above-average expected."""
        if self.historical_median_growth == 0:
            return 0.0
        return self.implied_growth_rate / self.historical_median_growth


@dataclass
class ReverseDCFFailure:
    """
    Returned when the reverse DCF solver cannot find a solution.

    Contains a human-readable diagnostic explaining why,
    rather than raising a cryptic exception.
    """
    ticker: str
    current_price: float
    wacc: float
    reason: str                          # Plain language explanation
    diagnostic: str                      # More detail for advanced users
    suggestion: str                      # What the user should do


# ── Reverse DCF solver ────────────────────────────────────────────────────────

class ReverseDCFSolver:
    """
    Solves for the implied FCF growth rate using scipy brentq.

    brentq finds a root of f(g) = IV(g) - current_price = 0
    between bracket bounds [g_low, g_high].

    The solver is robust to failure — when it cannot converge,
    it returns a ReverseDCFFailure with a human-readable message
    rather than crashing the app.

    Usage:
        solver = ReverseDCFSolver()
        result = solver.solve(
            fcf_analysis=analysis,
            wacc_result=wacc,
            current_price=180.0,
            shares_outstanding=15e9,
            net_debt=50e9,
        )
        if isinstance(result, ReverseDCFFailure):
            # Show diagnostic to user
        else:
            # Show implied growth rate
    """

    # Bracket bounds for brentq search
    # Growth rate between -50% and +100% covers all realistic cases
    G_LOW = -0.50
    G_HIGH = 1.00
    MAX_ITER = 200
    TOLERANCE = 1e-8

    def solve(
        self,
        fcf_analysis: FCFAnalysis,
        wacc_result: WACCResult,
        current_price: float,
        shares_outstanding: float,
        net_debt: float,
        terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH_RATE,
        horizon: int = FORECAST_HORIZON_YEARS,
        use_ex_sbc: bool = False,
    ) -> ReverseDCFResult | ReverseDCFFailure:
        """
        Solve for implied FCF growth rate.

        Args:
            fcf_analysis: FCFAnalysis with historical FCF data.
            wacc_result: WACCResult with discount rate.
            current_price: Current stock price per share.
            shares_outstanding: Diluted shares outstanding.
            net_debt: Total debt minus cash.
            terminal_growth_rate: Terminal growth assumption.
            horizon: Forecast horizon. Default 10 years.
            use_ex_sbc: Use FCF excluding SBC as base.

        Returns:
            ReverseDCFResult if converged, ReverseDCFFailure otherwise.
        """
        warnings = []
        wacc = wacc_result.wacc

        # ── Input validation ──────────────────────────────────────────────────

        if current_price <= 0:
            return ReverseDCFFailure(
                ticker=fcf_analysis.ticker,
                current_price=current_price,
                wacc=wacc,
                reason="Current price must be positive.",
                diagnostic=f"Received price: {current_price}",
                suggestion="Check that the price data is correct.",
            )

        if wacc <= terminal_growth_rate:
            return ReverseDCFFailure(
                ticker=fcf_analysis.ticker,
                current_price=current_price,
                wacc=wacc,
                reason=(
                    f"WACC ({wacc:.1%}) must exceed terminal growth rate "
                    f"({terminal_growth_rate:.1%}) for the DCF formula to work."
                ),
                diagnostic="The growing perpetuity formula diverges when WACC ≤ g.",
                suggestion="Reduce the terminal growth rate assumption.",
            )

        # ── Base FCF ──────────────────────────────────────────────────────────
        if use_ex_sbc:
            base_fcf = fcf_analysis.latest_fcf_ex_sbc
        else:
            base_fcf = fcf_analysis.latest_fcf

        if base_fcf <= 0:
            # Use median of last 3 positive years
            clean = fcf_analysis.fcf_reported.dropna()
            positive = clean[clean > 0]
            if len(positive) >= 2:
                base_fcf = float(positive.iloc[-3:].median())
                warnings.append(
                    "Latest FCF is negative — using median of recent "
                    "positive years as base for reverse DCF."
                )
            else:
                return ReverseDCFFailure(
                    ticker=fcf_analysis.ticker,
                    current_price=current_price,
                    wacc=wacc,
                    reason=(
                        "Insufficient positive FCF history to run reverse DCF. "
                        "The company has not generated meaningful positive cash flows."
                    ),
                    diagnostic=f"Latest FCF: {base_fcf:.0f}. Positive years: {len(positive)}.",
                    suggestion=(
                        "Reverse DCF requires a company with positive free cash flows. "
                        "Consider EV/Revenue or comparable transactions instead."
                    ),
                )

        # ── Define objective function ─────────────────────────────────────────

        def iv_minus_price(g: float) -> float:
            """
            Compute IV(g) - current_price.
            Root of this function is the implied growth rate.
            """
            # Ensure WACC > terminal growth (for terminal value)
            if wacc <= terminal_growth_rate:
                return -current_price  # Force negative

            # Project FCF with growth rate g
            projected_fcf = [
                base_fcf * (1 + g) ** year
                for year in range(1, horizon + 1)
            ]

            # PV of projected FCFs
            pv_fcfs = sum(
                fcf / (1 + wacc) ** t
                for t, fcf in enumerate(projected_fcf, 1)
            )

            # Terminal value = FCF_n × (1+terminal_g) / (WACC - terminal_g)
            terminal_fcf = projected_fcf[-1]
            tv = terminal_fcf * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
            pv_tv = tv / (1 + wacc) ** horizon

            # Enterprise value → equity value → IV per share
            ev = pv_fcfs + pv_tv
            equity_value = ev - net_debt
            iv_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

            return iv_per_share - current_price

        # ── Check bracket validity ────────────────────────────────────────────

        try:
            f_low = iv_minus_price(self.G_LOW)
            f_high = iv_minus_price(self.G_HIGH)
        except Exception as e:
            return ReverseDCFFailure(
                ticker=fcf_analysis.ticker,
                current_price=current_price,
                wacc=wacc,
                reason="Could not evaluate the DCF function.",
                diagnostic=str(e),
                suggestion="Check that all inputs are valid numbers.",
            )

        # brentq requires opposite signs at bracket endpoints
        if f_low * f_high > 0:
            # Both same sign — no root in bracket
            if f_high < 0:
                # Even at 100% growth, IV < current price
                # Stock is priced for impossible growth
                return ReverseDCFFailure(
                    ticker=fcf_analysis.ticker,
                    current_price=current_price,
                    wacc=wacc,
                    reason=(
                        "The current stock price implies FCF growth above 100% "
                        "per year — beyond what this model can solve for. "
                        "The stock appears priced for perfection or the DCF "
                        "framework may not be appropriate here."
                    ),
                    diagnostic=(
                        f"IV at g=100%: ${iv_minus_price(1.0) + current_price:.2f} "
                        f"vs current price ${current_price:.2f}. "
                        f"Base FCF: {base_fcf/1e9:.1f}B, "
                        f"WACC: {wacc:.1%}"
                    ),
                    suggestion=(
                        "This may indicate: (1) the company is priced on "
                        "non-FCF metrics (e.g. revenue growth for early-stage), "
                        "(2) the WACC is understated, or "
                        "(3) DCF is not the right framework."
                    ),
                )
            else:
                # Even at -50% decline, IV > current price
                # Stock appears very undervalued or base FCF is too large
                return ReverseDCFFailure(
                    ticker=fcf_analysis.ticker,
                    current_price=current_price,
                    wacc=wacc,
                    reason=(
                        "Even with a 50% annual FCF decline, the implied "
                        "intrinsic value exceeds the current price. "
                        "The stock appears significantly undervalued "
                        "under this model, or the base FCF is unusually high."
                    ),
                    diagnostic=(
                        f"IV at g=-50%: ${iv_minus_price(-0.5) + current_price:.2f} "
                        f"vs current price ${current_price:.2f}."
                    ),
                    suggestion=(
                        "Review whether the most recent FCF is representative. "
                        "Consider using FCF excluding one-time items."
                    ),
                )

        # ── Solve with brentq ─────────────────────────────────────────────────

        iterations = [0]

        def counting_f(g):
            iterations[0] += 1
            return iv_minus_price(g)

        try:
            g_star = brentq(
                counting_f,
                self.G_LOW,
                self.G_HIGH,
                xtol=self.TOLERANCE,
                maxiter=self.MAX_ITER,
                full_output=False,
            )
            solver_converged = True
            residual = abs(iv_minus_price(g_star))

        except (ValueError, RuntimeError) as e:
            # brentq raises ValueError when the bracket has the same sign at
            # both ends, and RuntimeError when it cannot converge within
            # maxiter; both should degrade to a structured failure rather
            # than crashing the endpoint.
            return ReverseDCFFailure(
                ticker=fcf_analysis.ticker,
                current_price=current_price,
                wacc=wacc,
                reason="The solver failed to converge.",
                diagnostic=str(e),
                suggestion=(
                    "This typically means the DCF model cannot reproduce "
                    "the current price with any reasonable growth assumption. "
                    "Try adjusting the WACC or terminal growth rate."
                ),
            )

        # ── Build result ──────────────────────────────────────────────────────

        hist_median = fcf_analysis.median_growth_rate
        hist_mean = fcf_analysis.mean_growth_rate
        rev_cagr = fcf_analysis.revenue_cagr_5yr

        verdict = self._generate_verdict(
            implied_growth=g_star,
            historical_median=hist_median,
            revenue_cagr=rev_cagr,
            wacc=wacc,
            ticker=fcf_analysis.ticker,
            company_name=fcf_analysis.company_name,
        )

        # CFA-honest framing — always shown
        framing_note = (
            "This is the constant FCF growth rate required over "
            f"{horizon} years under the current WACC ({wacc:.1%}) "
            f"and terminal growth ({terminal_growth_rate:.1%}) assumptions — "
            "holding all other variables fixed. "
            "It is one interpretation of market expectations, "
            "not a complete picture of what drives the stock price."
        )

        return ReverseDCFResult(
            ticker=fcf_analysis.ticker,
            company_name=fcf_analysis.company_name,
            implied_growth_rate=g_star,
            historical_median_growth=hist_median,
            historical_mean_growth=hist_mean,
            revenue_cagr=rev_cagr,
            damodaran_industry_growth=None,  # Set externally if available
            current_price=current_price,
            wacc=wacc,
            terminal_growth_rate=terminal_growth_rate,
            horizon=horizon,
            net_debt=net_debt,
            shares_outstanding=shares_outstanding,
            base_fcf=base_fcf,
            solver_converged=solver_converged,
            solver_iterations=iterations[0],
            residual=residual,
            verdict=verdict,
            framing_note=framing_note,
            warnings=warnings,
        )

    def _generate_verdict(
        self,
        implied_growth: float,
        historical_median: float,
        revenue_cagr: float,
        wacc: float,
        ticker: str,
        company_name: str,
    ) -> str:
        """
        Generate plain-language verdict.

        Compares implied growth to historical performance
        and asks the user to form a judgment — not to trust
        a model output blindly.
        """
        diff = implied_growth - historical_median
        diff_pct = abs(diff) * 100

        if abs(diff) < 0.02:
            comparison = (
                f"approximately in line with its historical median FCF growth "
                f"of {historical_median:.1%}"
            )
            judgment_prompt = (
                "The market's expectations appear consistent with "
                "historical performance. The key question: "
                "is there a reason to expect performance to change?"
            )
        elif implied_growth > historical_median:
            comparison = (
                f"{diff_pct:.0f} percentage points above its historical "
                f"median FCF growth of {historical_median:.1%}"
            )
            judgment_prompt = (
                "The market expects above-average performance. "
                "Is there a clear business reason why FCF growth "
                "will be higher than historical levels?"
            )
        else:
            comparison = (
                f"{diff_pct:.0f} percentage points below its historical "
                f"median FCF growth of {historical_median:.1%}"
            )
            judgment_prompt = (
                "The market expects below-average performance. "
                "Is there a reason FCF growth will be lower "
                "than historical levels — or is this an opportunity?"
            )

        return (
            f"The current price of {company_name} implies the market "
            f"expects FCF to grow at {implied_growth:.1%} per year "
            f"for the next 10 years. This is {comparison}. "
            f"{judgment_prompt}"
        )

    def round_trip_check(
        self,
        result: ReverseDCFResult,
        fcf_analysis: FCFAnalysis,
        wacc_result: WACCResult,
        tolerance: float = 0.01,
    ) -> bool:
        """
        Verify the implied growth rate by running a forward DCF.

        Takes the implied growth rate, runs a forward DCF,
        and checks that the resulting IV matches the current price.

        Args:
            result: ReverseDCFResult from solve().
            fcf_analysis: Same FCFAnalysis used in solve().
            wacc_result: Same WACCResult used in solve().
            tolerance: Maximum allowed price deviation (%). Default 1%.

        Returns:
            True if round-trip check passes.
        """
        from openquant.valuation.dcf import DCFEngine
        engine = DCFEngine()

        forward = engine.value(
            fcf_analysis=fcf_analysis,
            wacc_result=wacc_result,
            current_price=result.current_price,
            shares_outstanding=result.shares_outstanding,
            net_debt=result.net_debt,
            terminal_growth_rate=result.terminal_growth_rate,
            horizon=result.horizon,
        )

        # Use base scenario with implied growth rate
        base = engine._compute_scenario(
            scenario_name="RoundTrip",
            growth_rate=result.implied_growth_rate,
            wacc=result.wacc,
            fcf_analysis=fcf_analysis,
            terminal_growth_rate=result.terminal_growth_rate,
            horizon=result.horizon,
            current_price=result.current_price,
            shares_outstanding=result.shares_outstanding,
            net_debt=result.net_debt,
            use_ex_sbc=False,
        )

        iv = base.intrinsic_value_per_share
        price = result.current_price

        if price <= 0:
            return False

        deviation = abs(iv - price) / price
        return deviation < tolerance
