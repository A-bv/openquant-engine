"""
Tests for openquant/valuation/dcf.py

Covers:
1. EPFL growing-perpetuity terminal value formula
2. Three-scenario differentiation (growth + WACC vary per scenario)
3. WACC > g enforcement
4. Negative equity value handled gracefully (IV = 0, not a crash)
5. Intrinsic value per share formula
6. Terminal value percentage sanity
"""

from datetime import datetime

import pandas as pd
import pytest

from openquant.data import FinancialStatements
from openquant.valuation.dcf import DCFEngine
from openquant.valuation.fcf import FCFAnalyser
from openquant.valuation.wacc import WACCResult

# ── Helpers ────────────────────────────────────────────────────────────────────

def make_statements(
    fcf_values: list[float],
    years: list[int] | None = None,
    ticker: str = "TEST",
    company: str = "Test Co",
) -> FinancialStatements:
    n = len(fcf_values)
    if years is None:
        years = list(range(2015, 2015 + n))
    idx = pd.Index(years, name="year")
    fcf = pd.Series(fcf_values, index=idx, dtype=float)
    revenue = pd.Series([max(abs(v) * 5, 1e9) for v in fcf_values], index=idx, dtype=float)
    zeros = pd.Series([0.0] * n, index=idx, dtype=float)
    ones_b = pd.Series([1e9] * n, index=idx, dtype=float)
    return FinancialStatements(
        ticker=ticker, company_name=company, cik="0000000000", source="test",
        fetched_at=datetime(2025, 1, 1),
        revenue=revenue, ebit=zeros, depreciation_amortisation=zeros,
        interest_expense=zeros, tax_expense=zeros, net_income=zeros, ebitda=zeros,
        total_assets=ones_b, total_debt=zeros, beginning_debt=zeros,
        cash_and_equivalents=zeros, shares_outstanding=ones_b,
        net_working_capital=zeros, operating_cash_flow=fcf,
        capital_expenditure=zeros, free_cash_flow=fcf,
        stock_based_compensation=zeros,
        effective_tax_rate=pd.Series([0.21] * n, index=idx, dtype=float),
        fcf_margin=pd.Series([f / max(abs(f) * 5, 1e9) for f in fcf_values], index=idx, dtype=float),
        data_warnings=[],
    )


def make_wacc(wacc: float = 0.10) -> WACCResult:
    """Build a minimal WACCResult with a fixed WACC."""
    return WACCResult(
        ticker="TEST",
        company_name="Test Co",
        market_cap=10e9,
        total_debt=0.0,
        firm_value=10e9,
        equity_weight=1.0,
        debt_weight=0.0,
        cost_of_equity=wacc,
        cost_of_debt_pretax=0.04,
        cost_of_debt_aftertax=0.04 * (1 - 0.21),
        tax_rate=0.21,
        wacc=wacc,
        beta=1.0,
        risk_free_rate=0.045,
        market_risk_premium=0.055,
        tax_shield_pv_note="",
        wacc_sensitivity={},
        warnings=[],
    )


ENGINE = DCFEngine()
ANALYSER = FCFAnalyser()


# ── EPFL growing-perpetuity formula ───────────────────────────────────────────

class TestGrowingPerpetuity:

    def test_npv_epfl_exam1(self, epfl_exam1):
        """
        EPFL Exam 1, Problem 2: NPV at 20% WACC.

        FCF = [-24M, +8.4M, +9.15M, +11.1M, +14.85M]
        The NPV should be > 0 (per exam answer key).
        """
        npv = ENGINE.npv(epfl_exam1["fcf"], epfl_exam1["required_return"])
        assert npv > 0, f"Expected positive NPV, got {npv:,.0f}"

    def test_npv_zero_at_irr(self):
        """NPV is ~0 when the discount rate equals the IRR."""
        # Simple: invest 100 today, get 110 in one year → IRR = 10%
        cash_flows = [-100, 110]
        npv = ENGINE.npv(cash_flows, 0.10)
        assert abs(npv) < 1e-6

    def test_growing_perpetuity_formula(self):
        """
        PV of growing perpetuity = C / (r - g).
        EPFL formula sheet: C=100, r=0.10, g=0.03 → PV = 100/0.07 ≈ 1428.57
        """
        pv = ENGINE.growing_perpetuity_pv(100, 0.10, 0.03)
        assert abs(pv - 100 / 0.07) < 0.01

    def test_growing_perpetuity_raises_when_r_le_g(self):
        """Raises ValueError when discount rate ≤ growth rate."""
        with pytest.raises(ValueError, match="[Dd]iscount rate"):
            ENGINE.growing_perpetuity_pv(100, 0.03, 0.05)

    def test_growing_perpetuity_raises_when_r_equals_g(self):
        """Raises ValueError when discount rate = growth rate exactly."""
        with pytest.raises(ValueError):
            ENGINE.growing_perpetuity_pv(100, 0.05, 0.05)


# ── Three-scenario differentiation ────────────────────────────────────────────

class TestScenarioDifferentiation:

    def _base_result(self, median_growth=0.15, wacc=0.10):
        fcf = [1e9 * (1 + median_growth) ** i for i in range(8)]
        analysis = ANALYSER.analyse(make_statements(fcf))
        wacc_result = make_wacc(wacc)
        return ENGINE.value(
            fcf_analysis=analysis,
            wacc_result=wacc_result,
            current_price=50.0,
            shares_outstanding=1e9,
            net_debt=0.0,
            terminal_growth_rate=0.025,
        )

    def test_three_ivs_are_ordered(self):
        """Conservative IV < Base IV < Optimistic IV."""
        result = self._base_result()
        assert result.conservative.intrinsic_value_per_share \
             < result.base.intrinsic_value_per_share \
             < result.optimistic.intrinsic_value_per_share, (
            "Scenario IVs are not ordered conservative < base < optimistic."
        )

    def test_conservative_uses_higher_wacc(self):
        """Conservative scenario uses a higher WACC than base."""
        result = self._base_result()
        assert result.conservative.wacc > result.base.wacc

    def test_optimistic_uses_lower_wacc(self):
        """Optimistic scenario uses a lower WACC than base."""
        result = self._base_result()
        assert result.optimistic.wacc < result.base.wacc

    def test_all_ivs_are_positive(self):
        """All three scenario IVs must be positive for a profitable company."""
        result = self._base_result()
        for scenario in result.all_scenarios:
            assert scenario.intrinsic_value_per_share > 0

    def test_scenario_names(self):
        """Scenario names are exactly Conservative, Base, Optimistic."""
        result = self._base_result()
        assert result.conservative.scenario_name == "Conservative"
        assert result.base.scenario_name == "Base"
        assert result.optimistic.scenario_name == "Optimistic"


# ── WACC > terminal growth enforcement ────────────────────────────────────────

class TestWACCConstraint:

    def test_raises_when_wacc_equals_terminal_growth(self):
        """ValueError when WACC == terminal_growth_rate."""
        fcf = [1e9, 1.2e9, 1.4e9, 1.6e9, 1.8e9]
        analysis = ANALYSER.analyse(make_statements(fcf))
        wacc_result = make_wacc(wacc=0.025)
        with pytest.raises(ValueError, match="[Ww][Aa][Cc][Cc]"):
            ENGINE.value(
                fcf_analysis=analysis,
                wacc_result=wacc_result,
                current_price=50.0,
                shares_outstanding=1e9,
                net_debt=0.0,
                terminal_growth_rate=0.025,
            )

    def test_raises_when_wacc_below_terminal_growth(self):
        """ValueError when WACC < terminal_growth_rate."""
        fcf = [1e9, 1.2e9, 1.4e9, 1.6e9, 1.8e9]
        analysis = ANALYSER.analyse(make_statements(fcf))
        wacc_result = make_wacc(wacc=0.01)
        with pytest.raises(ValueError):
            ENGINE.value(
                fcf_analysis=analysis,
                wacc_result=wacc_result,
                current_price=50.0,
                shares_outstanding=1e9,
                net_debt=0.0,
                terminal_growth_rate=0.025,
            )


# ── Negative equity value ─────────────────────────────────────────────────────

class TestNegativeEquity:

    def test_iv_is_negative_when_net_debt_exceeds_ev(self):
        """
        When net debt exceeds enterprise value, equity value < 0.
        IV per share must reflect that as a negative number so the UI can
        distinguish structural insolvency from mere overpricing — silently
        clamping to 0 hides real economic information.
        """
        fcf = [0.1e9, 0.1e9, 0.1e9, 0.1e9, 0.1e9]
        analysis = ANALYSER.analyse(make_statements(fcf))
        wacc_result = make_wacc(wacc=0.15)
        result = ENGINE.value(
            fcf_analysis=analysis,
            wacc_result=wacc_result,
            current_price=50.0,
            shares_outstanding=1e9,
            net_debt=100e9,   # absurdly large net debt
            terminal_growth_rate=0.025,
        )
        assert result.base.intrinsic_value_per_share < 0
        assert result.conservative.intrinsic_value_per_share < 0
        assert result.optimistic.intrinsic_value_per_share < 0

    def test_negative_equity_warning_present(self):
        """A warning should be emitted when equity value is negative."""
        fcf = [0.1e9, 0.1e9, 0.1e9, 0.1e9, 0.1e9]
        analysis = ANALYSER.analyse(make_statements(fcf))
        wacc_result = make_wacc(wacc=0.15)
        result = ENGINE.value(
            fcf_analysis=analysis,
            wacc_result=wacc_result,
            current_price=50.0,
            shares_outstanding=1e9,
            net_debt=100e9,
            terminal_growth_rate=0.025,
        )
        combined = " ".join(result.warnings).lower()
        assert "negative" in combined or "less than net debt" in combined


# ── Intrinsic value per share arithmetic ──────────────────────────────────────

class TestIVPerShare:

    def test_iv_scales_with_shares(self):
        """Doubling shares outstanding halves IV per share."""
        fcf = [1e9, 1.2e9, 1.4e9, 1.6e9, 1.8e9]
        analysis = ANALYSER.analyse(make_statements(fcf))
        wacc_result = make_wacc(wacc=0.10)

        result_1b = ENGINE.value(
            fcf_analysis=analysis, wacc_result=wacc_result,
            current_price=50.0, shares_outstanding=1e9, net_debt=0.0,
        )
        result_2b = ENGINE.value(
            fcf_analysis=analysis, wacc_result=wacc_result,
            current_price=50.0, shares_outstanding=2e9, net_debt=0.0,
        )
        iv_1b = result_1b.base.intrinsic_value_per_share
        iv_2b = result_2b.base.intrinsic_value_per_share
        assert abs(iv_1b / iv_2b - 2.0) < 0.01, (
            f"Doubling shares should halve IV: {iv_1b:.2f} / {iv_2b:.2f} = {iv_1b/iv_2b:.3f}"
        )

    def test_net_cash_increases_iv(self):
        """Negative net debt (net cash) increases equity value and IV."""
        fcf = [1e9, 1.2e9, 1.4e9, 1.6e9, 1.8e9]
        analysis = ANALYSER.analyse(make_statements(fcf))
        wacc_result = make_wacc(wacc=0.10)

        result_zero_debt = ENGINE.value(
            fcf_analysis=analysis, wacc_result=wacc_result,
            current_price=50.0, shares_outstanding=1e9, net_debt=0.0,
        )
        result_net_cash = ENGINE.value(
            fcf_analysis=analysis, wacc_result=wacc_result,
            current_price=50.0, shares_outstanding=1e9, net_debt=-5e9,  # net cash
        )
        assert result_net_cash.base.intrinsic_value_per_share \
             > result_zero_debt.base.intrinsic_value_per_share


# ── Terminal value sanity ──────────────────────────────────────────────────────

class TestTerminalValue:

    def test_terminal_value_pct_between_0_and_1(self):
        """Terminal value as % of EV must be between 0% and 100%."""
        fcf = [1e9 * (1.10 ** i) for i in range(8)]
        analysis = ANALYSER.analyse(make_statements(fcf))
        wacc_result = make_wacc(wacc=0.10)
        result = ENGINE.value(
            fcf_analysis=analysis, wacc_result=wacc_result,
            current_price=50.0, shares_outstanding=1e9, net_debt=0.0,
        )
        for scenario in result.all_scenarios:
            assert 0.0 <= scenario.terminal_value_pct <= 1.0, (
                f"{scenario.scenario_name} TV% = {scenario.terminal_value_pct:.1%}"
            )

    def test_higher_terminal_growth_increases_tv(self):
        """Higher terminal growth rate → higher terminal value."""
        fcf = [1e9, 1.2e9, 1.4e9, 1.6e9, 1.8e9]
        analysis = ANALYSER.analyse(make_statements(fcf))
        wacc_result = make_wacc(wacc=0.10)

        result_low = ENGINE.value(
            fcf_analysis=analysis, wacc_result=wacc_result,
            current_price=50.0, shares_outstanding=1e9, net_debt=0.0,
            terminal_growth_rate=0.01,
        )
        result_high = ENGINE.value(
            fcf_analysis=analysis, wacc_result=wacc_result,
            current_price=50.0, shares_outstanding=1e9, net_debt=0.0,
            terminal_growth_rate=0.025,
        )
        assert result_high.base.pv_terminal_value > result_low.base.pv_terminal_value

    def test_terminal_growth_capped_at_max(self):
        """terminal_growth_rate is capped at MAX_TERMINAL_GROWTH_RATE (3%)."""
        from openquant.config import MAX_TERMINAL_GROWTH_RATE
        fcf = [1e9, 1.2e9, 1.4e9, 1.6e9, 1.8e9]
        analysis = ANALYSER.analyse(make_statements(fcf))
        wacc_result = make_wacc(wacc=0.10)
        result = ENGINE.value(
            fcf_analysis=analysis, wacc_result=wacc_result,
            current_price=50.0, shares_outstanding=1e9, net_debt=0.0,
            terminal_growth_rate=0.99,  # absurd — should be capped
        )
        assert result.terminal_growth_rate <= MAX_TERMINAL_GROWTH_RATE
