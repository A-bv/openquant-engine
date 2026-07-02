"""
Tests for openquant/common/utils.py

Every function tested against known values.
EPFL fixtures used as ground truth where applicable.
"""

import numpy as np
import pandas as pd
import pytest

from openquant.common import (
    log_returns,
    simple_returns,
    annualise_return,
    annualise_vol,
    annualise_returns_series,
    annualise_vol_series,
    bootstrap_ci,
    sharpe_ratio,
    sharpe_ratio_with_ci,
    cagr,
    winsorize_series,
    median_growth_rate,
    format_currency,
    format_percent,
    validate_weights,
)


# ── log_returns ───────────────────────────────────────────────────────────────

class TestLogReturns:

    def test_known_values(self, simple_prices, known_returns):
        """Log returns match manually verified values."""
        result = log_returns(simple_prices)
        np.testing.assert_allclose(
            result.values,
            known_returns.values,
            rtol=1e-5,
        )

    def test_length(self, simple_prices):
        """Returns series has one fewer observation than prices."""
        result = log_returns(simple_prices)
        assert len(result) == len(simple_prices) - 1

    def test_raises_on_too_few_observations(self):
        """Raises ValueError with single price."""
        with pytest.raises(ValueError, match="at least 2"):
            log_returns(pd.Series([100.0]))

    def test_raises_on_non_positive_prices(self):
        """Raises ValueError when prices contain zero or negative."""
        prices = pd.Series([100.0, -50.0, 80.0])
        with pytest.raises(ValueError, match="non-positive"):
            log_returns(prices)

    def test_first_return_is_ln_ratio(self):
        """First return is ln(p1/p0)."""
        prices = pd.Series([100.0, 110.0, 90.0])
        result = log_returns(prices)
        expected_first = np.log(110.0 / 100.0)
        assert abs(result.iloc[0] - expected_first) < 1e-10


# ── annualise ─────────────────────────────────────────────────────────────────

class TestAnnualise:

    def test_annualise_return_zero(self):
        """Zero daily return gives zero annualised return."""
        assert annualise_return(0.0) == 0.0

    def test_annualise_vol_scaling(self):
        """Annualised vol = daily vol × sqrt(252)."""
        daily_vol = 0.01
        expected = daily_vol * np.sqrt(252)
        assert abs(annualise_vol(daily_vol) - expected) < 1e-10

    def test_annualise_returns_series(self):
        """
        annualise_returns_series treats its input as LOG returns, so the
        correct annualisation is exp(mean * trading_days) - 1, not the
        (1 + r)^trading_days - 1 used by annualise_return for simple returns.
        """
        returns = pd.Series([0.001] * 252)
        result = annualise_returns_series(returns)
        expected = np.expm1(0.001 * 252)
        assert abs(result - expected) < 1e-10


# ── EPFL portfolio — annualised stats ────────────────────────────────────────

class TestEPFLAnnualised:

    def test_epfl_h2_mean_return(self, epfl_h2):
        """
        EPFL_H2 ground truth: mean annual return = 0.10 for each asset.
        """
        returns_matrix = epfl_h2["returns"]
        for i in range(3):
            asset_returns = pd.Series(returns_matrix[:, i])
            mean = asset_returns.mean()
            assert abs(mean - epfl_h2["mean_return"]) < 1e-4, (
                f"Asset {i} mean return {mean:.6f} != {epfl_h2['mean_return']}"
            )

    def test_epfl_h2_variance(self, epfl_h2):
        """
        EPFL_H2 ground truth: variance = 0.018 for each asset (ddof=1).
        """
        returns_matrix = epfl_h2["returns"]
        for i in range(3):
            asset_returns = pd.Series(returns_matrix[:, i])
            var = asset_returns.var(ddof=1)
            assert abs(var - epfl_h2["variance"]) < 1e-4, (
                f"Asset {i} variance {var:.6f} != {epfl_h2['variance']}"
            )

    def test_epfl_h2_sd(self, epfl_h2):
        """
        EPFL_H2 ground truth: SD = 0.1342 for each asset.
        """
        returns_matrix = epfl_h2["returns"]
        for i in range(3):
            asset_returns = pd.Series(returns_matrix[:, i])
            sd = asset_returns.std(ddof=1)
            assert abs(sd - epfl_h2["sd"]) < 1e-3, (
                f"Asset {i} SD {sd:.6f} != {epfl_h2['sd']}"
            )


# ── bootstrap_ci ──────────────────────────────────────────────────────────────

class TestBootstrapCI:

    def test_ci_contains_true_value(self):
        """Bootstrap CI should contain the true statistic most of the time."""
        np.random.seed(42)
        data = np.random.normal(0.001, 0.02, 252)
        mean_fn = lambda x: np.mean(x)
        lower, upper = bootstrap_ci(data, mean_fn, n_resamples=500)
        true_mean = np.mean(data)
        assert lower < true_mean < upper

    def test_ci_lower_less_than_upper(self):
        """Lower bound must be less than upper bound."""
        data = np.random.normal(0, 1, 100)
        lower, upper = bootstrap_ci(data, np.mean, n_resamples=100)
        assert lower < upper

    def test_ci_reproducible(self):
        """Same random state produces same CI."""
        data = np.random.normal(0, 1, 100)
        r1 = bootstrap_ci(data, np.mean, random_state=42)
        r2 = bootstrap_ci(data, np.mean, random_state=42)
        assert r1 == r2


# ── sharpe_ratio ──────────────────────────────────────────────────────────────

class TestSharpeRatio:

    def test_positive_returns_positive_sharpe(self):
        """Positive mean return above rf gives positive Sharpe."""
        returns = pd.Series([0.001] * 252)
        sr = sharpe_ratio(returns, risk_free_rate=0.0)
        assert sr > 0

    def test_zero_vol_returns_zero(self):
        """Zero volatility returns zero Sharpe (avoids division by zero)."""
        returns = pd.Series([0.001] * 252)
        # Make returns constant (zero vol after small perturbation removed)
        returns_const = pd.Series([0.0] * 252)
        sr = sharpe_ratio(returns_const, risk_free_rate=0.0)
        assert sr == 0.0

    def test_sharpe_with_ci_returns_three_values(self):
        """sharpe_ratio_with_ci returns (sr, lower, upper)."""
        returns = pd.Series(np.random.normal(0.001, 0.02, 252))
        result = sharpe_ratio_with_ci(returns, n_resamples=100)
        assert len(result) == 3
        sr, lower, upper = result
        assert lower < upper


# ── growth rate utilities ─────────────────────────────────────────────────────

class TestGrowthRates:

    def test_cagr_known_value(self):
        """CAGR from 100 to 200 over 10 years = 7.177%."""
        result = cagr(100, 200, 10)
        expected = 2 ** (1/10) - 1  # ≈ 0.07177
        assert abs(result - expected) < 1e-6

    def test_cagr_raises_on_zero_start(self):
        """Raises ValueError when start_value is zero."""
        with pytest.raises(ValueError, match="positive"):
            cagr(0, 100, 5)

    def test_cagr_raises_on_zero_years(self):
        """Raises ValueError when years is zero."""
        with pytest.raises(ValueError, match="positive"):
            cagr(100, 200, 0)

    def test_winsorize_clips_extremes(self):
        """Winsorize clips values outside quantile range."""
        values = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
        result = winsorize_series(values, 0.1, 0.9)
        assert result.max() < 100

    def test_median_growth_rate_stable_series(self):
        """Stable 10% annual growth gives approximately 10% median."""
        values = pd.Series([100, 110, 121, 133.1, 146.41])
        result = median_growth_rate(values, winsorize=False)
        assert abs(result - 0.10) < 1e-4


# ── formatting ────────────────────────────────────────────────────────────────

class TestFormatting:

    def test_format_billions(self):
        assert format_currency(1_234_567_890) == "$1.23B"

    def test_format_millions(self):
        assert format_currency(456_780_000) == "$456.78M"

    def test_format_thousands(self):
        assert format_currency(12_340) == "$12.34K"

    def test_format_negative(self):
        assert format_currency(-1_000_000_000) == "-$1.00B"

    def test_format_percent(self):
        assert format_percent(0.1234) == "12.3%"

    def test_format_percent_decimals(self):
        assert format_percent(0.1234, decimals=2) == "12.34%"


# ── validate_weights ──────────────────────────────────────────────────────────

class TestValidateWeights:

    def test_valid_weights(self):
        """Weights summing to 1.0 pass validation."""
        assert validate_weights([0.3, 0.3, 0.4]) is True

    def test_invalid_weights_raise(self):
        """Weights not summing to 1.0 raise ValueError."""
        with pytest.raises(ValueError, match="sum to 1.0"):
            validate_weights([0.3, 0.3, 0.3])

    def test_tolerance_respected(self):
        """Weights within tolerance pass."""
        assert validate_weights([0.3333, 0.3333, 0.3334]) is True
