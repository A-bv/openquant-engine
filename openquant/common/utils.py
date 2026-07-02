"""
OpenQuant — Shared utility functions.

Pure Python. No external dependencies beyond numpy and pandas.
No Streamlit imports. Fully testable in isolation.

All functions used across multiple core modules live here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Union

from openquant.config import (
    DEFAULT_RISK_FREE_RATE,
    DEFAULT_TRADING_DAYS,
    BOOTSTRAP_RESAMPLES,
    BETA_CONFIDENCE_LEVEL,
    GROWTH_WINSOR_LOW,
    GROWTH_WINSOR_HIGH,
)


# ── Return computation ────────────────────────────────────────────────────────

def log_returns(prices: pd.Series) -> pd.Series:
    """
    Compute log returns from a price series.

    Uses ln(P_t / P_{t-1}) — time-additive, approximately normal,
    industry standard for multi-period analysis.

    Args:
        prices: Series of adjusted closing prices, indexed by date.
                Must have at least 2 observations.

    Returns:
        Series of log returns with the same index (first row is NaN, dropped).

    Raises:
        ValueError: If prices has fewer than 2 observations or contains
                    non-positive values.

    Example:
        >>> prices = pd.Series([100, 105, 98, 110])
        >>> log_returns(prices)
        0.048790   # ln(105/100)
        -0.068993  # ln(98/105)
        0.115534   # ln(110/98)
    """
    if len(prices) < 2:
        raise ValueError(
            f"Need at least 2 price observations to compute returns. "
            f"Got {len(prices)}."
        )
    if (prices <= 0).any():
        raise ValueError(
            "Price series contains non-positive values. "
            "Ensure you are using adjusted closing prices."
        )
    return np.log(prices / prices.shift(1)).dropna()


def simple_returns(prices: pd.Series) -> pd.Series:
    """
    Compute simple returns from a price series.

    Uses P_t / P_{t-1} - 1. Shown in UI for readability alongside
    log returns used internally for all calculations.

    Args:
        prices: Series of adjusted closing prices.

    Returns:
        Series of simple returns (first row dropped).

    Raises:
        ValueError: If prices has fewer than 2 observations.
    """
    if len(prices) < 2:
        raise ValueError(
            f"Need at least 2 price observations. Got {len(prices)}."
        )
    return prices.pct_change().dropna()


# ── Two-asset portfolio helper (used in EPFL Sample Exam 2 problems) ─────────

def min_variance_two_asset_weight(
    sigma_a: float,
    sigma_b: float,
    correlation: float,
) -> tuple[float, float]:
    """
    Closed-form minimum-variance weights for a two-asset portfolio.

    EPFL formula sheet:
        ω_A = (σ_B² − ρ_AB σ_A σ_B) / (σ_A² + σ_B² − 2 ρ_AB σ_A σ_B)
        ω_B = 1 − ω_A

    EPFL Sample Exam 2 Problem 4-Q4b (assets Y and Z):
        σ_Y = 0.24, σ_Z = 0.15, ρ_YZ = 0.3  →  ω_Y = 0.2, ω_Z = 0.8

    Returns can be negative (implying a short sale) when one asset is much
    less volatile and the pair is strongly positively correlated.

    NOTE: This is the only piece of full portfolio theory remaining in
    OpenQuant. The full portfolio-construction module (efficient frontier,
    five-portfolio comparison) was removed when the project was refocused
    on equity valuation only. The closed-form weight is kept because it
    appears on the EPFL Sample Exam 2 answer key and is needed by the
    `test_epfl_exam2.py` test of that problem.
    """
    if sigma_a < 0 or sigma_b < 0:
        raise ValueError("volatilities must be non-negative")
    if not -1.0 <= correlation <= 1.0:
        raise ValueError(f"correlation {correlation} not in [-1, 1]")
    denominator = sigma_a ** 2 + sigma_b ** 2 - 2 * correlation * sigma_a * sigma_b
    if denominator <= 0:
        return 0.5, 0.5
    w_a = (sigma_b ** 2 - correlation * sigma_a * sigma_b) / denominator
    return w_a, 1.0 - w_a


# ── Annualisation ─────────────────────────────────────────────────────────────

def annualise_return(
    daily_return: float,
    trading_days: int = DEFAULT_TRADING_DAYS,
) -> float:
    """
    Annualise a daily return using compounding.

    Args:
        daily_return: Mean daily log return.
        trading_days: Number of trading days per year. Default 252.

    Returns:
        Annualised return as a decimal (e.g. 0.12 for 12%).

    Example:
        >>> annualise_return(0.0004)
        0.1040  # approximately 10.4%
    """
    return (1 + daily_return) ** trading_days - 1


def annualise_vol(
    daily_vol: float,
    trading_days: int = DEFAULT_TRADING_DAYS,
) -> float:
    """
    Annualise a daily volatility using the square-root-of-time rule.

    Args:
        daily_vol: Daily standard deviation of returns.
        trading_days: Number of trading days per year. Default 252.

    Returns:
        Annualised volatility as a decimal.

    Example:
        >>> annualise_vol(0.01)
        0.1587  # approximately 15.9%
    """
    return daily_vol * np.sqrt(trading_days)


def annualise_returns_series(
    returns: pd.Series,
    trading_days: int = DEFAULT_TRADING_DAYS,
) -> float:
    """
    Compute annualised return from a series of daily log returns.

    Log returns are time-additive, so the correct annualisation is
    exp(mean_daily * trading_days) - 1, NOT (1 + mean_daily)^trading_days - 1
    (that formula assumes simple returns).

    Args:
        returns: Series of daily log returns.
        trading_days: Trading days per year.

    Returns:
        Annualised return as a decimal.
    """
    mean_daily = float(returns.mean())
    return float(np.expm1(mean_daily * trading_days))


def annualise_vol_series(
    returns: pd.Series,
    trading_days: int = DEFAULT_TRADING_DAYS,
) -> float:
    """
    Compute annualised volatility from a series of daily log returns.

    Args:
        returns: Series of daily log returns.
        trading_days: Trading days per year.

    Returns:
        Annualised volatility as a decimal.
    """
    return annualise_vol(returns.std(ddof=1), trading_days)


# ── Bootstrap confidence intervals ───────────────────────────────────────────

def bootstrap_ci(
    data: Union[np.ndarray, pd.Series],
    statistic_fn: callable,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    confidence_level: float = BETA_CONFIDENCE_LEVEL,
    random_state: int = 42,
) -> tuple[float, float]:
    """
    Compute bootstrap confidence interval for any statistic.

    Used primarily for Sharpe ratio CI — showing users that a single
    Sharpe number hides significant estimation uncertainty.

    Args:
        data: Array or Series of observations (e.g. daily returns).
        statistic_fn: Function that takes an array and returns a scalar.
                      e.g. lambda x: np.mean(x) / np.std(x, ddof=1)
        n_resamples: Number of bootstrap resamples. Default 1000.
        confidence_level: CI level. Default 0.95 (95% CI).
        random_state: Random seed for reproducibility.

    Returns:
        Tuple of (lower_bound, upper_bound).

    Example:
        >>> returns = np.random.normal(0.001, 0.02, 252)
        >>> sharpe_fn = lambda x: np.mean(x) / np.std(x, ddof=1) * np.sqrt(252)
        >>> bootstrap_ci(returns, sharpe_fn)
        (0.32, 1.87)  # wide CI — typical for 1 year of data
    """
    rng = np.random.default_rng(random_state)
    data_array = np.asarray(data)
    n = len(data_array)

    bootstrap_stats = np.array([
        statistic_fn(rng.choice(data_array, size=n, replace=True))
        for _ in range(n_resamples)
    ])

    alpha = 1 - confidence_level
    lower = np.percentile(bootstrap_stats, 100 * alpha / 2)
    upper = np.percentile(bootstrap_stats, 100 * (1 - alpha / 2))

    return float(lower), float(upper)


def sharpe_from_stats(
    expected_return: float,
    risk_free_rate: float,
    std_dev: float,
) -> float:
    """
    Sharpe ratio from summary statistics (no return series needed).

    EPFL formula sheet:
        Sh = (E(Rp) − Rf) / SD(Rp)

    Use this when only mean/SD are available (e.g. fund fact sheets,
    textbook problems). For a daily return series, use sharpe_ratio() which
    annualises internally.

    EPFL Sample Exam 2 Problem 5-Q5b:
        Fund A: E=0.25, Rf=0.05, SD=√0.37 ≈ 0.6083  →  Sh ≈ 0.3287
        Fund B: E=0.16, Rf=0.05, SD=√0.26 ≈ 0.5099  →  Sh ≈ 0.2157
    """
    if std_dev <= 0:
        return 0.0
    return (expected_return - risk_free_rate) / std_dev


def capital_gain_rate(price_new: float, price_old: float) -> float:
    """
    Single-period capital gain rate: (P_t − P_{t-1}) / P_{t-1}.

    EPFL formula sheet:
        capital gain rate = (P_t − P_{t-1}) / P_{t-1}

    EPFL Sample Exam 2 Problem 2-Q2b:
        P_3 = 22.23, P_4 = 22.67  →  gain rate ≈ 0.0198
    """
    if price_old == 0:
        raise ValueError("Cannot compute capital gain rate from zero base price")
    return (price_new - price_old) / price_old


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    trading_days: int = DEFAULT_TRADING_DAYS,
) -> float:
    """
    Compute annualised Sharpe ratio.

    Formula: (annualised_return - rf) / annualised_volatility
    From EPFL formula sheet: Sh = (E(Rp) - Rf) / SD(Rp)

    Args:
        returns: Series of daily log returns.
        risk_free_rate: Annual risk-free rate. Default 4.5%.
        trading_days: Trading days per year. Default 252.

    Returns:
        Annualised Sharpe ratio.
    """
    ann_return = annualise_returns_series(returns, trading_days)
    ann_vol = annualise_vol_series(returns, trading_days)

    if ann_vol == 0:
        return 0.0

    return (ann_return - risk_free_rate) / ann_vol


def sharpe_ratio_with_ci(
    returns: pd.Series,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    trading_days: int = DEFAULT_TRADING_DAYS,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    confidence_level: float = BETA_CONFIDENCE_LEVEL,
) -> tuple[float, float, float]:
    """
    Compute Sharpe ratio with bootstrap confidence interval.

    Args:
        returns: Series of daily log returns.
        risk_free_rate: Annual risk-free rate.
        trading_days: Trading days per year.
        n_resamples: Bootstrap resamples.
        confidence_level: CI level.

    Returns:
        Tuple of (sharpe, ci_lower, ci_upper).
    """
    sr = sharpe_ratio(returns, risk_free_rate, trading_days)

    def _sharpe_fn(r: np.ndarray) -> float:
        s = pd.Series(r)
        return sharpe_ratio(s, risk_free_rate, trading_days)

    ci_lower, ci_upper = bootstrap_ci(
        returns,
        _sharpe_fn,
        n_resamples=n_resamples,
        confidence_level=confidence_level,
    )

    return sr, ci_lower, ci_upper


# ── Growth rate utilities ─────────────────────────────────────────────────────

def cagr(
    start_value: float,
    end_value: float,
    years: int,
) -> float:
    """
    Compute Compound Annual Growth Rate.

    Args:
        start_value: Starting value.
        end_value: Ending value.
        years: Number of years.

    Returns:
        CAGR as a decimal.

    Raises:
        ValueError: If start_value is zero or negative, or years is zero.
    """
    if start_value <= 0:
        raise ValueError(
            f"start_value must be positive. Got {start_value}."
        )
    if years <= 0:
        raise ValueError(
            f"years must be positive. Got {years}."
        )
    return (end_value / start_value) ** (1 / years) - 1


def winsorize_series(
    values: pd.Series,
    lower_quantile: float = GROWTH_WINSOR_LOW,
    upper_quantile: float = GROWTH_WINSOR_HIGH,
) -> pd.Series:
    """
    Winsorize a series by clipping at specified quantiles.

    Used for FCF growth rate defaults — prevents extreme historical
    values from producing absurd scenario assumptions.

    Args:
        values: Series to winsorize.
        lower_quantile: Lower clip quantile. Default 5th percentile.
        upper_quantile: Upper clip quantile. Default 95th percentile.

    Returns:
        Winsorized series.
    """
    lower = values.quantile(lower_quantile)
    upper = values.quantile(upper_quantile)
    return values.clip(lower=lower, upper=upper)


def median_growth_rate(
    values: pd.Series,
    winsorize: bool = True,
    lower_quantile: float = GROWTH_WINSOR_LOW,
    upper_quantile: float = GROWTH_WINSOR_HIGH,
) -> float:
    """
    Compute median year-over-year growth rate from a value series.

    Used as default FCF growth assumption — more robust than mean
    for volatile FCF series.

    Args:
        values: Series of annual values (e.g. FCF over 5 years).
        winsorize: Whether to winsorize before computing median.
        lower_quantile: Lower winsorize quantile.
        upper_quantile: Upper winsorize quantile.

    Returns:
        Median YoY growth rate as a decimal.
    """
    yoy_growth = values.pct_change().dropna()

    if winsorize and len(yoy_growth) >= 4:
        yoy_growth = winsorize_series(
            yoy_growth, lower_quantile, upper_quantile
        )

    return float(yoy_growth.median())


# ── Financial formatting ──────────────────────────────────────────────────────

def format_currency(
    value: float,
    currency: str = "$",
    decimals: int = 2,
) -> str:
    """
    Format a number as currency with appropriate scale suffix.

    Args:
        value: Numeric value to format.
        currency: Currency symbol. Default "$".
        decimals: Decimal places. Default 2.

    Returns:
        Formatted string e.g. "$1.23B", "$456.78M", "$12.34K".

    Example:
        >>> format_currency(1_234_567_890)
        "$1.23B"
        >>> format_currency(456_780_000)
        "$456.78M"
    """
    abs_val = abs(value)
    sign = "-" if value < 0 else ""

    if abs_val >= 1e12:
        return f"{sign}{currency}{abs_val/1e12:.{decimals}f}T"
    elif abs_val >= 1e9:
        return f"{sign}{currency}{abs_val/1e9:.{decimals}f}B"
    elif abs_val >= 1e6:
        return f"{sign}{currency}{abs_val/1e6:.{decimals}f}M"
    elif abs_val >= 1e3:
        return f"{sign}{currency}{abs_val/1e3:.{decimals}f}K"
    else:
        return f"{sign}{currency}{abs_val:.{decimals}f}"


def format_percent(
    value: float,
    decimals: int = 1,
) -> str:
    """
    Format a decimal as a percentage string.

    Args:
        value: Decimal value (e.g. 0.123 for 12.3%).
        decimals: Decimal places. Default 1.

    Returns:
        Formatted string e.g. "12.3%".
    """
    return f"{value * 100:.{decimals}f}%"


# ── Validation helpers ────────────────────────────────────────────────────────

def validate_weights(
    weights: Union[list[float], np.ndarray],
    tolerance: float = 1e-6,
) -> bool:
    """
    Validate that portfolio weights sum to 1.0 within tolerance.

    Args:
        weights: List or array of portfolio weights.
        tolerance: Acceptable deviation from 1.0. Default 1e-6.

    Returns:
        True if weights sum to approximately 1.0.

    Raises:
        ValueError: If weights do not sum to 1.0 within tolerance.
    """
    total = sum(weights)
    if abs(total - 1.0) > tolerance:
        raise ValueError(
            f"Portfolio weights must sum to 1.0. Got {total:.6f}. "
            f"Difference: {abs(total - 1.0):.2e}"
        )
    return True
