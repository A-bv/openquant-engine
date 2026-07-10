"""
OpenQuant — Company suitability checker.

Runs before any DCF analysis. Determines whether the DCF methodology
is appropriate for this company.

This is the honest gate that prevents misleading outputs.
No other free tool does this — most just run the math regardless.

Dependency rule: zero Streamlit imports. Pure Python. Fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from openquant.config import (
    DEFAULT_TERMINAL_GROWTH_RATE,
    EXCLUDED_SECTORS,
    FCF_MARGIN_SD_MILD,
    FCF_MARGIN_SD_SEVERE,
    GROWTH_WINSOR_HIGH,
    GROWTH_WINSOR_LOW,
    MIN_FCF_HISTORY_YEARS,
    MIN_PRICE_HISTORY_YEARS,
    MIN_TRADING_DAYS,
    REVENUE_SWING_MILD,
    REVENUE_SWING_SEVERE,
)
from openquant.data import FinancialStatements

# ── Enums ─────────────────────────────────────────────────────────────────────

class SuitabilityRating(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class SuitabilityCheckName(str, Enum):
    FCF_HISTORY = "FCF history"
    FCF_POSITIVE = "FCF positivity"
    SECTOR = "Sector suitability"
    PRICE_HISTORY = "Price history"
    WACC_GT_GROWTH = "WACC > terminal growth"
    MARGIN_STABILITY = "FCF margin stability"
    REVENUE_STABILITY = "Revenue stability"
    ONE_TIME_EVENTS = "One-time FCF events"


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class SuitabilityCheck:
    """Result of a single suitability check."""
    name: str
    passed: bool
    rating: SuitabilityRating
    message: str
    detail: Optional[str] = None


@dataclass
class SuitabilityReport:
    """
    Complete suitability assessment for one company.

    Used to gate DCF analysis and populate the Red Flag Summary.
    """
    ticker: str
    company_name: str
    overall_rating: SuitabilityRating
    is_suitable: bool                        # True if GREEN or AMBER
    checks: list[SuitabilityCheck] = field(default_factory=list)
    recommendation: str = ""
    alternative_methods: list[str] = field(default_factory=list)

    @property
    def red_flags(self) -> list[SuitabilityCheck]:
        """Checks that failed (RED or AMBER)."""
        return [c for c in self.checks if c.rating != SuitabilityRating.GREEN]

    @property
    def blocking_issues(self) -> list[SuitabilityCheck]:
        """Checks that make DCF completely inappropriate (RED)."""
        return [c for c in self.checks if c.rating == SuitabilityRating.RED]


# ── Suitability checker ───────────────────────────────────────────────────────

class SuitabilityChecker:
    """
    Determines whether DCF valuation is appropriate for a company.

    Runs 8 checks in sequence. Stops at first blocking (RED) issue.
    Returns a SuitabilityReport with plain language explanations.

    Usage:
        checker = SuitabilityChecker()
        report = checker.check(statements, trading_days=1258, sector="Technology")
        if not report.is_suitable:
            # Show blocking message, suggest alternatives
    """

    def check(
        self,
        statements: FinancialStatements,
        trading_days: int,
        sector: str,
        wacc_estimate: Optional[float] = None,
        terminal_growth: float = DEFAULT_TERMINAL_GROWTH_RATE,
    ) -> SuitabilityReport:
        """
        Run all suitability checks for a company.

        Args:
            statements: Fetched financial statements.
            trading_days: Number of available trading days for beta.
            sector: Company sector (SIC description from EDGAR).
            wacc_estimate: Estimated WACC if available. Used for WACC > g check.
            terminal_growth: Terminal growth rate assumption.

        Returns:
            SuitabilityReport with overall rating and per-check details.
        """
        checks = []
        ticker = statements.ticker
        company_name = statements.company_name

        # Run all checks
        checks.append(self._check_sector(sector))
        checks.append(self._check_fcf_history(statements))
        checks.append(self._check_fcf_positivity(statements))
        checks.append(self._check_fcf_cyclicality(statements))
        checks.append(self._check_price_history(trading_days))
        checks.append(self._check_margin_stability(statements))
        checks.append(self._check_revenue_stability(statements))
        checks.append(self._check_one_time_events(statements))

        if wacc_estimate is not None:
            checks.append(
                self._check_wacc_gt_growth(wacc_estimate, terminal_growth)
            )

        # Determine overall rating
        has_red = any(c.rating == SuitabilityRating.RED for c in checks)
        has_amber = any(c.rating == SuitabilityRating.AMBER for c in checks)

        if has_red:
            overall = SuitabilityRating.RED
            is_suitable = False
        elif has_amber:
            overall = SuitabilityRating.AMBER
            is_suitable = True  # Amber = proceed with caution
        else:
            overall = SuitabilityRating.GREEN
            is_suitable = True

        # Build recommendation
        recommendation, alternatives = self._build_recommendation(
            checks, sector, overall
        )

        return SuitabilityReport(
            ticker=ticker,
            company_name=company_name,
            overall_rating=overall,
            is_suitable=is_suitable,
            checks=checks,
            recommendation=recommendation,
            alternative_methods=alternatives,
        )

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_sector(self, sector: str) -> SuitabilityCheck:
        """
        Check 1: Is DCF appropriate for this sector?

        Financial companies (banks, insurers) have fundamentally different
        balance sheet structures. DCF does not apply.
        """
        sector_lower = sector.lower()
        is_financial = any(
            excluded.lower() in sector_lower
            for excluded in EXCLUDED_SECTORS
        )

        if is_financial:
            return SuitabilityCheck(
                name=SuitabilityCheckName.SECTOR,
                passed=False,
                rating=SuitabilityRating.RED,
                message=(
                    f"DCF is not appropriate for financial companies "
                    f"(sector: {sector}). Banks and insurers require "
                    f"different valuation methodologies."
                ),
                detail=(
                    "Financial companies have fundamentally different balance "
                    "sheet structures where debt is an input to the business "
                    "model, not just a source of financing. Free cash flow "
                    "cannot be computed meaningfully."
                ),
            )

        return SuitabilityCheck(
            name=SuitabilityCheckName.SECTOR,
            passed=True,
            rating=SuitabilityRating.GREEN,
            message=f"Sector '{sector}' is suitable for DCF analysis.",
        )

    def _check_fcf_history(
        self, statements: FinancialStatements
    ) -> SuitabilityCheck:
        """
        Check 2: Does the company have sufficient FCF history?

        Need at least MIN_FCF_HISTORY_YEARS of data for
        meaningful trend analysis.
        """
        fcf_clean = statements.free_cash_flow.dropna()
        years_available = len(fcf_clean)

        if years_available < MIN_FCF_HISTORY_YEARS:
            return SuitabilityCheck(
                name=SuitabilityCheckName.FCF_HISTORY,
                passed=False,
                rating=SuitabilityRating.RED,
                message=(
                    f"Only {years_available} year(s) of FCF history available. "
                    f"Need at least {MIN_FCF_HISTORY_YEARS} years for DCF analysis."
                ),
                detail=(
                    "Insufficient history means growth rate estimates are "
                    "unreliable and the model cannot identify trends."
                ),
            )

        return SuitabilityCheck(
            name=SuitabilityCheckName.FCF_HISTORY,
            passed=True,
            rating=SuitabilityRating.GREEN,
            message=f"{years_available} years of FCF history available.",
        )

    def _check_fcf_positivity(
        self, statements: FinancialStatements
    ) -> SuitabilityCheck:
        """
        Check 3: Has the company generated positive FCF consistently?

        Companies with mostly negative FCF cannot be valued with DCF.
        """
        fcf_clean = statements.free_cash_flow.dropna()
        if len(fcf_clean) == 0:
            return SuitabilityCheck(
                name=SuitabilityCheckName.FCF_POSITIVE,
                passed=False,
                rating=SuitabilityRating.RED,
                message="No FCF data available.",
            )

        n_negative = (fcf_clean < 0).sum()
        n_total = len(fcf_clean)
        pct_negative = n_negative / n_total

        if pct_negative > 0.5:
            return SuitabilityCheck(
                name=SuitabilityCheckName.FCF_POSITIVE,
                passed=False,
                rating=SuitabilityRating.RED,
                message=(
                    f"FCF was negative in {n_negative} of {n_total} years "
                    f"({pct_negative:.0%}). DCF requires consistent positive "
                    f"cash flows."
                ),
                detail=(
                    "Companies that consistently burn cash cannot be valued "
                    "by discounting future cash flows — there are no positive "
                    "flows to discount. Consider EV/Sales or comparable "
                    "transactions instead."
                ),
            )

        if n_negative > 0:
            return SuitabilityCheck(
                name=SuitabilityCheckName.FCF_POSITIVE,
                passed=True,
                rating=SuitabilityRating.AMBER,
                message=(
                    f"FCF was negative in {n_negative} of {n_total} years. "
                    f"Proceed with caution — results may be sensitive to "
                    f"the loss years."
                ),
            )

        return SuitabilityCheck(
            name=SuitabilityCheckName.FCF_POSITIVE,
            passed=True,
            rating=SuitabilityRating.GREEN,
            message=f"FCF was positive in all {n_total} years.",
        )

    def _check_fcf_cyclicality(
        self, statements: FinancialStatements
    ) -> SuitabilityCheck:
        """
        Check 3b: Is FCF trend too cyclical / declining for meaningful projection?

        Catches commodity companies (oil, mining) that pass the positivity check
        yet have a strongly negative median FCF growth trend.
        """
        fcf_clean = statements.free_cash_flow.dropna()
        if len(fcf_clean) < 4:
            return SuitabilityCheck(
                name="FCF Cyclicality",
                passed=True,
                rating=SuitabilityRating.GREEN,
                message="Insufficient history for cyclicality check.",
            )

        # Percentage growth is only meaningful when both endpoints are
        # positive — sign-crossing years (e.g. -3B → +1B) produce -133%
        # outputs that flip the cyclicality verdict. Restrict to positive
        # transitions; if none survive, treat as too noisy to judge.
        yoy_raw = fcf_clean.pct_change().dropna()
        prior_fcf = fcf_clean.shift(1)
        both_positive = (fcf_clean > 0) & (prior_fcf > 0)
        yoy = yoy_raw[both_positive.reindex(yoy_raw.index, fill_value=False)]
        if len(yoy) < 3:
            return SuitabilityCheck(
                name="FCF Cyclicality",
                passed=True,
                rating=SuitabilityRating.GREEN,
                message=(
                    "Insufficient positive-to-positive FCF transitions "
                    "for cyclicality check."
                ),
            )
        from openquant.common import winsorize_series
        if len(yoy) >= 4:
            yoy = winsorize_series(yoy, GROWTH_WINSOR_LOW, GROWTH_WINSOR_HIGH)
        median_g = float(yoy.median())

        if median_g < -0.10:
            return SuitabilityCheck(
                name="FCF Cyclicality",
                passed=False,
                rating=SuitabilityRating.RED,
                message=(
                    f"FCF has declined at {median_g:.1%}/yr median over the past "
                    f"{len(fcf_clean)} years. This suggests highly cyclical or "
                    f"commodity-driven cash flows. DCF projections from this base "
                    f"will be misleading."
                ),
                detail=(
                    "Highly cyclical companies require normalised through-cycle "
                    "earnings, not recent FCF trends. Consider EV/EBITDA on "
                    "normalised earnings instead."
                ),
            )

        return SuitabilityCheck(
            name="FCF Cyclicality",
            passed=True,
            rating=SuitabilityRating.GREEN,
            message=f"FCF trend is acceptable for DCF (median growth: {median_g:.1%}/yr).",
        )

    def _check_price_history(self, trading_days: int) -> SuitabilityCheck:
        """
        Check 4: Is there sufficient price history for beta computation?
        """
        min_days = MIN_TRADING_DAYS * MIN_PRICE_HISTORY_YEARS

        if trading_days < min_days:
            return SuitabilityCheck(
                name=SuitabilityCheckName.PRICE_HISTORY,
                passed=False,
                rating=SuitabilityRating.AMBER,
                message=(
                    f"Only {trading_days} trading days available. "
                    f"Beta estimate may be unreliable "
                    f"(recommend {min_days}+ days)."
                ),
                detail=(
                    "Short price history produces a noisy beta estimate "
                    "with wide confidence intervals. The WACC will be "
                    "less reliable."
                ),
            )

        return SuitabilityCheck(
            name=SuitabilityCheckName.PRICE_HISTORY,
            passed=True,
            rating=SuitabilityRating.GREEN,
            message=f"{trading_days} trading days available for beta computation.",
        )

    def _check_margin_stability(
        self, statements: FinancialStatements
    ) -> SuitabilityCheck:
        """
        Check 5: Are FCF margins stable?

        Highly volatile margins make projections unreliable.
        """
        margin_clean = statements.fcf_margin.dropna()
        if len(margin_clean) < 3:
            return SuitabilityCheck(
                name=SuitabilityCheckName.MARGIN_STABILITY,
                passed=True,
                rating=SuitabilityRating.AMBER,
                message="Insufficient margin history for stability assessment.",
            )

        margin_sd = float(margin_clean.std(ddof=1))

        # NaN comparisons always return False, which would silently fall
        # through to GREEN even though the underlying data is corrupt
        # (e.g. Inf margins from zero-revenue years poisoning std).
        if not np.isfinite(margin_sd):
            return SuitabilityCheck(
                name=SuitabilityCheckName.MARGIN_STABILITY,
                passed=False,
                rating=SuitabilityRating.RED,
                message=(
                    "FCF margin standard deviation could not be computed "
                    "(likely Inf/NaN margins from zero-revenue years). "
                    "Margin stability cannot be assessed."
                ),
            )

        if margin_sd > FCF_MARGIN_SD_SEVERE:
            return SuitabilityCheck(
                name=SuitabilityCheckName.MARGIN_STABILITY,
                passed=False,
                rating=SuitabilityRating.AMBER,
                message=(
                    f"FCF margin has high volatility (SD: {margin_sd:.1%}). "
                    f"Projections based on average margins may be misleading."
                ),
                detail=(
                    f"FCF margin ranged from {margin_clean.min():.1%} to "
                    f"{margin_clean.max():.1%}. "
                    f"Consider normalising margins before projecting."
                ),
            )

        if margin_sd > FCF_MARGIN_SD_MILD:
            return SuitabilityCheck(
                name=SuitabilityCheckName.MARGIN_STABILITY,
                passed=True,
                rating=SuitabilityRating.AMBER,
                message=(
                    f"Moderate FCF margin variability (SD: {margin_sd:.1%}). "
                    f"Review the conservative scenario carefully."
                ),
            )

        return SuitabilityCheck(
            name=SuitabilityCheckName.MARGIN_STABILITY,
            passed=True,
            rating=SuitabilityRating.GREEN,
            message=f"FCF margins are stable (SD: {margin_sd:.1%}).",
        )

    def _check_revenue_stability(
        self, statements: FinancialStatements
    ) -> SuitabilityCheck:
        """
        Check 6: Is revenue relatively stable (not highly cyclical)?

        Highly cyclical revenue makes FCF projections unreliable.
        """
        rev_clean = statements.revenue.dropna()
        if len(rev_clean) < 3:
            return SuitabilityCheck(
                name=SuitabilityCheckName.REVENUE_STABILITY,
                passed=True,
                rating=SuitabilityRating.AMBER,
                message="Insufficient revenue history for cyclicality assessment.",
            )

        # Distinguish cyclicality (up-down-up) from growth (consistently up)
        # Use year-over-year changes to detect actual declines
        yoy_changes = rev_clean.pct_change().dropna()
        n_declines = (yoy_changes < -0.05).sum()   # >5% decline = meaningful
        max_decline = float(yoy_changes[yoy_changes < 0].min()) if (yoy_changes < 0).any() else 0.0

        rev_max = float(rev_clean.max())
        rev_min = float(rev_clean.min())

        if rev_max == 0:
            return SuitabilityCheck(
                name=SuitabilityCheckName.REVENUE_STABILITY,
                passed=False,
                rating=SuitabilityRating.RED,
                message="Revenue data appears invalid (maximum is zero).",
            )

        if n_declines >= 2 or max_decline < -REVENUE_SWING_SEVERE:
            return SuitabilityCheck(
                name=SuitabilityCheckName.REVENUE_STABILITY,
                passed=False,
                rating=SuitabilityRating.AMBER,
                message=(
                    f"Revenue shows cyclical behaviour — "
                    f"{n_declines} year(s) with >5% decline detected. "
                    f"This company may be significantly affected by economic cycles."
                ),
                detail=(
                    f"Worst annual decline: {max_decline:.1%}. "
                    f"Revenue ranged from {rev_min/1e9:.1f}B to {rev_max/1e9:.1f}B. "
                    f"Consider using normalised (through-cycle) margins."
                ),
            )

        if n_declines == 1 or max_decline < -REVENUE_SWING_MILD:
            return SuitabilityCheck(
                name=SuitabilityCheckName.REVENUE_STABILITY,
                passed=True,
                rating=SuitabilityRating.AMBER,
                message=(
                    f"Minor revenue decline detected (worst: {max_decline:.1%}). "
                    f"Base case growth assumptions should be treated with caution."
                ),
            )

        return SuitabilityCheck(
            name=SuitabilityCheckName.REVENUE_STABILITY,
            passed=True,
            rating=SuitabilityRating.GREEN,
            message="Revenue shows consistent growth with no significant declines.",
        )

    def _check_one_time_events(
        self, statements: FinancialStatements
    ) -> SuitabilityCheck:
        """
        Check 7: Are there abnormal one-time FCF events?

        Detects years where FCF deviates dramatically from the trend —
        likely due to acquisitions, disposals, or restructuring charges.
        """
        fcf_clean = statements.free_cash_flow.dropna()
        if len(fcf_clean) < 4:
            return SuitabilityCheck(
                name=SuitabilityCheckName.ONE_TIME_EVENTS,
                passed=True,
                rating=SuitabilityRating.GREEN,
                message="Insufficient history to detect one-time events.",
            )

        # Z-score based outlier detection
        fcf_mean = float(fcf_clean.mean())
        fcf_std = float(fcf_clean.std(ddof=1))

        if fcf_std == 0:
            return SuitabilityCheck(
                name=SuitabilityCheckName.ONE_TIME_EVENTS,
                passed=True,
                rating=SuitabilityRating.GREEN,
                message="No outliers detected in FCF series.",
            )

        z_scores = ((fcf_clean - fcf_mean) / fcf_std).abs()
        outliers = fcf_clean[z_scores > 2.5]

        if len(outliers) > 0:
            outlier_years = [
                str(idx.year) if hasattr(idx, "year") else str(idx)
                for idx in outliers.index
            ]
            return SuitabilityCheck(
                name=SuitabilityCheckName.ONE_TIME_EVENTS,
                passed=True,
                rating=SuitabilityRating.AMBER,
                message=(
                    f"Potential one-time FCF events detected in: "
                    f"{', '.join(outlier_years)}. "
                    f"These years may distort growth rate estimates."
                ),
                detail=(
                    "One-time events (acquisitions, disposals, restructuring) "
                    "can cause large FCF swings that should not be projected "
                    "forward. The winsorized median growth rate partially "
                    "mitigates this."
                ),
            )

        return SuitabilityCheck(
            name=SuitabilityCheckName.ONE_TIME_EVENTS,
            passed=True,
            rating=SuitabilityRating.GREEN,
            message="No significant one-time FCF events detected.",
        )

    def _check_wacc_gt_growth(
        self,
        wacc: float,
        terminal_growth: float,
    ) -> SuitabilityCheck:
        """
        Check 8: Is WACC strictly greater than terminal growth rate?

        If WACC <= g, the terminal value formula diverges to infinity.
        This is enforced as a hard constraint.
        """
        if wacc <= terminal_growth:
            return SuitabilityCheck(
                name=SuitabilityCheckName.WACC_GT_GROWTH,
                passed=False,
                rating=SuitabilityRating.RED,
                message=(
                    f"WACC ({wacc:.1%}) must be greater than terminal growth "
                    f"rate ({terminal_growth:.1%}). "
                    f"The terminal value formula is undefined when WACC ≤ g."
                ),
                detail=(
                    "The growing perpetuity formula TV = FCF(1+g)/(WACC-g) "
                    "requires WACC > g. When this condition is violated, "
                    "terminal value becomes infinite or negative. "
                    "Reduce the terminal growth rate assumption."
                ),
            )

        buffer = wacc - terminal_growth
        if buffer < 0.02:
            return SuitabilityCheck(
                name=SuitabilityCheckName.WACC_GT_GROWTH,
                passed=True,
                rating=SuitabilityRating.AMBER,
                message=(
                    f"WACC ({wacc:.1%}) is only {buffer:.1%} above terminal "
                    f"growth ({terminal_growth:.1%}). "
                    f"Terminal value will be very sensitive to small changes "
                    f"in either assumption."
                ),
            )

        return SuitabilityCheck(
            name=SuitabilityCheckName.WACC_GT_GROWTH,
            passed=True,
            rating=SuitabilityRating.GREEN,
            message=(
                f"WACC ({wacc:.1%}) > terminal growth ({terminal_growth:.1%}). "
                f"Terminal value formula is valid."
            ),
        )

    # ── Recommendation builder ────────────────────────────────────────────────

    def _build_recommendation(
        self,
        checks: list[SuitabilityCheck],
        sector: str,
        overall: SuitabilityRating,
    ) -> tuple[str, list[str]]:
        """
        Build a plain-language recommendation based on check results.

        Returns:
            Tuple of (recommendation_text, list_of_alternative_methods).
        """
        alternatives = []
        sector_lower = sector.lower()

        if overall == SuitabilityRating.RED:
            # Find the blocking issue
            blocking = [c for c in checks if c.rating == SuitabilityRating.RED]
            primary_block = blocking[0] if blocking else None

            if primary_block and SuitabilityCheckName.SECTOR in primary_block.name:
                if "bank" in sector_lower or "financial" in sector_lower:
                    alternatives = ["Price-to-Book (P/B)", "Return on Equity (ROE) analysis", "Dividend Discount Model"]
                    rec = (
                        "DCF is not appropriate for this financial company. "
                        "Banks and insurers are better valued using P/B ratio, "
                        "ROE-based models, or Dividend Discount Models."
                    )
                elif "insurance" in sector_lower:
                    alternatives = ["Price-to-Book (P/B)", "Combined ratio analysis", "Embedded Value"]
                    rec = (
                        "DCF is not appropriate for insurance companies. "
                        "Consider Price-to-Book, combined ratio analysis, "
                        "or embedded value methodologies."
                    )
                else:
                    alternatives = ["EV/EBITDA", "P/E ratio", "Comparable transactions"]
                    rec = (
                        "DCF is not suitable for this company in its current sector. "
                        "Consider relative valuation methods instead."
                    )
            elif primary_block and primary_block.name == "FCF Cyclicality":
                alternatives = [
                    "EV/EBITDA on normalised earnings",
                    "Price/Normalised Cash Flow",
                    "Sum-of-parts valuation",
                ]
                rec = (
                    "DCF is not suitable — FCF is too cyclical or declining to project reliably. "
                    "Commodity and cyclical companies are better valued using normalised "
                    "earnings multiples over a full business cycle."
                )
            elif primary_block and "FCF" in primary_block.name:
                alternatives = ["EV/Revenue", "EV/Sales", "Comparable transactions"]
                rec = (
                    "DCF is not suitable — insufficient positive FCF history. "
                    "For pre-revenue or early-stage companies, consider "
                    "revenue multiples or comparable transaction analysis."
                )
            else:
                alternatives = ["EV/EBITDA", "P/E ratio"]
                rec = (
                    "DCF cannot be reliably applied to this company. "
                    f"Issue: {primary_block.message if primary_block else 'See checks above.'}"
                )

        elif overall == SuitabilityRating.AMBER:
            amber_issues = [c for c in checks if c.rating == SuitabilityRating.AMBER]
            issue_names = [c.name for c in amber_issues]
            rec = (
                "DCF can be applied with caution. "
                f"Pay particular attention to: {', '.join(issue_names)}. "
                "The conservative scenario is recommended as your base case."
            )

        else:
            rec = (
                "DCF is well-suited for this company. "
                "Stable cash flows and sufficient history support reliable analysis."
            )

        return rec, alternatives
