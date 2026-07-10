"""
OpenQuant — Portfolio risk & diversification engine tests.

Two jobs:
  1. Pin the multi-asset covariance engine against the EPFL Sample Exam 2
     answer key (P4) — the same oracle that already governs `openquant/common/utils` and
     `openquant/valuation/wacc`. The 2-asset reduction must reproduce the exam's worked values.
  2. Verify the "effective number of bets" deliverable behaves exactly as the
     closed form predicts on the canonical equal-weight / equal-vol case.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from openquant.common import min_variance_two_asset_weight
from openquant.portfolio import (
    analyse_diversification,
    covariance_from_vols_and_corr,
    diversification_ratio,
    effective_number_of_bets,
    independent_volatility,
    min_variance_weights,
    portfolio_volatility,
    risk_contributions,
)

# ── 1. Pin against EPFL Sample Exam 2 — Problem 4 ──────────────────────────────

class TestExam2P4_ReducesToTwoAsset:
    """
    X and Y: σ = [0.10, 0.24], ρ_XY = -1, equal weight  →  σ_p = 0.07.
    Y and Z: σ = [0.24, 0.15], ρ_YZ = 0.3              →  ω_Y = 0.20 (MVP).

    The full matrix engine must reproduce both, so the live-data path is
    governed by the same exam ground truth as the rest of OpenQuant.
    """

    def test_equal_weight_XY_volatility_with_perfect_negative_correlation(self):
        cov = covariance_from_vols_and_corr(
            vols=[0.10, 0.24],
            corr=[[1.0, -1.0], [-1.0, 1.0]],
        )
        assert abs(portfolio_volatility([0.5, 0.5], cov) - 0.07) < 1e-6

    def test_min_variance_weight_YZ_matches_closed_form(self):
        cov = covariance_from_vols_and_corr(
            vols=[0.24, 0.15],
            corr=[[1.0, 0.3], [0.3, 1.0]],
        )
        w = min_variance_weights(cov)
        assert abs(w[0] - 0.20) < 1e-6
        assert abs(w[1] - 0.80) < 1e-6

    def test_matrix_mvp_agrees_with_two_asset_helper(self):
        """The n-asset MVP must collapse to the EPFL two-asset closed form."""
        cov = covariance_from_vols_and_corr(
            vols=[0.24, 0.15],
            corr=[[1.0, 0.3], [0.3, 1.0]],
        )
        w_matrix = min_variance_weights(cov)
        w_y, w_z = min_variance_two_asset_weight(0.24, 0.15, 0.3)
        assert abs(w_matrix[0] - w_y) < 1e-9
        assert abs(w_matrix[1] - w_z) < 1e-9


# ── 2. Effective number of bets — canonical closed form ────────────────────────

def _equicorrelated_cov(n: int, sigma: float, rho: float):
    corr = np.full((n, n), rho)
    np.fill_diagonal(corr, 1.0)
    return covariance_from_vols_and_corr([sigma] * n, corr)


class TestEffectiveBets:
    """
    For n equal-weight assets, equal vol σ, pairwise correlation ρ:
        N_eff = DR² = n / (1 + (n-1)·ρ)
    """

    def test_eight_correlated_tech_names_collapse_to_about_1_4_bets(self):
        cov = _equicorrelated_cov(8, sigma=0.35, rho=0.7)
        # n / (1 + (n-1)ρ) = 8 / (1 + 7*0.7) = 8 / 5.9 ≈ 1.356
        assert abs(effective_number_of_bets(None, cov) - 8 / 5.9) < 1e-6

    def test_uncorrelated_book_gives_full_count(self):
        cov = _equicorrelated_cov(8, sigma=0.35, rho=0.0)
        assert abs(effective_number_of_bets(None, cov) - 8.0) < 1e-6

    def test_perfectly_correlated_book_is_one_bet(self):
        cov = _equicorrelated_cov(8, sigma=0.35, rho=1.0)
        assert abs(effective_number_of_bets(None, cov) - 1.0) < 1e-6

    def test_independent_vol_below_real_vol_when_positively_correlated(self):
        cov = _equicorrelated_cov(8, sigma=0.35, rho=0.7)
        assert independent_volatility(None, cov) < portfolio_volatility(None, cov)

    def test_diversification_ratio_at_least_one(self):
        cov = _equicorrelated_cov(5, sigma=0.30, rho=0.4)
        assert diversification_ratio(None, cov) >= 1.0 - 1e-12


# ── 3. Risk contributions ──────────────────────────────────────────────────────

class TestRiskContributions:
    def test_contributions_sum_to_one(self):
        cov = _equicorrelated_cov(4, sigma=0.30, rho=0.5)
        rc = risk_contributions([0.4, 0.3, 0.2, 0.1], cov)
        assert abs(rc.sum() - 1.0) < 1e-9

    def test_high_vol_position_can_dominate_risk_beyond_its_weight(self):
        # Asset 0 is far more volatile; at equal weight it should carry the
        # larger risk share — the "10% of capital, 25% of risk" phenomenon.
        cov = covariance_from_vols_and_corr(
            vols=[0.60, 0.15, 0.15],
            corr=[[1.0, 0.2, 0.2], [0.2, 1.0, 0.2], [0.2, 0.2, 1.0]],
        )
        rc = risk_contributions(None, cov)  # equal weight
        assert rc[0] > rc[1]
        assert rc[0] > 1.0 / 3  # more risk share than capital share


# ── 4. End-to-end on synthetic return series ───────────────────────────────────

class TestAnalyseDiversification:
    def test_report_fields_are_coherent(self):
        rng = np.random.default_rng(0)
        market = rng.normal(0.0004, 0.01, 800)
        # three names sharing a strong common factor → few effective bets
        data = {
            t: market + rng.normal(0.0, 0.004, 800)
            for t in ["AAA", "BBB", "CCC"]
        }
        returns = pd.DataFrame(data)
        report = analyse_diversification(returns)

        assert report.n_holdings == 3
        assert 1.0 <= report.effective_bets <= 3.0
        assert report.independent_vol <= report.portfolio_vol + 1e-9
        assert abs(report.risk_contributions.sum() - 1.0) < 1e-9
        assert len(report.summary_lines()) >= 4
        assert report.to_dict()["n_holdings"] == 3

    def test_requires_at_least_two_holdings(self):
        returns = pd.DataFrame({"AAA": [0.01, -0.02, 0.005]})
        with pytest.raises(ValueError, match="at least 2"):
            analyse_diversification(returns)
