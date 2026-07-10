"""
OpenQuant — Forward DCF valuation engine.

Implements directly from the EPFL formula sheet:

    Terminal Value = FCF_n × (1 + g) / (WACC − g)
    [Growing perpetuity — requires WACC > g]

    Enterprise Value = Σ FCF_t / (1+WACC)^t + TV / (1+WACC)^n

    Equity Value = Enterprise Value − Net Debt

    Intrinsic Value per Share = Equity Value / Diluted Shares Outstanding

Ground truth fixture (EPFL Exam 1, Problem 2):
    FCF = [-24M, 8.4M, 9.15M, 11.1M, 14.85M]
    WACC = 20%
    NPV = Σ FCF_t / (1.20)^t

Three scenarios always computed:
    Conservative: median_growth × 0.7, WACC + 1%
    Base:         median_growth,        WACC
    Optimistic:   median_growth × 1.3, WACC − 1%

Dependency rule: zero Streamlit imports. Pure Python. Fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from openquant.config import (
    DEFAULT_TERMINAL_GROWTH_RATE,
    FORECAST_HORIZON_YEARS,
    MAX_TERMINAL_GROWTH_RATE,
    SCENARIO_CONSERVATIVE_WACC_ADD,
    SCENARIO_OPTIMISTIC_WACC_SUB,
    TERMINAL_GROWTH_MATURE_WARNING,
    TERMINAL_VALUE_SEVERE_THRESHOLD,
    TERMINAL_VALUE_WARNING_THRESHOLD,
)
from openquant.valuation.fcf import FCFAnalysis
from openquant.valuation.wacc import WACCResult

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class DCFScenario:
    """
    Single DCF scenario result.

    Contains all components needed for the valuation output:
    projected FCFs, terminal value, enterprise value,
    equity value, and intrinsic value per share.
    """
    scenario_name: str                   # "Conservative", "Base", "Optimistic"
    growth_rate: float                   # FCF growth rate assumed
    wacc: float                          # Discount rate used

    # Projected FCFs — year 1 to n
    projected_fcf: pd.Series             # Index: 1..n

    # Present values
    pv_fcfs: pd.Series                   # PV of each projected FCF
    pv_fcfs_total: float                 # Sum of PV of FCFs

    # Terminal value
    terminal_fcf: float                  # FCF in final forecast year
    terminal_value: float                # TV = FCF_n × (1+g) / (WACC-g)
    pv_terminal_value: float             # TV / (1+WACC)^n
    terminal_value_pct: float            # TV as % of enterprise value

    # Valuation
    enterprise_value: float              # PV FCFs + PV TV
    net_debt: float                      # Total debt - cash
    equity_value: float                  # EV - net debt
    shares_outstanding: float
    intrinsic_value_per_share: float     # Equity value / shares

    # Current price context
    current_price: float
    margin_of_safety: float              # (IV - Price) / IV

    # Warnings
    warnings: list[str] = field(default_factory=list)

    @property
    def upside_downside(self) -> float:
        """% upside (positive) or downside (negative) vs current price."""
        if self.current_price <= 0:
            return 0.0
        return (self.intrinsic_value_per_share - self.current_price) / self.current_price

    @property
    def is_overvalued(self) -> bool:
        return self.intrinsic_value_per_share < self.current_price

    @property
    def terminal_value_warning(self) -> bool:
        return self.terminal_value_pct > TERMINAL_VALUE_WARNING_THRESHOLD


@dataclass
class DCFResult:
    """
    Complete DCF valuation with all three scenarios.

    This is the primary output of the valuation module.
    Contains conservative, base, and optimistic scenarios
    plus plain language summary.
    """
    ticker: str
    company_name: str
    current_price: float

    # Three scenarios
    conservative: DCFScenario
    base: DCFScenario
    optimistic: DCFScenario

    # Inputs summary (for audit trail)
    base_fcf: float                      # Starting FCF for projections
    forecast_horizon: int
    terminal_growth_rate: float
    shares_outstanding: float
    net_debt: float

    # Warnings aggregated across scenarios
    warnings: list[str] = field(default_factory=list)

    @property
    def all_scenarios(self) -> list[DCFScenario]:
        return [self.conservative, self.base, self.optimistic]

    @property
    def intrinsic_value_range(self) -> tuple[float, float]:
        """(conservative IV, optimistic IV) per share."""
        return (
            self.conservative.intrinsic_value_per_share,
            self.optimistic.intrinsic_value_per_share,
        )

    @property
    def base_upside(self) -> float:
        return self.base.upside_downside


# ── DCF engine ────────────────────────────────────────────────────────────────

class DCFEngine:
    """
    Computes forward DCF valuation across three scenarios.

    Implements the EPFL growing perpetuity terminal value formula.
    Enforces WACC > g constraint.
    Shows terminal value as % of total — honest about dominance.

    Usage:
        engine = DCFEngine()
        result = engine.value(
            fcf_analysis=analysis,
            wacc_result=wacc,
            current_price=150.0,
            shares_outstanding=15e9,
            net_debt=80e9,
        )
    """

    def value(
        self,
        fcf_analysis: FCFAnalysis,
        wacc_result: WACCResult,
        current_price: float,
        shares_outstanding: float,
        net_debt: float,
        terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH_RATE,
        horizon: int = FORECAST_HORIZON_YEARS,
        use_ex_sbc: bool = False,
    ) -> DCFResult:
        """
        Compute full DCF valuation across three scenarios.

        Args:
            fcf_analysis: FCFAnalysis with growth assumptions.
            wacc_result: WACCResult with discount rate.
            current_price: Current share price.
            shares_outstanding: Diluted shares outstanding.
            net_debt: Total debt minus cash and equivalents.
            terminal_growth_rate: Terminal growth rate. Default 2.5%.
                                  Capped at MAX_TERMINAL_GROWTH_RATE.
            horizon: Forecast horizon in years. Default 10.
            use_ex_sbc: Use FCF excluding SBC as base. Default False.

        Returns:
            DCFResult with three scenarios.

        Raises:
            ValueError: If WACC <= terminal_growth_rate.
        """
        warnings = []

        # ── Input validation ──────────────────────────────────────────────────

        # Cap terminal growth
        terminal_growth_rate = min(
            terminal_growth_rate,
            MAX_TERMINAL_GROWTH_RATE,
        )

        # Warn if terminal growth is high for mature company
        if terminal_growth_rate > TERMINAL_GROWTH_MATURE_WARNING:
            warnings.append(
                f"Terminal growth rate of {terminal_growth_rate:.1%} exceeds "
                f"long-run nominal GDP growth. Ensure this is justified for "
                f"this specific company."
            )

        wacc = wacc_result.wacc

        # Enforce WACC > g — growing perpetuity formula undefined otherwise
        if wacc <= terminal_growth_rate:
            raise ValueError(
                f"WACC ({wacc:.1%}) must be greater than terminal growth rate "
                f"({terminal_growth_rate:.1%}). "
                f"The growing perpetuity formula TV = FCF(1+g)/(WACC-g) "
                f"is undefined when WACC ≤ g."
            )

        # ── Three scenario WACCs ──────────────────────────────────────────────
        wacc_conservative = wacc + SCENARIO_CONSERVATIVE_WACC_ADD
        wacc_base = wacc
        wacc_optimistic_raw = wacc - SCENARIO_OPTIMISTIC_WACC_SUB
        wacc_optimistic_floor = terminal_growth_rate + 0.005
        wacc_optimistic = max(wacc_optimistic_raw, wacc_optimistic_floor)
        wacc_warnings: list[str] = []
        if wacc_optimistic > wacc_optimistic_raw:
            wacc_warnings.append(
                f"Optimistic WACC clamped to {wacc_optimistic:.2%} "
                f"(floor = terminal growth + 0.5%); the documented "
                f"{SCENARIO_OPTIMISTIC_WACC_SUB:.1%} delta from base "
                f"could not be applied without violating WACC > g."
            )

        # ── Three scenarios ───────────────────────────────────────────────────
        conservative = self._compute_scenario(
            scenario_name="Conservative",
            growth_rate=fcf_analysis.growth_conservative,
            wacc=wacc_conservative,
            fcf_analysis=fcf_analysis,
            terminal_growth_rate=terminal_growth_rate,
            horizon=horizon,
            current_price=current_price,
            shares_outstanding=shares_outstanding,
            net_debt=net_debt,
            use_ex_sbc=use_ex_sbc,
        )

        base = self._compute_scenario(
            scenario_name="Base",
            growth_rate=fcf_analysis.growth_base,
            wacc=wacc_base,
            fcf_analysis=fcf_analysis,
            terminal_growth_rate=terminal_growth_rate,
            horizon=horizon,
            current_price=current_price,
            shares_outstanding=shares_outstanding,
            net_debt=net_debt,
            use_ex_sbc=use_ex_sbc,
        )

        optimistic = self._compute_scenario(
            scenario_name="Optimistic",
            growth_rate=fcf_analysis.growth_optimistic,
            wacc=wacc_optimistic,
            fcf_analysis=fcf_analysis,
            terminal_growth_rate=terminal_growth_rate,
            horizon=horizon,
            current_price=current_price,
            shares_outstanding=shares_outstanding,
            net_debt=net_debt,
            use_ex_sbc=use_ex_sbc,
        )

        # Aggregate warnings
        warnings.extend(wacc_warnings)
        for scenario in [conservative, base, optimistic]:
            warnings.extend(scenario.warnings)

        # Deduplicate warnings
        seen = set()
        unique_warnings = []
        for w in warnings:
            if w not in seen:
                seen.add(w)
                unique_warnings.append(w)

        return DCFResult(
            ticker=fcf_analysis.ticker,
            company_name=fcf_analysis.company_name,
            current_price=current_price,
            conservative=conservative,
            base=base,
            optimistic=optimistic,
            base_fcf=fcf_analysis.latest_fcf,
            forecast_horizon=horizon,
            terminal_growth_rate=terminal_growth_rate,
            shares_outstanding=shares_outstanding,
            net_debt=net_debt,
            warnings=unique_warnings,
        )

    def _compute_scenario(
        self,
        scenario_name: str,
        growth_rate: float,
        wacc: float,
        fcf_analysis: FCFAnalysis,
        terminal_growth_rate: float,
        horizon: int,
        current_price: float,
        shares_outstanding: float,
        net_debt: float,
        use_ex_sbc: bool,
    ) -> DCFScenario:
        """
        Compute one DCF scenario.

        Args:
            scenario_name: "Conservative", "Base", or "Optimistic".
            growth_rate: FCF growth rate for this scenario.
            wacc: Discount rate for this scenario.
            fcf_analysis: FCFAnalysis for base FCF.
            terminal_growth_rate: Terminal growth rate.
            horizon: Forecast years.
            current_price: Current share price.
            shares_outstanding: Diluted shares.
            net_debt: Total debt - cash.
            use_ex_sbc: Use FCF ex SBC.

        Returns:
            DCFScenario with full valuation.
        """
        from openquant.valuation.fcf import FCFAnalyser
        analyser = FCFAnalyser()
        projection = analyser.project(
            fcf_analysis,
            custom_growth=growth_rate,
            use_ex_sbc=use_ex_sbc,
            horizon=horizon,
        )
        projection.scenario_name = scenario_name

        warnings = []

        projected_fcf = projection.projected_fcf

        # ── Present value of projected FCFs ───────────────────────────────────
        # PV_t = FCF_t / (1 + WACC)^t
        pv_fcfs = pd.Series(
            {
                year: fcf / (1 + wacc) ** year
                for year, fcf in projected_fcf.items()
            }
        )
        pv_fcfs_total = float(pv_fcfs.sum())

        # ── Terminal value ────────────────────────────────────────────────────
        # TV = FCF_n × (1 + g) / (WACC − g)
        # EPFL formula sheet — growing perpetuity
        terminal_fcf = float(projected_fcf.iloc[-1])

        if wacc <= terminal_growth_rate:
            raise ValueError(
                f"WACC ({wacc:.1%}) ≤ terminal growth ({terminal_growth_rate:.1%}). "
                f"Terminal value undefined."
            )

        terminal_value = terminal_fcf * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
        pv_terminal_value = terminal_value / (1 + wacc) ** horizon

        # ── Enterprise value ──────────────────────────────────────────────────
        enterprise_value = pv_fcfs_total + pv_terminal_value

        # Terminal value as % of EV
        terminal_value_pct = (
            pv_terminal_value / enterprise_value
            if enterprise_value > 0 else 0.0
        )

        # Warn if TV dominates
        if terminal_value_pct > TERMINAL_VALUE_SEVERE_THRESHOLD:
            warnings.append(
                f"{scenario_name}: Terminal value represents "
                f"{terminal_value_pct:.0%} of enterprise value. "
                f"This valuation is highly sensitive to the terminal "
                f"growth assumption."
            )
        elif terminal_value_pct > TERMINAL_VALUE_WARNING_THRESHOLD:
            warnings.append(
                f"{scenario_name}: Terminal value is "
                f"{terminal_value_pct:.0%} of enterprise value. "
                f"Review the terminal growth assumption carefully."
            )

        # ── Equity value ──────────────────────────────────────────────────────
        # Equity Value = Enterprise Value − Net Debt
        equity_value = enterprise_value - net_debt

        if equity_value < 0:
            warnings.append(
                f"{scenario_name}: Enterprise value ({enterprise_value/1e9:.1f}B) "
                f"is less than net debt ({net_debt/1e9:.1f}B). "
                f"Equity value is negative — stock may be worthless under "
                f"this scenario."
            )

        # ── Intrinsic value per share ─────────────────────────────────────────
        # Negative equity (EV < net debt) is real economic information —
        # preserve the negative per-share value so the UI can distinguish a
        # structurally insolvent company from one that is merely overpriced.
        if shares_outstanding > 0:
            intrinsic_value_per_share = equity_value / shares_outstanding
        else:
            intrinsic_value_per_share = 0.0

        # ── Margin of safety ─────────────────────────────────────────────────
        if intrinsic_value_per_share > 0:
            margin_of_safety = (
                (intrinsic_value_per_share - current_price)
                / intrinsic_value_per_share
            )
        else:
            margin_of_safety = -1.0

        return DCFScenario(
            scenario_name=scenario_name,
            growth_rate=growth_rate,
            wacc=wacc,
            projected_fcf=projected_fcf,
            pv_fcfs=pv_fcfs,
            pv_fcfs_total=pv_fcfs_total,
            terminal_fcf=terminal_fcf,
            terminal_value=terminal_value,
            pv_terminal_value=pv_terminal_value,
            terminal_value_pct=terminal_value_pct,
            enterprise_value=enterprise_value,
            net_debt=net_debt,
            equity_value=equity_value,
            shares_outstanding=shares_outstanding,
            intrinsic_value_per_share=intrinsic_value_per_share,
            current_price=current_price,
            margin_of_safety=margin_of_safety,
            warnings=warnings,
        )

    # ── NPV helper — EPFL exam compatibility ─────────────────────────────────

    def npv(
        self,
        cash_flows: list[float],
        discount_rate: float,
    ) -> float:
        """
        Compute NPV of a cash flow series.

        Implements EPFL formula:
            NPV = Σ CF_t / (1 + r)^t

        First cash flow at t=0 (not discounted).
        Subsequent cash flows at t=1, 2, ..., n.

        Args:
            cash_flows: List of cash flows. Index 0 = t=0.
            discount_rate: Annual discount rate.

        Returns:
            Net present value.

        Example (EPFL Exam 1 Problem 2):
            npv([-24000, 8400, 9150, 11100, 14850], 0.20)
            Should give positive NPV
        """
        return sum(
            cf / (1 + discount_rate) ** t
            for t, cf in enumerate(cash_flows)
        )

    def irr(
        self,
        cash_flows: list[float],
        low: float = -0.99,
        high: float = 10.0,
    ) -> float:
        """
        Internal rate of return — the discount rate r such that NPV(r) = 0.

        EPFL Sample Exam 1 Problem 3:
            irr([-5000, 3600, 3600])      ≈ 0.282  (28.2%)
            irr([-100000, 66000, 66000])  ≈ 0.207  (20.7%)

        Args:
            cash_flows: Cash flow series, index 0 = t=0 (typically negative outlay).
            low: Lower bracket bound for brentq. Default -99%.
            high: Upper bracket bound. Default 1000%.

        Returns:
            The IRR as a decimal.

        Raises:
            ValueError: If the bracket does not contain a sign change (no real
                IRR within [low, high], or multiple IRRs from cashflow-sign changes).
        """
        from scipy.optimize import brentq

        def f(r):
            return self.npv(cash_flows, r)
        try:
            return float(brentq(f, low, high, xtol=1e-9, maxiter=200))
        except ValueError as e:
            raise ValueError(
                f"IRR not found in [{low:.0%}, {high:.0%}]; cash flow series "
                f"may have no real root or multiple sign changes."
            ) from e

    def pv_tax_shield(
        self,
        debt_schedule: list[float],
        interest_rate: float,
        tax_rate: float,
        discount_rate: float,
    ) -> float:
        """
        Present value of the interest tax shield from a known debt schedule.

        EPFL formula sheet (Tax shield on interest):
            PVTS = Σ_{t=1..T} (Debt_{t-1} × r_D × T_c) / (1 + r_disc)^t

        EPFL Sample Exam 1 Problem 3:
            debt_schedule = [12_000_000, 9_000_000, 6_000_000, 3_000_000, 0]
            interest_rate = 0.10, tax_rate = 0.35, discount_rate = 0.10
            → PVTS ≈ 871,640  (answer key states 876,641 — small typo in key)

        Args:
            debt_schedule: Debt outstanding at the end of each year, starting
                with year 0 (i.e. debt_schedule[t-1] is the principal on which
                interest is paid in year t). Length T+1.
            interest_rate: Pre-tax cost of debt (r_D).
            tax_rate: Corporate tax rate (T_c).
            discount_rate: Discount rate for the tax shields. Standard practice
                uses r_D (since the shield's risk matches the debt's).

        Returns:
            PV of the tax shield in the same currency as the debt schedule.
        """
        if tax_rate < 0 or tax_rate > 1:
            raise ValueError(f"tax_rate must be in [0, 1], got {tax_rate}")
        pv = 0.0
        for t in range(1, len(debt_schedule)):
            interest = debt_schedule[t - 1] * interest_rate
            tax_saving = interest * tax_rate
            pv += tax_saving / (1 + discount_rate) ** t
        return pv

    def growing_annuity_pv(
        self,
        cash_flow: float,
        discount_rate: float,
        growth_rate: float,
        n_periods: int,
    ) -> float:
        """
        Present value of a growing annuity (finite-horizon growing cashflow).

        EPFL formula sheet:
            PV = C / (r − g) × (1 − ((1 + g)/(1 + r))^N)

        Reduces to the growing perpetuity as N → ∞ (when g < r) and to the
        ordinary annuity formula when g = 0.

        EPFL Sample Exam 2 Problem 1-Q2:
            growing_annuity_pv(400, 0.075, 0.04, 18)  ≈  5,130.03

        Args:
            cash_flow: First period cash flow C (paid at t=1).
            discount_rate: Discount rate r per period.
            growth_rate: Per-period growth rate g.
            n_periods: Number of payments N.

        Returns:
            Present value of the growing annuity.

        Raises:
            ValueError: When r == g exactly (formula undefined; closed-form
                degenerates — use PV = N·C/(1+r) in that limit).
        """
        if discount_rate == growth_rate:
            raise ValueError(
                "growing_annuity_pv is undefined for r == g; use "
                "PV = N · C / (1 + r) for that degenerate case."
            )
        ratio = (1.0 + growth_rate) / (1.0 + discount_rate)
        return cash_flow / (discount_rate - growth_rate) * (1.0 - ratio ** n_periods)

    def growing_perpetuity_pv(
        self,
        cash_flow: float,
        discount_rate: float,
        growth_rate: float,
    ) -> float:
        """
        Present value of a growing perpetuity.

        EPFL formula sheet:
            PV = C / (r − g)

        Args:
            cash_flow: First period cash flow (C).
            discount_rate: Discount rate (r).
            growth_rate: Growth rate (g). Must be < r.

        Returns:
            Present value of the growing perpetuity.

        Raises:
            ValueError: If discount_rate <= growth_rate.
        """
        if discount_rate <= growth_rate:
            raise ValueError(
                f"Discount rate ({discount_rate:.1%}) must exceed "
                f"growth rate ({growth_rate:.1%}) for a growing perpetuity."
            )
        return cash_flow / (discount_rate - growth_rate)
