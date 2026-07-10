"""
EPFL Principles of Finance — Sample Exam 2 (MidTerm B).

Pins OpenQuant's implementation against the exam's worked-out values.

In scope:
  P1-Q2 — Growing annuity PV
  P2    — Multi-stage Dividend Discount Model + capital gain rate
  P3    — Beta from correlation + CAPM (incl. negative β)
  P4    — Portfolio expected return / volatility + 2-asset min-variance
  P5    — Idiosyncratic variance + Sharpe ratio from summary stats

Out of scope (intentionally not tested):
  P1-Q1 — Sub-annual (monthly) compounding NPV — OpenQuant uses annual periods
  P1-Q3 — Annuity-FV solving for contribution amount — not equity-DCF math
  P1-Q4 — Zero-coupon bonds + forward rates + coupon-bond pricing — bonds out of scope
  P3-Q3a — Theory MCQ
"""

from __future__ import annotations

import math

import pytest

from openquant.common import (
    capital_gain_rate,
    min_variance_two_asset_weight,
    sharpe_from_stats,
)
from openquant.valuation.dcf import DCFEngine
from openquant.valuation.wacc import (
    beta_from_correlation,
    capm_cost_of_equity,
    idiosyncratic_variance,
)

ENGINE = DCFEngine()


# ── P1-Q2: Growing annuity PV ──────────────────────────────────────────────

class TestExam2P1_GrowingAnnuity:
    """
    18-year growing annuity: C=400, g=4%, r=7.5%  →  PV ≈ $5,130.03
    """

    def test_growing_annuity_pv_matches_exam(self):
        pv = ENGINE.growing_annuity_pv(
            cash_flow=400, discount_rate=0.075,
            growth_rate=0.04, n_periods=18,
        )
        assert abs(pv - 5130.03) < 0.10

    def test_growing_annuity_reduces_to_perpetuity_in_limit(self):
        """As N → ∞ with g < r, the growing annuity → growing perpetuity."""
        c, r, g = 100.0, 0.10, 0.03
        annuity = ENGINE.growing_annuity_pv(c, r, g, n_periods=500)
        perpetuity = ENGINE.growing_perpetuity_pv(c, r, g)
        assert abs(annuity - perpetuity) < 0.01

    def test_growing_annuity_rejects_r_equals_g(self):
        with pytest.raises(ValueError, match="r == g"):
            ENGINE.growing_annuity_pv(100, 0.05, 0.05, 10)


# ── P2: Multi-stage Dividend Discount Model ────────────────────────────────

class TestExam2P2_DDM:
    """
    Blue Inc. — dividends [0 (t=0), 0 (t=1), 6 (t=2), 5 (t=3), 2 (t=4)],
    then 2% growth forever from year 5. Cost of equity = 11%.

    P_4 = D_5 / (r-g) = 2(1.02)/0.09 = 22.67
    P_3 = (2 + 22.67) / 1.11 = 22.225
    P_0 = 6/1.11² + 5/1.11³ + (2+22.67)/1.11⁴ = 24.78
    Capital gain rate from P_3 to P_4 = 0.0198
    """

    RE = 0.11
    G_TERMINAL = 0.02
    DIV_4 = 2.0

    def test_terminal_price_at_end_of_year_4(self):
        """P_4 = D_5/(r-g) where D_5 = D_4·(1+g)."""
        p4 = ENGINE.growing_perpetuity_pv(
            cash_flow=self.DIV_4 * (1 + self.G_TERMINAL),
            discount_rate=self.RE,
            growth_rate=self.G_TERMINAL,
        )
        assert abs(p4 - 22.67) < 0.01

    def test_price_today_via_npv_of_dividend_stream(self):
        """
        P_0 reads exactly as NPV([CF_0, CF_1, ..., CF_4], r) where the last
        cash flow bundles the year-4 dividend with the terminal price P_4.
        """
        p4 = self.DIV_4 * (1 + self.G_TERMINAL) / (self.RE - self.G_TERMINAL)
        dividend_stream = [0.0, 0.0, 6.0, 5.0, self.DIV_4 + p4]
        p0 = ENGINE.npv(dividend_stream, self.RE)
        assert abs(p0 - 24.78) < 0.01

    def test_capital_gain_rate_p3_to_p4(self):
        """Capital gain rate ≈ r − dividend yield ≈ 11% − 9% ≈ 2% (= g)."""
        p4 = 22.67
        p3 = (self.DIV_4 + p4) / (1 + self.RE)
        rate = capital_gain_rate(p4, p3)
        assert abs(rate - 0.0198) < 0.001

    def test_capital_gain_rate_rejects_zero_base(self):
        with pytest.raises(ValueError, match="zero base"):
            capital_gain_rate(10.0, 0.0)


# ── P3: Beta from correlation + CAPM ───────────────────────────────────────

class TestExam2P3_BetaCAPM:
    """
    Risk-free rate 5%, market expected return 13%, market vol 18%.
      Monsters:        σ=24%, ρ=0.60   →  β ≈ 0.80
      California Gold: σ=32%, ρ=-0.70  →  β ≈ -1.244, required return ≈ -5%
    """

    RF = 0.05
    R_M = 0.13
    SIGMA_M = 0.18

    def test_monsters_beta_is_0_8(self):
        beta = beta_from_correlation(
            correlation_with_market=0.60,
            asset_volatility=0.24,
            market_volatility=self.SIGMA_M,
        )
        assert abs(beta - 0.80) < 0.01

    def test_california_gold_required_return_via_capm_with_negative_beta(self):
        beta = beta_from_correlation(-0.70, 0.32, self.SIGMA_M)
        # MRP = E(R_M) − R_F
        required_return = capm_cost_of_equity(self.RF, beta, self.R_M - self.RF)
        # Exam says "closest to -5%"; exact value is -4.96%
        assert abs(required_return - (-0.05)) < 0.005

    def test_beta_from_correlation_rejects_zero_market_vol(self):
        with pytest.raises(ValueError, match="market_volatility"):
            beta_from_correlation(0.5, 0.10, 0.0)


# ── P4: Two-asset portfolio expected return / volatility / MVP ─────────────

class TestExam2P4_TwoAssetPortfolio:
    """
    X and Y with E(R)=[0.16, 0.32], σ=[0.10, 0.24], ρ_XY = -1.
      Equal-weight portfolio:  E(R)=0.24, σ=0.07
    Y and Z with σ=[0.24, 0.15], ρ_YZ = 0.3.
      Minimum-variance weight on Y: ω_Y = 0.20
    """

    def test_equal_weight_XY_expected_return(self):
        e_r = 0.5 * 0.16 + 0.5 * 0.32
        assert abs(e_r - 0.24) < 1e-9

    def test_equal_weight_XY_volatility_with_perfect_negative_correlation(self):
        wx = wy = 0.5
        sx, sy = 0.10, 0.24
        rho = -1.0
        var = (wx ** 2) * sx ** 2 + (wy ** 2) * sy ** 2 + 2 * wx * wy * rho * sx * sy
        assert abs(var - 0.0049) < 1e-6
        assert abs(math.sqrt(var) - 0.07) < 1e-6

    def test_min_variance_weight_YZ(self):
        w_y, w_z = min_variance_two_asset_weight(
            sigma_a=0.24, sigma_b=0.15, correlation=0.3,
        )
        assert abs(w_y - 0.20) < 0.001
        assert abs(w_z - 0.80) < 0.001
        assert abs(w_y + w_z - 1.0) < 1e-12

    def test_min_variance_weight_rejects_invalid_correlation(self):
        with pytest.raises(ValueError, match="correlation"):
            min_variance_two_asset_weight(0.10, 0.20, correlation=1.5)


# ── P5: Idiosyncratic variance + Sharpe ─────────────────────────────────────

class TestExam2P5_IdioAndSharpe:
    """
    Market: σ_M = 0.31, R_M = 0.13, R_f = 0.05.
      Fund A: R̄=0.25, β=1.3, σ²=0.37  →  idio var ≈ 0.2076, Sharpe ≈ 0.3287
      Fund B: R̄=0.16, β=0.9, σ²=0.26  →  idio var ≈ 0.1821, Sharpe ≈ 0.2157
    """

    SIGMA_M_SQ = 0.31 ** 2  # 0.0961

    def test_fund_a_idiosyncratic_variance(self):
        v = idiosyncratic_variance(total_variance=0.37, beta=1.3, market_variance=self.SIGMA_M_SQ)
        assert abs(v - 0.2076) < 0.001

    def test_fund_b_idiosyncratic_variance(self):
        v = idiosyncratic_variance(total_variance=0.26, beta=0.9, market_variance=self.SIGMA_M_SQ)
        assert abs(v - 0.1821) < 0.001

    def test_idiosyncratic_variance_clamps_at_zero(self):
        """Inconsistent inputs (β too high for σ_i²) should give 0, not negative."""
        v = idiosyncratic_variance(total_variance=0.05, beta=2.0, market_variance=0.10)
        assert v == 0.0

    def test_fund_a_sharpe_ratio(self):
        sh = sharpe_from_stats(expected_return=0.25, risk_free_rate=0.05, std_dev=math.sqrt(0.37))
        assert abs(sh - 0.3287) < 0.001

    def test_fund_b_sharpe_ratio(self):
        sh = sharpe_from_stats(expected_return=0.16, risk_free_rate=0.05, std_dev=math.sqrt(0.26))
        assert abs(sh - 0.2157) < 0.001

    def test_fund_a_beats_fund_b_on_sharpe(self):
        """Despite higher total variance, Fund A has the better risk-adjusted return."""
        sh_a = sharpe_from_stats(0.25, 0.05, math.sqrt(0.37))
        sh_b = sharpe_from_stats(0.16, 0.05, math.sqrt(0.26))
        assert sh_a > sh_b

    def test_sharpe_returns_zero_for_zero_std(self):
        assert sharpe_from_stats(0.10, 0.05, 0.0) == 0.0
