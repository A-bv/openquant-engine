"""
OpenQuant — Model audit trail.

Collapsible panel in the UI that shows exactly how
every analysis was produced. Makes the tool reproducible
and professional.

Contains:
- Data source used (EDGAR / yfinance)
- Timestamp of data fetch
- All key assumptions used
- Formulas applied (list with expandable panels)
- Warnings triggered
- OpenQuant version

Dependency rule: zero Streamlit imports. Pure Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from openquant.config import DEFAULT_TERMINAL_GROWTH_RATE
from openquant.data import FinancialStatements
from openquant.valuation.fcf import FCFAnalysis
from openquant.valuation.wacc import WACCResult
from openquant.valuation.dcf import DCFResult
from openquant.valuation.reverse_dcf import ReverseDCFResult
from openquant.valuation.assumption_diagnostic import AssumptionDiagnostic
from openquant.valuation.suitability import SuitabilityReport


@dataclass
class AuditTrail:
    """
    Complete audit trail for one valuation analysis.

    Always available via collapsible panel in UI.
    Makes every analysis reproducible and traceable.
    """
    ticker: str
    company_name: str
    generated_at: datetime

    # Data provenance
    financial_data_source: str          # "SEC EDGAR" or "FMP"
    price_data_source: str              # "yfinance"
    financial_data_fetched_at: datetime
    cik: Optional[str]                  # SEC CIK for EDGAR

    # Key assumptions used
    risk_free_rate: float
    market_risk_premium: float
    beta_used: float
    cost_of_equity: float
    cost_of_debt_pretax: float
    wacc: float
    terminal_growth_rate: float
    forecast_horizon: int
    tax_rate_used: float

    # FCF inputs
    base_fcf: float
    fcf_growth_conservative: float
    fcf_growth_base: float
    fcf_growth_optimistic: float
    historical_median_growth: float

    # Outputs summary
    dcf_iv_conservative: float
    dcf_iv_base: float
    dcf_iv_optimistic: float
    implied_growth_rate: Optional[float]    # From reverse DCF
    terminal_value_pct: float

    # Warnings triggered
    all_warnings: list[str]

    # Suitability
    suitability_rating: str
    diagnostic_rating: str

    # Version
    openquant_version: str = "1.0.0"

    def to_display_dict(self) -> dict:
        """
        Convert to human-readable display dictionary.
        Used by UI to render the audit panel.
        """
        return {
            "Generated": self.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
            "Version": f"OpenQuant {self.openquant_version}",
            "Company": f"{self.company_name} ({self.ticker})",
            "CIK": self.cik or "N/A",
            "Financial Data": self.financial_data_source,
            "Price Data": self.price_data_source,
            "Data Fetched": self.financial_data_fetched_at.strftime("%Y-%m-%d"),
            "─── Assumptions ───": "",
            "Risk-Free Rate": f"{self.risk_free_rate:.2%}",
            "Market Risk Premium": f"{self.market_risk_premium:.2%}",
            "Beta": f"{self.beta_used:.3f}",
            "Cost of Equity (CAPM)": f"{self.cost_of_equity:.2%}",
            "Cost of Debt (Pre-tax)": f"{self.cost_of_debt_pretax:.2%}",
            "WACC": f"{self.wacc:.2%}",
            "Terminal Growth Rate": f"{self.terminal_growth_rate:.2%}",
            "Forecast Horizon": f"{self.forecast_horizon} years",
            "Effective Tax Rate": f"{self.tax_rate_used:.2%}",
            "─── FCF Inputs ───": "",
            "Base FCF": f"${self.base_fcf/1e9:.2f}B",
            "Conservative Growth": f"{self.fcf_growth_conservative:.1%}",
            "Base Growth": f"{self.fcf_growth_base:.1%}",
            "Optimistic Growth": f"{self.fcf_growth_optimistic:.1%}",
            "Historical Median Growth": f"{self.historical_median_growth:.1%}",
            "─── Outputs ───": "",
            "IV (Conservative)": f"${self.dcf_iv_conservative:.2f}",
            "IV (Base)": f"${self.dcf_iv_base:.2f}",
            "IV (Optimistic)": f"${self.dcf_iv_optimistic:.2f}",
            "Implied Growth (Reverse DCF)": (
                f"{self.implied_growth_rate:.1%}"
                if self.implied_growth_rate is not None
                else "N/A"
            ),
            "Terminal Value %": f"{self.terminal_value_pct:.0%}",
            "─── Quality ───": "",
            "Suitability": self.suitability_rating,
            "Assumption Diagnostic": self.diagnostic_rating,
            "Warnings": f"{len(self.all_warnings)} triggered",
        }

    @property
    def formula_references(self) -> list[dict]:
        """
        List of formulas used — for expandable formula panels in UI.
        Each entry: {name, formula, source, description}
        """
        return [
            {
                "name": "Beta",
                "formula": "β = Cov(r_stock, r_market) / Var(r_market)",
                "source": "EPFL Formula Sheet",
                "description": (
                    "Measures sensitivity of stock returns to market movements. "
                    f"Computed from {self.forecast_horizon * 252} daily returns "
                    "vs S&P 500."
                ),
            },
            {
                "name": "Cost of Equity (CAPM)",
                "formula": "r_E = r_f + β × (r_m − r_f)",
                "source": "EPFL Formula Sheet — CAPM",
                "description": (
                    f"r_f={self.risk_free_rate:.2%}, "
                    f"β={self.beta_used:.3f}, "
                    f"MRP={self.market_risk_premium:.2%} → "
                    f"r_E={self.cost_of_equity:.2%}"
                ),
            },
            {
                "name": "WACC",
                "formula": "WACC = (E/V) × r_E + (D/V) × r_D × (1 − T)",
                "source": "EPFL Formula Sheet",
                "description": (
                    f"Discount rate = {self.wacc:.2%}. "
                    "Combines cost of equity and after-tax cost of debt "
                    "weighted by capital structure."
                ),
            },
            {
                "name": "Free Cash Flow",
                "formula": "FCF = EBIT×(1−T) + D&A − CapEx − ΔNWC",
                "source": "EPFL Exam 1 Problem 2",
                "description": (
                    f"Latest FCF: ${self.base_fcf/1e9:.2f}B. "
                    "Represents cash generated by the business "
                    "available to all capital providers."
                ),
            },
            {
                "name": "Terminal Value",
                "formula": "TV = FCF_n × (1 + g) / (WACC − g)",
                "source": "EPFL Formula Sheet — Growing Perpetuity",
                "description": (
                    f"Terminal growth: {self.terminal_growth_rate:.2%}. "
                    f"Terminal value = {self.terminal_value_pct:.0%} of EV. "
                    "Requires WACC > g (enforced)."
                ),
            },
            {
                "name": "Enterprise Value (DCF)",
                "formula": "EV = Σ FCF_t/(1+WACC)^t + TV/(1+WACC)^n",
                "source": "EPFL Formula Sheet — NPV",
                "description": (
                    f"Sum of PV of {self.forecast_horizon}-year FCF projections "
                    "plus PV of terminal value."
                ),
            },
            {
                "name": "Intrinsic Value per Share",
                "formula": "IV = (EV − Net Debt) / Diluted Shares",
                "source": "Standard equity bridge",
                "description": (
                    f"Base case IV: ${self.dcf_iv_base:.2f}. "
                    "Enterprise value minus net debt gives equity value, "
                    "divided by diluted shares outstanding."
                ),
            },
        ]


_SOURCE_LABELS = {
    "edgar": "SEC EDGAR",
    "fmp": "Financial Modeling Prep",
}


def _format_source(source: str) -> str:
    """Map a raw source identifier to its display label, falling back to the
    raw value so an unknown or future source is not silently misattributed."""
    if not source:
        return "Unknown"
    return _SOURCE_LABELS.get(source.lower(), source)


class AuditTrailBuilder:
    """Assembles the audit trail from all analysis components."""

    def build(
        self,
        statements: FinancialStatements,
        fcf_analysis: FCFAnalysis,
        wacc_result: WACCResult,
        dcf_result: DCFResult,
        suitability: SuitabilityReport,
        diagnostic: AssumptionDiagnostic,
        reverse_result: Optional[ReverseDCFResult] = None,
        terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH_RATE,
    ) -> AuditTrail:
        """
        Build complete audit trail.

        Args:
            statements: Financial statements.
            fcf_analysis: FCF analysis.
            wacc_result: WACC computation.
            dcf_result: Forward DCF result.
            suitability: Suitability report.
            diagnostic: Assumption diagnostic.
            reverse_result: Reverse DCF result (optional).
            terminal_growth_rate: Terminal growth used.

        Returns:
            AuditTrail ready for display.
        """
        # Collect all warnings
        all_warnings = []
        all_warnings.extend(wacc_result.warnings)
        all_warnings.extend(dcf_result.warnings)
        all_warnings.extend(statements.data_warnings)
        if reverse_result and hasattr(reverse_result, 'warnings'):
            all_warnings.extend(reverse_result.warnings)

        # Deduplicate
        seen = set()
        unique_warnings = []
        for w in all_warnings:
            if w not in seen:
                seen.add(w)
                unique_warnings.append(w)

        implied_growth = None
        if reverse_result and hasattr(reverse_result, 'implied_growth_rate'):
            implied_growth = reverse_result.implied_growth_rate

        return AuditTrail(
            ticker=statements.ticker,
            company_name=statements.company_name,
            generated_at=datetime.now(),
            financial_data_source=_format_source(statements.source),
            price_data_source="yfinance",
            financial_data_fetched_at=statements.fetched_at,
            cik=statements.cik,
            risk_free_rate=wacc_result.risk_free_rate,
            market_risk_premium=wacc_result.market_risk_premium,
            beta_used=wacc_result.beta,
            cost_of_equity=wacc_result.cost_of_equity,
            cost_of_debt_pretax=wacc_result.cost_of_debt_pretax,
            wacc=wacc_result.wacc,
            terminal_growth_rate=terminal_growth_rate,
            forecast_horizon=dcf_result.forecast_horizon,
            tax_rate_used=wacc_result.tax_rate,
            base_fcf=dcf_result.base_fcf,
            fcf_growth_conservative=fcf_analysis.growth_conservative,
            fcf_growth_base=fcf_analysis.growth_base,
            fcf_growth_optimistic=fcf_analysis.growth_optimistic,
            historical_median_growth=fcf_analysis.median_growth_rate,
            dcf_iv_conservative=dcf_result.conservative.intrinsic_value_per_share,
            dcf_iv_base=dcf_result.base.intrinsic_value_per_share,
            dcf_iv_optimistic=dcf_result.optimistic.intrinsic_value_per_share,
            implied_growth_rate=implied_growth,
            terminal_value_pct=dcf_result.base.terminal_value_pct,
            all_warnings=unique_warnings,
            suitability_rating=suitability.overall_rating.value.upper(),
            diagnostic_rating=diagnostic.overall_rating.value.upper(),
        )
