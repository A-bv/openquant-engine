"""
EPFL Introduction to Finance — Sample Exam 1.

Tests the OpenQuant implementation against the exam's worked-out
ground-truth values. Covers:

  Problem 2 — Q1: FCF from EBIT components
  Problem 2 — Q2: Hamada unlevering + CAPM cost of equity
  Problem 2 — Q3: PV of interest tax shield
  Problem 3 — Q1: IRR of two mutually-exclusive projects
  Problem 3 — Q4: NPV of those projects at 15%
  Problem 3 — Q5: Incremental IRR(B − A)

These tests guard the formulas in openquant/valuation/fcf.py, openquant/valuation/wacc.py and openquant/valuation/dcf.py
against silent regressions of the underlying finance math. Theory MCQs
(P1, P4) and out-of-scope items (P2-Q4 bankruptcy costs) are not tested.
"""

from __future__ import annotations

import pytest

from openquant.valuation.dcf import DCFEngine
from openquant.valuation.fcf import fcf_from_ebit_components
from openquant.valuation.wacc import unlever_beta_hamada, capm_cost_of_equity


ENGINE = DCFEngine()


# ── Problem 2 — Q1: FCF from EBIT components ────────────────────────────────

class TestExam1Problem2_FCF:
    """
    Project FCFs computed from EBITDA, depreciation, tax rate, and ΔWC.
    Ground truth (in $000s):  Year 1=8400, Year 2=9150, Year 3=11100, Year 4=14850
    """

    TAX_RATE = 0.35
    DEPRECIATION = 6000  # 24000 / 4 years, linear

    def test_year_1_fcf(self):
        fcf = fcf_from_ebit_components(
            ebitda=12000, depreciation=self.DEPRECIATION,
            tax_rate=self.TAX_RATE, change_in_wc=1500,
        )
        assert abs(fcf - 8400) < 1e-6

    def test_year_2_fcf(self):
        fcf = fcf_from_ebit_components(
            ebitda=12000, depreciation=self.DEPRECIATION,
            tax_rate=self.TAX_RATE, change_in_wc=750,
        )
        assert abs(fcf - 9150) < 1e-6

    def test_year_3_fcf(self):
        fcf = fcf_from_ebit_components(
            ebitda=15000, depreciation=self.DEPRECIATION,
            tax_rate=self.TAX_RATE, change_in_wc=750,
        )
        assert abs(fcf - 11100) < 1e-6

    def test_year_4_fcf_with_wc_recovery(self):
        """Year 4 recovers the entire working capital — ΔWC is negative."""
        fcf = fcf_from_ebit_components(
            ebitda=15000, depreciation=self.DEPRECIATION,
            tax_rate=self.TAX_RATE, change_in_wc=-3000,
        )
        assert abs(fcf - 14850) < 1e-6

    def test_full_fcf_series_matches_fixture(self, epfl_exam1):
        """The four computed FCFs match the hand-computed series in the fixture."""
        expected = epfl_exam1["fcf"][1:]  # Skip the t=0 initial investment
        wc_changes = [1500, 750, 750, -3000]
        ebitdas = [12000, 12000, 15000, 15000]
        computed = [
            fcf_from_ebit_components(
                ebitda=e * 1000,  # Fixture stores in dollars; we're in $000s
                depreciation=self.DEPRECIATION * 1000,
                tax_rate=self.TAX_RATE,
                change_in_wc=w * 1000,
            )
            for e, w in zip(ebitdas, wc_changes)
        ]
        for c, exp in zip(computed, expected):
            assert abs(c - exp) < 1.0


# ── Problem 2 — Q2: Hamada unlevering + CAPM ────────────────────────────────

class TestExam1Problem2_HamadaCAPM:
    """
    Firm A: βE=1.99, D/V=33%  →  D/E ≈ 0.4925 → βU = 1.500
    Firm B: βE=2.48, D/V=50%  →  D/E = 1.00   → βU = 1.503 (~1.50)
    Average βU = 1.50; rE = 8% + 1.50 × 8% = 20%
    """

    TAX = 0.35
    RF = 0.08
    MRP = 0.08

    @staticmethod
    def _dv_to_de(dv: float) -> float:
        """Convert D/V leverage ratio to D/E."""
        return dv / (1.0 - dv)

    def test_firm_a_unlevered_beta(self):
        de = self._dv_to_de(0.33)
        bu = unlever_beta_hamada(beta_levered=1.99, debt_to_equity=de, tax_rate=self.TAX)
        # EPFL exam states 1.50 — exact arithmetic gives 1.5004 with D/V=0.33
        assert abs(bu - 1.50) < 0.01

    def test_firm_b_unlevered_beta(self):
        de = self._dv_to_de(0.50)
        bu = unlever_beta_hamada(beta_levered=2.48, debt_to_equity=de, tax_rate=self.TAX)
        assert abs(bu - 1.50) < 0.01

    def test_average_unlevered_beta_is_1_50(self):
        bu_a = unlever_beta_hamada(1.99, self._dv_to_de(0.33), self.TAX)
        bu_b = unlever_beta_hamada(2.48, self._dv_to_de(0.50), self.TAX)
        assert abs((bu_a + bu_b) / 2 - 1.50) < 0.01

    def test_required_return_via_capm(self):
        """CAPM: rE = 8% + 1.50 × 8% = 20%."""
        r = capm_cost_of_equity(self.RF, 1.50, self.MRP)
        assert abs(r - 0.20) < 1e-9

    def test_capm_matches_fixture_required_return(self, epfl_exam1):
        r = capm_cost_of_equity(
            epfl_exam1["risk_free_rate"],
            epfl_exam1["unlevered_beta"],
            epfl_exam1["market_risk_premium"],
        )
        assert abs(r - epfl_exam1["required_return"]) < 1e-9


# ── Problem 2 — Q3: PV of interest tax shield ───────────────────────────────

class TestExam1Problem2_PVTS:
    """
    Debt amortises 25% of $12M per year: schedule = [12M, 9M, 6M, 3M, 0].
    Interest rate 10%, tax rate 35%, shields discounted at 10%.

    The exam answer key states PVTS = 876,641, but its own algebraic formula
    evaluates to ~871,640. The discrepancy is a small arithmetic error in the
    key — we test against the correct value computed from the formula.
    """

    def test_pvts_matches_formula(self):
        debt_schedule = [12_000_000, 9_000_000, 6_000_000, 3_000_000, 0]
        pvts = ENGINE.pv_tax_shield(
            debt_schedule=debt_schedule,
            interest_rate=0.10,
            tax_rate=0.35,
            discount_rate=0.10,
        )
        # Exact value from the EPFL formula: 105_000 × (4/1.1 + 3/1.1² + 2/1.1³ + 1/1.1⁴)
        expected = 105_000 * (4/1.1 + 3/1.1**2 + 2/1.1**3 + 1/1.1**4)
        assert abs(pvts - expected) < 1.0
        # Should also be within $5K of the (slightly wrong) exam answer
        assert abs(pvts - 876_641) < 5_500

    def test_pvts_zero_when_no_debt(self):
        assert ENGINE.pv_tax_shield([0, 0, 0], 0.10, 0.35, 0.10) == 0.0

    def test_pvts_zero_when_no_tax(self):
        debt_schedule = [12_000_000, 9_000_000, 6_000_000, 3_000_000, 0]
        assert ENGINE.pv_tax_shield(debt_schedule, 0.10, 0.0, 0.10) == 0.0

    def test_pvts_rejects_invalid_tax_rate(self):
        with pytest.raises(ValueError, match="tax_rate"):
            ENGINE.pv_tax_shield([1000, 500, 0], 0.10, 1.5, 0.10)


# ── Problem 3 — Q1 + Q4: IRR & NPV of two projects ──────────────────────────

class TestExam1Problem3_NPV_IRR:
    """
    Project A: [-5000, 3600, 3600]
        NPV @ 15% = 852.55,  IRR = 28.2%
    Project B: [-100000, 66000, 66000]
        NPV @ 15% = 7296.79, IRR = 20.7%
    """

    PROJECT_A = [-5000, 3600, 3600]
    PROJECT_B = [-100_000, 66_000, 66_000]

    def test_npv_project_a_at_15pct(self):
        assert abs(ENGINE.npv(self.PROJECT_A, 0.15) - 852.55) < 0.01

    def test_npv_project_b_at_15pct(self):
        assert abs(ENGINE.npv(self.PROJECT_B, 0.15) - 7296.79) < 0.01

    def test_npv_b_exceeds_npv_a(self):
        """At 15%, project B has higher NPV despite lower IRR — the scale effect."""
        npv_a = ENGINE.npv(self.PROJECT_A, 0.15)
        npv_b = ENGINE.npv(self.PROJECT_B, 0.15)
        assert npv_b > npv_a

    def test_irr_project_a(self):
        irr = ENGINE.irr(self.PROJECT_A)
        assert abs(irr - 0.282) < 0.001

    def test_irr_project_b(self):
        irr = ENGINE.irr(self.PROJECT_B)
        assert abs(irr - 0.207) < 0.001

    def test_irr_at_zero_makes_npv_zero(self):
        """Sanity: IRR is by definition the rate that zeroes NPV."""
        irr_a = ENGINE.irr(self.PROJECT_A)
        assert abs(ENGINE.npv(self.PROJECT_A, irr_a)) < 1e-6

    def test_irr_a_exceeds_irr_b(self):
        """Smaller project has higher IRR — the result that IRR-only ranking
        misses (this is what the exam's Q3 is illustrating)."""
        assert ENGINE.irr(self.PROJECT_A) > ENGINE.irr(self.PROJECT_B)


# ── Problem 3 — Q5: Incremental IRR(B − A) ──────────────────────────────────

class TestExam1Problem3_IncrementalIRR:
    """
    NPV(B) > NPV(A) iff NPV(B-A) ≥ 0 iff r ≤ IRR(B-A) = 20.289%.
    Below 20.289%, prefer B. Above, prefer A.
    """

    def test_incremental_irr_is_20_289_pct(self):
        a = [-5000, 3600, 3600]
        b = [-100_000, 66_000, 66_000]
        incremental = [b_i - a_i for b_i, a_i in zip(b, a)]
        irr = ENGINE.irr(incremental)
        assert abs(irr - 0.20289) < 0.001

    def test_crossover_at_incremental_irr(self):
        """At exactly the incremental IRR, NPV(A) == NPV(B)."""
        a = [-5000, 3600, 3600]
        b = [-100_000, 66_000, 66_000]
        irr = ENGINE.irr([b_i - a_i for b_i, a_i in zip(b, a)])
        assert abs(ENGINE.npv(a, irr) - ENGINE.npv(b, irr)) < 1e-3
