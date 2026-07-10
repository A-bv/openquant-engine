"""
OpenQuant — Red Flag Summary generator.

Generates 3-5 plain-language bullet points shown at the TOP
of every valuation output — before any numbers.

This ensures users see the most important caveats FIRST,
not buried in footnotes or expandable sections.

The red flags are automatically generated from:
- Assumption Diagnostic results
- Suitability report warnings
- DCF scenario outputs
- Reverse DCF result

Dependency rule: zero Streamlit imports. Pure Python. Fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from openquant.valuation.assumption_diagnostic import AssumptionDiagnostic, DiagnosticRating
from openquant.valuation.dcf import DCFResult
from openquant.valuation.reverse_dcf import ReverseDCFResult
from openquant.valuation.suitability import SuitabilityReport


@dataclass
class RedFlagSummary:
    """
    3-5 plain-language red flags shown before valuation numbers.

    Each flag is a single sentence the user can read in 5 seconds.
    """
    ticker: str
    flags: list[str]                 # 0-5 flags, ordered by importance
    has_blocking_issues: bool        # True if analysis should not proceed
    overall_confidence: str          # "High", "Moderate", "Low", "Very Low"

    @property
    def flag_count(self) -> int:
        return len(self.flags)

    @property
    def is_clean(self) -> bool:
        """True if no flags — analysis is clean."""
        return len(self.flags) == 0


class RedFlagBuilder:
    """
    Builds the red flag summary from all available analysis results.

    Priority order:
    1. Blocking suitability issues (DCF not appropriate)
    2. Severe diagnostic dimensions
    3. Terminal value dominance
    4. High implied growth
    5. Data quality warnings
    """

    MAX_FLAGS = 5

    def build(
        self,
        ticker: str,
        diagnostic: AssumptionDiagnostic,
        suitability: SuitabilityReport,
        dcf_result: Optional[DCFResult] = None,
        reverse_result: Optional[ReverseDCFResult] = None,
    ) -> RedFlagSummary:
        """
        Build red flag summary from all analysis components.

        Args:
            ticker: Stock ticker symbol.
            diagnostic: Assumption diagnostic result.
            suitability: Suitability report.
            dcf_result: Forward DCF result (optional).
            reverse_result: Reverse DCF result (optional).

        Returns:
            RedFlagSummary with ordered flags.
        """
        flags: list[str] = []
        # Used for confidence computation downstream; independent from the
        # decision to suppress RED diagnostic dimensions (we no longer do).
        has_blocking = bool(suitability.blocking_issues)

        # ── Priority 1: Blocking suitability issues
        for issue in suitability.blocking_issues:
            if len(flags) < self.MAX_FLAGS:
                flags.append(f"⛔ {issue.message}")

        # ── Priority 2: Severe diagnostic dimensions (RED). Surface these
        # alongside blocking issues — a user who acknowledges the block still
        # needs to see the other RED dimensions to understand all the reasons
        # the model is unreliable.
        for dim in diagnostic.red_dimensions:
            if len(flags) < self.MAX_FLAGS:
                flags.append(f"🔴 {dim.name}: {dim.message}")

        # ── Priority 3: Terminal value dominance
        if dcf_result is not None and len(flags) < self.MAX_FLAGS:
            tv_pct = dcf_result.base.terminal_value_pct
            if tv_pct > 0.75:
                flags.append(
                    f"⚠ Terminal value = {tv_pct:.0%} of total — "
                    f"valuation is highly sensitive to the long-run growth assumption."
                )
            elif tv_pct > 0.60 and len(flags) < self.MAX_FLAGS:
                flags.append(
                    f"⚠ Terminal value = {tv_pct:.0%} of total — "
                    f"review the terminal growth rate carefully."
                )

        # ── Priority 4: High implied growth
        if reverse_result is not None and len(flags) < self.MAX_FLAGS:
            if isinstance(reverse_result, ReverseDCFResult):
                implied = reverse_result.implied_growth_rate
                hist = reverse_result.historical_median_growth
                if implied > hist * 2.0 and implied > 0.10:
                    flags.append(
                        f"⚠ Market implies {implied:.1%} FCF growth vs "
                        f"{hist:.1%} historical — above-average performance expected."
                    )

        # ── Priority 5: Amber diagnostic dimensions
        for dim in diagnostic.amber_dimensions:
            if len(flags) < self.MAX_FLAGS:
                flags.append(f"🟡 {dim.name}: {dim.message}")

        # ── Priority 6: Beta instability
        if len(flags) < self.MAX_FLAGS:
            beta_dim = next(
                (d for d in diagnostic.dimensions if d.name == "Beta Reliability"),
                None,
            )
            if beta_dim and beta_dim.rating != DiagnosticRating.GREEN:
                if not any("Beta" in f for f in flags):
                    flags.append(f"🟡 {beta_dim.message}")

        # ── Determine overall confidence
        overall_confidence = self._compute_confidence(
            diagnostic, suitability, has_blocking
        )

        return RedFlagSummary(
            ticker=ticker,
            flags=flags[:self.MAX_FLAGS],
            has_blocking_issues=has_blocking,
            overall_confidence=overall_confidence,
        )

    def _compute_confidence(
        self,
        diagnostic: AssumptionDiagnostic,
        suitability: SuitabilityReport,
        has_blocking: bool,
    ) -> str:
        """Determine overall confidence level."""
        if has_blocking or not suitability.is_suitable:
            return "Very Low"
        if diagnostic.overall_rating == DiagnosticRating.RED:
            return "Low"
        if diagnostic.overall_rating == DiagnosticRating.AMBER:
            return "Moderate"
        return "High"
