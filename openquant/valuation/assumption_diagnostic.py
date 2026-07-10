"""
OpenQuant — Assumption Diagnostic.

8-dimension severity-weighted diagnostic shown BEFORE valuation results.

This is the honest gate — tells users how much to trust the analysis
before they see a single number.

Critical distinction (per CFA feedback):
    This is a DIAGNOSTIC, not a confidence score.
    Green means assumptions are internally consistent.
    Green does NOT mean the valuation is reliable.
    All DCF valuations carry fundamental uncertainty about the future.

8 dimensions (per external CFA evaluation):
    1. FCF stability
    2. FCF margin stability
    3. Revenue cyclicality
    4. Terminal value dominance
    5. Beta reliability
    6. Data completeness
    7. Growth reasonableness
    8. Reinvestment support (3-check severity scoring)

Severity scoring (per CFA recommendation):
    0 = no issue
    1 = mild concern
    2 = severe failure
    0-1 total = Green
    2-3 total = Amber
    4+ total = Red
    One severity-2 failure alone can trigger Red.

Dependency rule: zero Streamlit imports. Pure Python. Fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from openquant.config import (
    ASSET_LIGHT_CAPEX_THRESHOLD,
    BETA_RANGE_MILD_THRESHOLD,
    BETA_RANGE_SEVERE_THRESHOLD,
    FCF_MARGIN_SD_MILD,
    FCF_MARGIN_SD_SEVERE,
    GROWTH_MILD_MULT,
    GROWTH_SEVERE_MULT,
    REVENUE_SWING_MILD,
    REVENUE_SWING_SEVERE,
    SEVERITY_MILD,
    SEVERITY_NONE,
    SEVERITY_SEVERE,
    TERMINAL_VALUE_SEVERE_THRESHOLD,
    TERMINAL_VALUE_WARNING_THRESHOLD,
)
from openquant.data import FinancialStatements
from openquant.valuation.dcf import DCFResult
from openquant.valuation.reverse_dcf import ReverseDCFResult
from openquant.valuation.wacc import BetaResult


class DiagnosticRating(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


@dataclass
class DimensionScore:
    """Score for one diagnostic dimension."""
    name: str
    severity: int                    # 0, 1, or 2
    rating: DiagnosticRating
    message: str                     # Plain language
    detail: Optional[str] = None     # Expandable detail


@dataclass
class AssumptionDiagnostic:
    """
    Complete 8-dimension assumption diagnostic.

    Shown before valuation results.
    Always includes the honest disclaimer.
    """
    ticker: str
    overall_rating: DiagnosticRating
    total_severity: int
    dimensions: list[DimensionScore]

    # Always shown — CFA-honest framing
    disclaimer: str = (
        "A Green rating means assumptions appear internally consistent — "
        "not that the valuation is reliable. "
        "All DCF valuations carry fundamental uncertainty about the future."
    )

    @property
    def red_dimensions(self) -> list[DimensionScore]:
        return [d for d in self.dimensions if d.rating == DiagnosticRating.RED]

    @property
    def amber_dimensions(self) -> list[DimensionScore]:
        return [d for d in self.dimensions if d.rating == DiagnosticRating.AMBER]

    @property
    def summary_text(self) -> str:
        n_issues = len(self.red_dimensions) + len(self.amber_dimensions)
        if n_issues == 0:
            return "All 8 diagnostic dimensions are Green. Assumptions appear internally consistent."
        names = [d.name for d in self.red_dimensions + self.amber_dimensions]
        return (
            f"Assumption diagnostic: {self.overall_rating.value.upper()} — "
            f"{n_issues} of 8 dimensions flagged: {', '.join(names)}."
        )


class DiagnosticBuilder:
    """
    Builds the 8-dimension assumption diagnostic.

    Called after FCF analysis, WACC computation, and DCF result
    are available — uses all of them for context.
    """

    def build(
        self,
        statements: FinancialStatements,
        dcf_result: DCFResult,
        beta_result: BetaResult,
        reverse_result: Optional[ReverseDCFResult] = None,
    ) -> AssumptionDiagnostic:
        """
        Build complete diagnostic from all available results.

        Args:
            statements: Financial statements.
            dcf_result: Forward DCF result (all 3 scenarios).
            beta_result: Beta estimation result.
            reverse_result: Optional reverse DCF result.

        Returns:
            AssumptionDiagnostic with 8 scored dimensions.
        """
        dimensions = [
            self._score_fcf_stability(statements),
            self._score_fcf_margin_stability(statements),
            self._score_revenue_cyclicality(statements),
            self._score_terminal_value_dominance(dcf_result),
            self._score_beta_reliability(beta_result),
            self._score_data_completeness(statements),
            self._score_growth_reasonableness(dcf_result, reverse_result),
            self._score_reinvestment_support(statements, dcf_result),
        ]

        total_severity = sum(d.severity for d in dimensions)

        # Overall rating
        if total_severity >= 4 or any(d.severity == SEVERITY_SEVERE for d in dimensions):
            overall = DiagnosticRating.RED
        elif total_severity >= 2:
            overall = DiagnosticRating.AMBER
        else:
            overall = DiagnosticRating.GREEN

        return AssumptionDiagnostic(
            ticker=statements.ticker,
            overall_rating=overall,
            total_severity=total_severity,
            dimensions=dimensions,
        )

    # ── Dimension 1: FCF stability ────────────────────────────────────────────

    def _score_fcf_stability(
        self, statements: FinancialStatements
    ) -> DimensionScore:
        """Are cash flows consistently positive and predictable?"""
        fcf = statements.free_cash_flow.dropna()
        if len(fcf) == 0:
            return DimensionScore(
                name="FCF Stability",
                severity=SEVERITY_SEVERE,
                rating=DiagnosticRating.RED,
                message="No FCF data available.",
            )

        n_negative = int((fcf < 0).sum())
        n_total = len(fcf)

        if n_negative >= 3 or n_negative / n_total > 0.5:
            return DimensionScore(
                name="FCF Stability",
                severity=SEVERITY_SEVERE,
                rating=DiagnosticRating.RED,
                message=f"FCF negative in {n_negative}/{n_total} years — highly unstable.",
                detail="Projecting from an unstable FCF base produces unreliable results.",
            )
        elif n_negative > 0:
            return DimensionScore(
                name="FCF Stability",
                severity=SEVERITY_MILD,
                rating=DiagnosticRating.AMBER,
                message=f"FCF negative in {n_negative}/{n_total} years — some instability.",
            )
        return DimensionScore(
            name="FCF Stability",
            severity=SEVERITY_NONE,
            rating=DiagnosticRating.GREEN,
            message=f"FCF positive in all {n_total} years.",
        )

    # ── Dimension 2: FCF margin stability ────────────────────────────────────

    def _score_fcf_margin_stability(
        self, statements: FinancialStatements
    ) -> DimensionScore:
        """Are FCF margins stable or swinging heavily?"""
        margin = statements.fcf_margin.dropna()
        if len(margin) < 3:
            return DimensionScore(
                name="FCF Margin Stability",
                severity=SEVERITY_MILD,
                rating=DiagnosticRating.AMBER,
                message="Insufficient margin history for stability assessment.",
            )

        sd = float(margin.std(ddof=1))

        if sd > FCF_MARGIN_SD_SEVERE:
            return DimensionScore(
                name="FCF Margin Stability",
                severity=SEVERITY_SEVERE,
                rating=DiagnosticRating.RED,
                message=f"FCF margin highly volatile (SD: {sd:.1%}).",
                detail=f"Range: {margin.min():.1%} to {margin.max():.1%}. Projections based on average margins may mislead.",
            )
        elif sd > FCF_MARGIN_SD_MILD:
            return DimensionScore(
                name="FCF Margin Stability",
                severity=SEVERITY_MILD,
                rating=DiagnosticRating.AMBER,
                message=f"Moderate FCF margin variability (SD: {sd:.1%}).",
            )
        return DimensionScore(
            name="FCF Margin Stability",
            severity=SEVERITY_NONE,
            rating=DiagnosticRating.GREEN,
            message=f"FCF margins stable (SD: {sd:.1%}).",
        )

    # ── Dimension 3: Revenue cyclicality ─────────────────────────────────────

    def _score_revenue_cyclicality(
        self, statements: FinancialStatements
    ) -> DimensionScore:
        """Is revenue smooth or highly volatile?"""
        rev = statements.revenue.dropna()
        if len(rev) < 3:
            return DimensionScore(
                name="Revenue Cyclicality",
                severity=SEVERITY_MILD,
                rating=DiagnosticRating.AMBER,
                message="Insufficient revenue history.",
            )

        yoy = rev.pct_change().dropna()
        n_declines = int((yoy < -0.05).sum())
        max_decline = float(yoy[yoy < 0].min()) if (yoy < 0).any() else 0.0

        if n_declines >= 2 or max_decline < -REVENUE_SWING_SEVERE:
            return DimensionScore(
                name="Revenue Cyclicality",
                severity=SEVERITY_SEVERE,
                rating=DiagnosticRating.RED,
                message=f"High revenue cyclicality — {n_declines} year(s) with >5% decline.",
                detail=f"Worst decline: {max_decline:.1%}. Consider normalised margins.",
            )
        elif n_declines == 1 or max_decline < -REVENUE_SWING_MILD:
            return DimensionScore(
                name="Revenue Cyclicality",
                severity=SEVERITY_MILD,
                rating=DiagnosticRating.AMBER,
                message=f"Minor revenue decline detected (worst: {max_decline:.1%}).",
            )
        return DimensionScore(
            name="Revenue Cyclicality",
            severity=SEVERITY_NONE,
            rating=DiagnosticRating.GREEN,
            message="Revenue shows consistent growth with no significant declines.",
        )

    # ── Dimension 4: Terminal value dominance ─────────────────────────────────

    def _score_terminal_value_dominance(
        self, dcf_result: DCFResult
    ) -> DimensionScore:
        """What % of enterprise value comes from terminal value?"""
        tv_pct = dcf_result.base.terminal_value_pct

        if tv_pct > TERMINAL_VALUE_SEVERE_THRESHOLD:
            return DimensionScore(
                name="Terminal Value Dominance",
                severity=SEVERITY_SEVERE,
                rating=DiagnosticRating.RED,
                message=f"Terminal value = {tv_pct:.0%} of enterprise value — extremely high.",
                detail=(
                    "When terminal value exceeds 75% of EV, the valuation "
                    "is almost entirely driven by the long-run growth assumption, "
                    "which is the least reliable input."
                ),
            )
        elif tv_pct > TERMINAL_VALUE_WARNING_THRESHOLD:
            return DimensionScore(
                name="Terminal Value Dominance",
                severity=SEVERITY_MILD,
                rating=DiagnosticRating.AMBER,
                message=f"Terminal value = {tv_pct:.0%} of enterprise value.",
                detail="Review the terminal growth rate assumption carefully.",
            )
        return DimensionScore(
            name="Terminal Value Dominance",
            severity=SEVERITY_NONE,
            rating=DiagnosticRating.GREEN,
            message=f"Terminal value = {tv_pct:.0%} of enterprise value — reasonable.",
        )

    # ── Dimension 5: Beta reliability ─────────────────────────────────────────

    def _score_beta_reliability(
        self, beta_result: BetaResult
    ) -> DimensionScore:
        """Is rolling beta stable enough to trust the WACC?"""
        r = beta_result.rolling_beta_range

        if r > BETA_RANGE_SEVERE_THRESHOLD:
            return DimensionScore(
                name="Beta Reliability",
                severity=SEVERITY_SEVERE,
                rating=DiagnosticRating.RED,
                message=f"Beta highly unstable — rolling range: {r:.2f}.",
                detail="WACC estimate may not reflect current market sensitivity.",
            )
        elif r > BETA_RANGE_MILD_THRESHOLD:
            return DimensionScore(
                name="Beta Reliability",
                severity=SEVERITY_MILD,
                rating=DiagnosticRating.AMBER,
                message=f"Moderate beta instability — rolling range: {r:.2f}.",
            )
        return DimensionScore(
            name="Beta Reliability",
            severity=SEVERITY_NONE,
            rating=DiagnosticRating.GREEN,
            message=f"Beta is stable — rolling range: {r:.2f}.",
        )

    # ── Dimension 6: Data completeness ────────────────────────────────────────

    def _score_data_completeness(
        self, statements: FinancialStatements
    ) -> DimensionScore:
        """Are all required fields available and consistent?"""
        critical_fields = {
            "FCF": statements.free_cash_flow,
            "Revenue": statements.revenue,
            "Total Debt": statements.total_debt,
            "Shares": statements.shares_outstanding,
            "Interest Expense": statements.interest_expense,
        }

        missing = [
            name for name, s in critical_fields.items()
            if len(s.dropna()) == 0
        ]

        sparse = [
            name for name, s in critical_fields.items()
            if 0 < len(s.dropna()) < 3
        ]

        warnings = statements.data_warnings

        if len(missing) >= 2:
            return DimensionScore(
                name="Data Completeness",
                severity=SEVERITY_SEVERE,
                rating=DiagnosticRating.RED,
                message=f"Missing critical data: {', '.join(missing)}.",
            )
        elif missing or sparse or len(warnings) > 2:
            return DimensionScore(
                name="Data Completeness",
                severity=SEVERITY_MILD,
                rating=DiagnosticRating.AMBER,
                message=(
                    "Some data gaps detected."
                    + (f" Missing: {', '.join(missing)}." if missing else "")
                    + (f" Sparse: {', '.join(sparse)}." if sparse else "")
                ),
            )
        return DimensionScore(
            name="Data Completeness",
            severity=SEVERITY_NONE,
            rating=DiagnosticRating.GREEN,
            message="All critical data fields available.",
        )

    # ── Dimension 7: Growth reasonableness ───────────────────────────────────

    def _score_growth_reasonableness(
        self,
        dcf_result: DCFResult,
        reverse_result: Optional[ReverseDCFResult],
    ) -> DimensionScore:
        """Is implied growth plausible vs history, industry, and GDP?"""
        if reverse_result is None or not isinstance(reverse_result, ReverseDCFResult):
            # Use base case DCF growth as proxy
            base_growth = dcf_result.base.growth_rate
            hist_growth = 0.05  # Fallback
            ratio = base_growth / hist_growth if hist_growth != 0 else 1.0
        else:
            base_growth = reverse_result.implied_growth_rate
            hist_growth = reverse_result.historical_median_growth
            ratio = reverse_result.implied_vs_historical_ratio

        gdp_growth = 0.03  # Long-run nominal GDP

        if base_growth > gdp_growth * 4 or ratio > GROWTH_SEVERE_MULT:
            return DimensionScore(
                name="Growth Reasonableness",
                severity=SEVERITY_SEVERE,
                rating=DiagnosticRating.RED,
                message=f"Implied growth ({base_growth:.1%}) is very high vs history ({hist_growth:.1%}).",
                detail=(
                    f"Implied growth is {ratio:.1f}× historical median. "
                    "Very few companies sustain above-GDP growth for 10 years."
                ),
            )
        elif ratio > GROWTH_MILD_MULT or base_growth > gdp_growth * 2:
            return DimensionScore(
                name="Growth Reasonableness",
                severity=SEVERITY_MILD,
                rating=DiagnosticRating.AMBER,
                message=f"Implied growth ({base_growth:.1%}) is above historical median ({hist_growth:.1%}).",
            )
        return DimensionScore(
            name="Growth Reasonableness",
            severity=SEVERITY_NONE,
            rating=DiagnosticRating.GREEN,
            message=f"Implied growth ({base_growth:.1%}) is consistent with history ({hist_growth:.1%}).",
        )

    # ── Dimension 8: Reinvestment support (3-check) ───────────────────────────

    def _score_reinvestment_support(
        self,
        statements: FinancialStatements,
        dcf_result: DCFResult,
    ) -> DimensionScore:
        """
        Does historical capex + ΔNWC support implied FCF growth?

        3-check severity scoring (per CFA recommendation):
        Check 1: Capex intensity — avg capex/revenue over 5 years
        Check 2: Reinvestment consistency — (capex + ΔNWC) vs revenue growth
        Check 3: Growth support — implied growth vs historical revenue growth
                 while reinvestment is flat/declining and margins stretched

        Severity 2 if all 3 checks fail (or one is very severe).
        Severity 1 if 1-2 checks fail.
        """
        rev = statements.revenue.dropna()
        capex = statements.capital_expenditure.dropna()
        nwc = statements.net_working_capital.dropna()
        implied_growth = dcf_result.base.growth_rate

        check1_score = SEVERITY_NONE
        check2_score = SEVERITY_NONE
        check3_score = SEVERITY_NONE
        details = []

        # ── Check 1: Capex intensity
        if len(capex) >= 3 and len(rev) >= 3:
            # Align
            common = capex.index.intersection(rev.index)
            if len(common) >= 3:
                capex_ratio = (capex.loc[common] / rev.loc[common]).mean()
                is_asset_light = capex_ratio < ASSET_LIGHT_CAPEX_THRESHOLD

                if is_asset_light:
                    details.append(
                        f"Asset-light business (capex/revenue: {capex_ratio:.1%}). "
                        "R&D, SBC, and acquisitions may be the real reinvestment channels."
                    )
                elif capex_ratio < 0.02:
                    check1_score = SEVERITY_MILD
                    details.append(f"Very low capex intensity ({capex_ratio:.1%}).")

        # ── Check 2: Reinvestment consistency
        if len(capex) >= 3 and len(nwc) >= 3 and len(rev) >= 3:
            common = capex.index.intersection(nwc.index).intersection(rev.index)
            if len(common) >= 3:
                reinvestment = capex.loc[common] + nwc.loc[common].diff().dropna().abs()
                reinv_trend = reinvestment.pct_change().dropna()
                rev_growth = rev.loc[common].pct_change().dropna()

                if len(reinv_trend) >= 2 and len(rev_growth) >= 2:
                    reinv_declining = (reinv_trend < -0.05).sum() >= 2
                    rev_growing = (rev_growth > 0.05).sum() >= 2
                    if reinv_declining and rev_growing:
                        check2_score = SEVERITY_MILD
                        details.append("Reinvestment declining while revenue growing.")

        # ── Check 3: Growth support
        # Require a positive starting revenue to avoid division-by-zero or
        # complex-number powers; require positive peak margin so the
        # "stretched" comparison is meaningful (a near-zero or negative peak
        # margin makes the 0.90× threshold flag any positive latest margin).
        if len(rev) >= 3 and float(rev.iloc[0]) > 0:
            rev_cagr = (rev.iloc[-1] / rev.iloc[0]) ** (1 / (len(rev) - 1)) - 1
            fcf_margin = statements.fcf_margin.dropna()
            margin_at_peak = float(fcf_margin.max()) if len(fcf_margin) > 0 else 0.0
            margin_latest = float(fcf_margin.iloc[-1]) if len(fcf_margin) > 0 else 0.0
            margin_stretched = (
                margin_at_peak > 0 and margin_latest > margin_at_peak * 0.90
            )

            if (implied_growth > rev_cagr * 1.5
                    and check2_score > SEVERITY_NONE
                    and margin_stretched):
                check3_score = SEVERITY_SEVERE
                details.append(
                    f"Implied FCF growth ({implied_growth:.1%}) >> "
                    f"historical revenue CAGR ({rev_cagr:.1%}) "
                    f"while reinvestment is flat and margins appear stretched."
                )
            elif implied_growth > rev_cagr * 2.0:
                check3_score = SEVERITY_MILD
                details.append(
                    f"Implied FCF growth ({implied_growth:.1%}) significantly "
                    f"exceeds historical revenue CAGR ({rev_cagr:.1%})."
                )

        # ── Aggregate
        total = check1_score + check2_score + check3_score

        if check3_score == SEVERITY_SEVERE or total >= 4:
            return DimensionScore(
                name="Reinvestment Support",
                severity=SEVERITY_SEVERE,
                rating=DiagnosticRating.RED,
                message="Implied growth is not supported by historical reinvestment.",
                detail=" ".join(details) if details else None,
            )
        elif total >= 2:
            return DimensionScore(
                name="Reinvestment Support",
                severity=SEVERITY_MILD,
                rating=DiagnosticRating.AMBER,
                message="Some concerns about reinvestment supporting implied growth.",
                detail=" ".join(details) if details else None,
            )
        return DimensionScore(
            name="Reinvestment Support",
            severity=SEVERITY_NONE,
            rating=DiagnosticRating.GREEN,
            message="Historical reinvestment appears consistent with projected growth.",
            detail=" ".join(details) if details else None,
        )
