"""
OpenQuant — Free Cash Flow computation and analysis.

Implements the FCF formula from the EPFL formula sheet:
    FCF = EBIT × (1 − Tax Rate)
        + Depreciation & Amortisation
        − Capital Expenditure
        − Change in Working Capital

Also computes:
    - FCF per share
    - Historical growth rates (median, winsorized)
    - Three-scenario growth assumptions
    - SBC-adjusted FCF (shown separately for transparency)
    - Tax rate normalisation (3-year average)

Dependency rule: zero Streamlit imports. Pure Python. Fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from openquant.config import (
    FORECAST_HORIZON_YEARS,
    SCENARIO_CONSERVATIVE_GROWTH_MULT,
    SCENARIO_OPTIMISTIC_GROWTH_MULT,
    GROWTH_WINSOR_LOW,
    GROWTH_WINSOR_HIGH,
    MAX_TERMINAL_GROWTH_RATE,
)
from openquant.data import FinancialStatements
from openquant.common import median_growth_rate, winsorize_series, format_currency


# ── EPFL formula sheet primitive ──────────────────────────────────────────────


def fcf_from_ebit_components(
    ebitda: float,
    depreciation: float,
    tax_rate: float,
    change_in_wc: float,
    capex: float = 0.0,
) -> float:
    """
    Free Cash Flow from EBIT components (EPFL formula sheet).

        FCF = (EBITDA − D&A) × (1 − T)  +  D&A  −  ΔWC  −  Capex

    The (EBITDA − D&A) × (1 − T) term is NOPAT; D&A is added back because it
    isn't a real cash outflow; ΔWC and capex are real outflows that EBITDA
    doesn't capture.

    EPFL Sample Exam 1 Problem 2 (in $000s):
        Year 1: EBITDA=12000, D=6000, T=0.35, ΔWC=1500  →  FCF=8400
        Year 2: EBITDA=12000, D=6000, T=0.35, ΔWC=750   →  FCF=9150
        Year 3: EBITDA=15000, D=6000, T=0.35, ΔWC=750   →  FCF=11100
        Year 4: EBITDA=15000, D=6000, T=0.35, ΔWC=-3000 →  FCF=14850
                                                  (WC recovered)

    Args:
        ebitda: Earnings before interest, tax, depreciation and amortisation.
        depreciation: D&A for the period.
        tax_rate: Effective corporate tax rate.
        change_in_wc: Increase in net working capital (positive = cash use).
            Pass a negative value for a working-capital release.
        capex: Capital expenditure for the period (positive = cash use).

    Returns:
        Free cash flow.
    """
    ebit = ebitda - depreciation
    nopat = ebit * (1.0 - tax_rate)
    return nopat + depreciation - change_in_wc - capex


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class FCFAnalysis:
    """
    Complete FCF analysis for one company.

    Contains historical FCF, growth rates, and three-scenario
    projections for the DCF model.
    """
    ticker: str
    company_name: str

    # Historical FCF series
    fcf_reported: pd.Series           # OCF - CapEx (as reported)
    fcf_ex_sbc: pd.Series             # FCF excluding stock-based compensation
    fcf_per_share: pd.Series          # FCF per diluted share

    # FCF margin
    fcf_margin: pd.Series             # FCF / Revenue
    fcf_margin_ex_sbc: pd.Series      # (FCF - SBC) / Revenue

    # Tax rate
    effective_tax_rate_annual: pd.Series   # Annual effective tax rate
    effective_tax_rate_3yr_avg: float      # 3-year average (used in projections)
    effective_tax_rate_latest: float       # Most recent year

    # Growth rates
    yoy_growth_rates: pd.Series       # Year-over-year FCF growth
    median_growth_rate: float         # Winsorized median (base case default)
    mean_growth_rate: float           # Simple mean (shown for reference)
    revenue_cagr_5yr: float           # Revenue CAGR as alternative anchor

    # Three scenario growth assumptions
    growth_conservative: float        # Conservative scenario
    growth_base: float                # Base case scenario
    growth_optimistic: float          # Optimistic scenario

    # Warnings
    warnings: list[str] = field(default_factory=list)

    @property
    def latest_fcf(self) -> float:
        """Most recent annual FCF."""
        clean = self.fcf_reported.dropna()
        return float(clean.iloc[-1]) if len(clean) > 0 else 0.0

    @property
    def latest_fcf_ex_sbc(self) -> float:
        """Most recent annual FCF excluding SBC."""
        clean = self.fcf_ex_sbc.dropna()
        return float(clean.iloc[-1]) if len(clean) > 0 else 0.0

    @property
    def years_of_history(self) -> int:
        """Number of years of FCF data available."""
        return len(self.fcf_reported.dropna())


@dataclass
class FCFProjection:
    """
    Projected FCF series for DCF model.
    One scenario (conservative, base, or optimistic).
    """
    scenario_name: str                # "Conservative", "Base", "Optimistic"
    growth_rate: float                # Annual FCF growth rate assumed
    projected_fcf: pd.Series          # 10-year projection
    terminal_fcf: float               # FCF in final forecast year
    base_fcf: float                   # Starting FCF for projection

    @property
    def total_projected_fcf(self) -> float:
        """Sum of all projected FCFs (undiscounted)."""
        return float(self.projected_fcf.sum())


# ── FCF analyser ──────────────────────────────────────────────────────────────

class FCFAnalyser:
    """
    Computes FCF analysis from financial statements.

    Implements the EPFL FCF formula directly.
    Handles SBC separately for transparency.
    Uses winsorized median for robust growth estimates.

    Usage:
        analyser = FCFAnalyser()
        analysis = analyser.analyse(statements)
        projection = analyser.project(analysis, scenario="base")
    """

    def analyse(self, statements: FinancialStatements) -> FCFAnalysis:
        """
        Compute complete FCF analysis from financial statements.

        Args:
            statements: Fetched financial statements from DataFetcher.

        Returns:
            FCFAnalysis with historical data and growth assumptions.
        """
        warnings = []

        # ── FCF series ────────────────────────────────────────────────────────

        fcf_reported = statements.free_cash_flow.copy()
        sbc = statements.stock_based_compensation.fillna(0)

        # FCF excluding SBC — SBC is a real economic cost
        # FCF reported already excludes SBC from cash flow perspective
        # But SBC dilutes shareholders — subtract it for a more conservative view
        fcf_ex_sbc = fcf_reported - sbc

        # FCF per share
        shares = statements.shares_outstanding
        fcf_per_share = fcf_reported / shares
        fcf_per_share = fcf_per_share.replace([np.inf, -np.inf], np.nan)

        # FCF margins
        revenue = statements.revenue
        fcf_margin = (fcf_reported / revenue).replace([np.inf, -np.inf], np.nan)
        fcf_margin_ex_sbc = (fcf_ex_sbc / revenue).replace([np.inf, -np.inf], np.nan)

        # ── Tax rate ──────────────────────────────────────────────────────────

        eff_tax = statements.effective_tax_rate.dropna()

        if len(eff_tax) >= 3:
            tax_3yr_avg = float(eff_tax.iloc[-3:].mean())
        elif len(eff_tax) >= 1:
            tax_3yr_avg = float(eff_tax.mean())
            warnings.append(
                "Less than 3 years of tax data available. "
                "Using available history for tax rate estimate."
            )
        else:
            tax_3yr_avg = 0.21  # US statutory rate as fallback
            warnings.append(
                "No effective tax rate data available. "
                "Using 21% US statutory rate as approximation."
            )

        tax_latest = float(eff_tax.iloc[-1]) if len(eff_tax) > 0 else tax_3yr_avg

        # ── Growth rates ──────────────────────────────────────────────────────

        fcf_clean = fcf_reported.dropna()
        yoy_growth_raw = fcf_clean.pct_change().dropna()

        # Percentage growth is only economically meaningful when BOTH the
        # current and prior year FCF are positive.  Transitions that cross
        # zero (e.g. -$3B → +$1B) or that start from a near-zero negative
        # base produce extreme/infinite values (e.g. -21,700%) that blow up
        # the mean and mislead scenario construction.
        prior_fcf = fcf_clean.shift(1)
        both_positive = (fcf_clean > 0) & (prior_fcf > 0)
        yoy_growth_filtered = yoy_growth_raw[both_positive.reindex(yoy_growth_raw.index, fill_value=False)]

        has_negative_fcf = (fcf_clean <= 0).any()

        if len(yoy_growth_filtered) >= 3:
            yoy_growth = yoy_growth_filtered
            if has_negative_fcf:
                warnings.append(
                    f"{statements.company_name} had negative FCF in some historical years. "
                    "Growth rates are computed only from years where FCF was positive in both "
                    "the current and prior year — sign-crossing transitions produce "
                    "mathematically extreme and economically meaningless percentages."
                )
        else:
            # Not enough positive-to-positive transitions; use full series but warn
            yoy_growth = yoy_growth_raw
            if has_negative_fcf:
                warnings.append(
                    f"{statements.company_name} had negative FCF in some historical years. "
                    "Growth rate estimates may be unreliable. Revenue CAGR may be a "
                    "more reliable growth anchor for this company."
                )

        if len(yoy_growth) >= 2:
            # Winsorized median — robust to outliers
            winsorized = winsorize_series(
                yoy_growth,
                lower_quantile=GROWTH_WINSOR_LOW,
                upper_quantile=GROWTH_WINSOR_HIGH,
            )
            median_gr = float(winsorized.median())
            mean_gr = float(winsorized.mean())
        else:
            median_gr = 0.05  # Conservative default
            mean_gr = 0.05
            warnings.append(
                "Insufficient FCF history for reliable growth rate estimate. "
                "Using 5% default growth rate."
            )

        # Revenue CAGR as alternative anchor
        rev_clean = revenue.dropna()
        if len(rev_clean) >= 3:
            from openquant.common import cagr
            try:
                rev_cagr = cagr(
                    float(rev_clean.iloc[0]),
                    float(rev_clean.iloc[-1]),
                    len(rev_clean) - 1,
                )
            except ValueError:
                rev_cagr = median_gr
        else:
            rev_cagr = median_gr

        # ── Scenario growth rates ─────────────────────────────────────────────

        # Base case: winsorized median FCF growth
        # Conservative: base × 0.7
        # Optimistic: base × 1.3
        # All capped at MAX_TERMINAL_GROWTH_RATE × 3 for reasonableness
        max_growth_cap = 0.35  # Max 35% projection growth — prevents absurd inputs only

        growth_base = float(np.clip(median_gr, -0.10, max_growth_cap))
        growth_conservative = float(
            np.clip(
                median_gr * SCENARIO_CONSERVATIVE_GROWTH_MULT,
                -0.10,
                max_growth_cap,
            )
        )
        growth_optimistic = float(
            np.clip(
                median_gr * SCENARIO_OPTIMISTIC_GROWTH_MULT,
                -0.10,
                max_growth_cap,
            )
        )

        # If the cap collapses base/optimistic together, the user loses the
        # promised scenario spread. Surface that explicitly.
        if np.isclose(growth_base, growth_optimistic):
            warnings.append(
                f"Base and optimistic growth scenarios both clip to "
                f"{growth_base:.1%}. The optimistic case provides no "
                f"differentiation from base — historical growth is already "
                f"above the {max_growth_cap:.0%} sustainable cap."
            )

        # Warn if base growth is negative
        if growth_base < 0:
            warnings.append(
                f"Base case FCF growth is negative ({growth_base:.1%}). "
                f"This suggests FCF has been declining. "
                f"Review whether this trend is likely to continue."
            )

        # Warn if growth is very high
        if growth_base > 0.15:
            warnings.append(
                f"Base case FCF growth is high ({growth_base:.1%}). "
                f"High growth rates are difficult to sustain and "
                f"the optimistic scenario may be unrealistic."
            )

        return FCFAnalysis(
            ticker=statements.ticker,
            company_name=statements.company_name,
            fcf_reported=fcf_reported,
            fcf_ex_sbc=fcf_ex_sbc,
            fcf_per_share=fcf_per_share,
            fcf_margin=fcf_margin,
            fcf_margin_ex_sbc=fcf_margin_ex_sbc,
            effective_tax_rate_annual=statements.effective_tax_rate,
            effective_tax_rate_3yr_avg=tax_3yr_avg,
            effective_tax_rate_latest=tax_latest,
            yoy_growth_rates=yoy_growth,
            median_growth_rate=median_gr,
            mean_growth_rate=mean_gr,
            revenue_cagr_5yr=rev_cagr,
            growth_conservative=growth_conservative,
            growth_base=growth_base,
            growth_optimistic=growth_optimistic,
            warnings=warnings,
        )

    def project(
        self,
        analysis: FCFAnalysis,
        scenario: str = "base",
        custom_growth: Optional[float] = None,
        use_ex_sbc: bool = False,
        horizon: int = FORECAST_HORIZON_YEARS,
    ) -> FCFProjection:
        """
        Project FCF series for DCF model.

        Args:
            analysis: FCFAnalysis from analyse().
            scenario: One of "conservative", "base", "optimistic".
            custom_growth: Override growth rate if provided.
            use_ex_sbc: Use FCF excluding SBC as starting point.
            horizon: Forecast horizon in years. Default 10.

        Returns:
            FCFProjection with year-by-year projected FCFs.

        Raises:
            ValueError: If scenario is not recognised.
        """
        scenario = scenario.lower()

        if custom_growth is not None:
            growth_rate = custom_growth
            scenario_name = "Custom"
        elif scenario == "conservative":
            growth_rate = analysis.growth_conservative
            scenario_name = "Conservative"
        elif scenario == "base":
            growth_rate = analysis.growth_base
            scenario_name = "Base"
        elif scenario == "optimistic":
            growth_rate = analysis.growth_optimistic
            scenario_name = "Optimistic"
        else:
            raise ValueError(
                f"Unknown scenario '{scenario}'. "
                f"Choose from: conservative, base, optimistic."
            )

        # Starting FCF
        if use_ex_sbc:
            base_fcf = analysis.latest_fcf_ex_sbc
        else:
            base_fcf = analysis.latest_fcf

        if base_fcf <= 0:
            # Try median of last 3 positive years before falling back to all
            # history; refuse to project from a non-positive base because
            # negative * (1+g)^t stays negative and produces meaningless DCFs.
            fcf_clean = analysis.fcf_reported.dropna()
            positive = fcf_clean[fcf_clean > 0]
            if len(positive) >= 1:
                base_fcf = float(positive.iloc[-min(3, len(positive)):].median())
            else:
                raise ValueError(
                    f"Cannot project FCF for {analysis.ticker}: no positive "
                    f"FCF in history. DCF is not appropriate for companies "
                    f"without a positive free-cash-flow track record."
                )

        # Project FCF for each year
        projected_values = []
        for year in range(1, horizon + 1):
            projected_fcf = base_fcf * (1 + growth_rate) ** year
            projected_values.append(projected_fcf)

        projected_series = pd.Series(
            projected_values,
            index=range(1, horizon + 1),
            name=f"FCF_{scenario_name}",
        )

        return FCFProjection(
            scenario_name=scenario_name,
            growth_rate=growth_rate,
            projected_fcf=projected_series,
            terminal_fcf=projected_values[-1],
            base_fcf=base_fcf,
        )

    def project_all_scenarios(
        self,
        analysis: FCFAnalysis,
        use_ex_sbc: bool = False,
        horizon: int = FORECAST_HORIZON_YEARS,
    ) -> dict[str, FCFProjection]:
        """
        Project all three scenarios at once.

        Args:
            analysis: FCFAnalysis from analyse().
            use_ex_sbc: Use FCF excluding SBC.
            horizon: Forecast horizon.

        Returns:
            Dict with keys "conservative", "base", "optimistic".
        """
        return {
            "conservative": self.project(analysis, "conservative", use_ex_sbc=use_ex_sbc, horizon=horizon),
            "base": self.project(analysis, "base", use_ex_sbc=use_ex_sbc, horizon=horizon),
            "optimistic": self.project(analysis, "optimistic", use_ex_sbc=use_ex_sbc, horizon=horizon),
        }

    def summary_text(self, analysis: FCFAnalysis) -> str:
        """
        Generate plain-language FCF summary.

        Args:
            analysis: FCFAnalysis from analyse().

        Returns:
            Plain language summary string.
        """
        fcf_clean = analysis.fcf_reported.dropna()
        if len(fcf_clean) == 0:
            return "No FCF data available."

        latest = analysis.latest_fcf
        median_margin = float(analysis.fcf_margin.dropna().median())

        direction = "growing" if analysis.median_growth_rate > 0.02 else (
            "declining" if analysis.median_growth_rate < -0.02 else "stable"
        )

        parts = [
            f"{analysis.company_name} generated "
            f"{format_currency(latest)} in free cash flow in its most recent year.",

            f"FCF has been {direction} at a median rate of "
            f"{analysis.median_growth_rate:.1%} per year "
            f"over the last {analysis.years_of_history} years.",

            f"FCF margin (FCF as % of revenue) has averaged "
            f"{median_margin:.1%}.",
        ]

        if analysis.warnings:
            parts.append(
                f"⚠ {analysis.warnings[0]}"
            )

        return " ".join(parts)
