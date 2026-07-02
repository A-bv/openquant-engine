"""
OpenQuant — Shared test fixtures.

Ground truth values verified against:
1. EPFL Introduction to Finance — Exam 1, Problem 2
2. EPFL_H2_exemple_Portfolio_volatility.xlsx (professor's workbook)
3. PortfolioSD_yahooapibroken.xlsm (verified covariance values)

These fixtures are the numerical source of truth for all math tests.
If any test fails against these values, the implementation is wrong.
"""

import numpy as np
import pandas as pd
import pytest


# ── EPFL Exam 1 Problem 2 — Valuation fixture ────────────────────────────────

@pytest.fixture
def epfl_exam1():
    """
    EPFL Introduction to Finance — Final Exam, Problem 2.

    A 4-year project with known FCF, known WACC derivation via CAPM,
    known NPV. Used to verify FCF computation, WACC, and DCF math.

    Verified values:
    - Unlevered beta = 1.50 (average of firm A and firm B)
    - Required return = 8% + 1.50 × 8% = 20%
    - PVTS = 876,641
    """
    return {
        "fcf": [-24_000_000, 8_400_000, 9_150_000, 11_100_000, 14_850_000],
        "equity_beta_a": 1.99,
        "equity_beta_b": 2.48,
        "leverage_a": 0.33,
        "leverage_b": 0.50,
        "tax_rate": 0.35,
        "unlevered_beta": 1.50,
        "risk_free_rate": 0.08,
        "market_risk_premium": 0.08,
        "required_return": 0.20,  # 8% + 1.50 × 8% = 20%
        "initial_investment": 24_000_000,
        "debt_initial": 12_000_000,  # 50% of initial investment
        "borrowing_rate": 0.10,
        "pvts": 876_641,
    }


# ── EPFL_H2_exemple — Portfolio fixture ──────────────────────────────────────

@pytest.fixture
def epfl_h2():
    """
    EPFL_H2_exemple_Portfolio_volatility.xlsx — professor's workbook.

    Three assets: North Air, West Air, Tex Oil.
    6 years of annual returns.

    All values verified by Python recomputation and match the workbook exactly.
    """
    returns = np.array([
        [0.21,  0.09, -0.02],
        [0.30,  0.21, -0.05],
        [0.07,  0.07,  0.09],
        [-0.05, -0.02,  0.21],
        [-0.02, -0.05,  0.30],
        [0.09,  0.30,  0.07],
    ])

    return {
        "returns": returns,
        "labels": ["North Air", "West Air", "Tex Oil"],
        "mean_return": 0.10,          # each asset, verified
        "variance": 0.018,            # each asset, ddof=1, verified
        "sd": 0.1342,                 # each asset, verified
        "correlation_01": 0.6200,     # North Air vs West Air
        "correlation_02": -0.9233,    # North Air vs Tex Oil
        "correlation_12": -0.7133,    # West Air vs Tex Oil
        # Portfolio at w = [0, 0.5, 0.5]
        "portfolio_weights": np.array([0.0, 0.5, 0.5]),
        "portfolio_sd": 0.050794,     # verified to 6 decimal places
        "portfolio_return": 0.10,     # (0×0.10) + (0.5×0.10) + (0.5×0.10)
    }


# ── PortfolioSD_yahooapibroken — Covariance fixture ──────────────────────────

@pytest.fixture
def portfolio_sd_verified():
    """
    Verified covariance values from PortfolioSD_yahooapibroken.xlsm.

    AMZN monthly data 2011-2014, manually verified.
    Used to cross-check covariance computation.
    """
    return {
        "gspc_monthly_sd": 0.02381,
        "amzn_monthly_sd": 0.07450,
        "cov_gspc_amzn": 0.001233,
        "correlation": 0.001233 / (0.02381 * 0.07450),  # ≈ 0.695
    }


# ── Simple price series for unit tests ───────────────────────────────────────

@pytest.fixture
def simple_prices():
    """Simple price series with known returns for unit testing."""
    prices = pd.Series(
        [100.0, 105.0, 98.0, 110.0, 108.0],
        index=pd.date_range("2020-01-01", periods=5, freq="D"),
        name="price",
    )
    return prices


@pytest.fixture
def known_returns():
    """
    Known log returns computed from simple_prices.
    Verified manually.
    """
    return pd.Series([
        np.log(105 / 100),   # 0.048790
        np.log(98 / 105),    # -0.068993
        np.log(110 / 98),    # 0.115534
        np.log(108 / 110),   # -0.018349
    ])
