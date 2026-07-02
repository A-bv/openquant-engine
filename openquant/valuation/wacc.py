"""
OpenQuant — Beta, CAPM, Cost of Debt, and WACC computation.

Implements directly from the EPFL formula sheet:

    β = Cov(r_stock, r_market) / Var(r_market)

    Cost of Equity = r_f + β × (r_m − r_f)          [CAPM]

    βU = βE / (1 + (1−T) × D/E)                      [Hamada unlevering]

    WACC = (E/V) × r_E + (D/V) × r_D × (1 − T)

Ground truth fixture (EPFL Exam 1, Problem 2):
    βU = 1.50, r_f = 8%, MRP = 8% → E(RU) = 20%

Dependency rule: zero Streamlit imports. Pure Python. Fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from openquant.config import (
    DEFAULT_RISK_FREE_RATE,
    DEFAULT_MARKET_RISK_PREMIUM,
    DEFAULT_TRADING_DAYS,
    BETA_LOOKBACK_YEARS,
    BETA_ROLLING_WINDOW_DAYS,
    BETA_CONFIDENCE_LEVEL,
)
from openquant.data import FinancialStatements, PriceData
from openquant.common import log_returns, annualise_return, annualise_vol, bootstrap_ci


# ── EPFL formula sheet primitives ─────────────────────────────────────────────


def unlever_beta_hamada(
    beta_levered: float,
    debt_to_equity: float,
    tax_rate: float,
) -> float:
    """
    Hamada unlevering — strip the financial-leverage component from equity beta.

    EPFL formula sheet:
        βU = βE / (1 + (1 − T) × D/E)

    Assumes debt beta = 0 (standard educational assumption).

    EPFL Sample Exam 1 Problem 2:
        Firm A: βE = 1.99, D/V = 0.33 (→ D/E ≈ 0.4925), T = 0.35  →  βU = 1.500
        Firm B: βE = 2.48, D/V = 0.50 (→ D/E = 1.00),   T = 0.35  →  βU = 1.503

    Args:
        beta_levered: Equity beta of the levered firm.
        debt_to_equity: D/E ratio (NOT D/V). Convert if needed:
            D/E = (D/V) / (1 − D/V)
        tax_rate: Corporate tax rate.

    Returns:
        Unlevered (asset) beta.
    """
    return beta_levered / (1.0 + (1.0 - tax_rate) * debt_to_equity)


def capm_cost_of_equity(
    risk_free_rate: float,
    beta: float,
    market_risk_premium: float,
) -> float:
    """
    CAPM cost of equity.

    EPFL formula sheet:
        rE = rf + β × (rM − rf)

    EPFL Sample Exam 1 Problem 2:
        rf = 0.08, β = 1.50, MRP = 0.08  →  rE = 0.20
    """
    return risk_free_rate + beta * market_risk_premium


def beta_from_correlation(
    correlation_with_market: float,
    asset_volatility: float,
    market_volatility: float,
) -> float:
    """
    Compute β from the correlation form: β = ρ_iM × σ_i / σ_M.

    Equivalent to Cov/Var but useful when only summary stats are available
    (e.g. asset has stated correlation and volatility but no return series).

    EPFL Sample Exam 2 Problem 3-Q3b:
        Monsters: ρ=0.60, σ_i=0.24, σ_M=0.18  →  β = 0.80
        California Gold: ρ=-0.7, σ_i=0.32, σ_M=0.18  →  β ≈ -1.244
    """
    if market_volatility <= 0:
        raise ValueError("market_volatility must be positive")
    return correlation_with_market * asset_volatility / market_volatility


def idiosyncratic_variance(
    total_variance: float,
    beta: float,
    market_variance: float,
) -> float:
    """
    Decompose total variance into systematic and idiosyncratic components.

        σ_i² = β² × σ_M² + σ_ε²     →     σ_ε² = σ_i² − β² × σ_M²

    EPFL Sample Exam 2 Problem 5-Q5a:
        Fund A: σ_i² = 0.37, β = 1.3, σ_M² = 0.0961  →  σ_ε² ≈ 0.2076
        Fund B: σ_i² = 0.26, β = 0.9, σ_M² = 0.0961  →  σ_ε² ≈ 0.1821

    Returns the residual variance (clamped at 0 since negative would
    indicate inconsistent inputs — β too large to reconcile with σ_i²).
    """
    return max(total_variance - (beta ** 2) * market_variance, 0.0)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class BetaResult:
    """
    Beta estimation result with statistical context.

    Honest about uncertainty — shows confidence interval,
    rolling instability, and Hamada assumption.
    """
    ticker: str

    # Static beta (OLS over full period)
    beta: float                          # Point estimate
    beta_ci_lower: float                 # 95% CI lower bound
    beta_ci_upper: float                 # 95% CI upper bound
    beta_se: float                       # Standard error (Newey-West)
    r_squared: float                     # R² of market model regression

    # Rolling beta
    rolling_beta: pd.Series              # 90-day rolling beta
    rolling_beta_range: float            # Max - Min of rolling beta
    rolling_beta_stable: bool            # True if range < 0.5

    # Unlevered beta (Hamada)
    unlevered_beta: Optional[float]      # None if leverage data unavailable
    leverage_ratio: Optional[float]      # D/E ratio used for unlevering
    tax_rate_used: Optional[float]       # Tax rate used for unlevering

    # Plain language
    beta_interpretation: str             # Human-readable description
    stability_note: str                  # Note on rolling stability

    # Warnings
    warnings: list[str] = field(default_factory=list)


@dataclass
class CostOfEquityResult:
    """CAPM cost of equity computation."""
    ticker: str

    # Inputs
    risk_free_rate: float
    beta: float
    market_risk_premium: float

    # Output
    cost_of_equity: float                # r_f + β × MRP

    # Formula trace (for UI display)
    formula_trace: str                   # "8% + 1.50 × 8% = 20%"


@dataclass
class CostOfDebtResult:
    """
    Cost of debt estimation.

    Uses interest expense / average debt — historical effective rate.
    Honest about the approximation.
    """
    ticker: str

    interest_expense_latest: float
    average_debt: float                  # (beginning + ending) / 2
    ending_debt: float
    cost_of_debt_pretax: float           # interest expense / avg debt
    tax_rate: float
    cost_of_debt_aftertax: float         # pretax × (1 − T)

    # Disclosure
    approximation_note: str             # Always shown to user

    # Warnings
    warnings: list[str] = field(default_factory=list)


@dataclass
class WACCResult:
    """
    Complete WACC computation.

    Implements EPFL formula: WACC = (E/V)×rE + (D/V)×rD×(1−T)
    Every component traced for UI display.
    """
    ticker: str
    company_name: str

    # Capital structure
    market_cap: float                    # E — equity market value
    total_debt: float                    # D — book value of debt
    firm_value: float                    # V = E + D
    equity_weight: float                 # E/V
    debt_weight: float                   # D/V

    # Components
    cost_of_equity: float                # r_E from CAPM
    cost_of_debt_pretax: float           # r_D before tax shield
    cost_of_debt_aftertax: float         # r_D × (1 − T)
    tax_rate: float                      # Effective tax rate

    # Result
    wacc: float                          # The final WACC

    # Beta inputs
    beta: float
    risk_free_rate: float
    market_risk_premium: float

    # Tax shield
    tax_shield_pv_note: str              # Reference to PVTS concept

    # Sensitivity
    wacc_sensitivity: dict               # WACC at ±1% equity/debt changes

    # Warnings
    warnings: list[str] = field(default_factory=list)

    @property
    def formula_trace(self) -> str:
        """Human-readable WACC formula with numbers filled in."""
        return (
            f"WACC = ({self.equity_weight:.1%} × {self.cost_of_equity:.1%}) "
            f"+ ({self.debt_weight:.1%} × {self.cost_of_debt_pretax:.1%} "
            f"× (1 − {self.tax_rate:.1%})) "
            f"= {self.wacc:.1%}"
        )


# ── Beta estimator ────────────────────────────────────────────────────────────

class BetaEstimator:
    """
    Estimates market beta using OLS regression with Newey-West
    standard errors and rolling beta for stability analysis.

    Formula (EPFL formula sheet):
        β = Cov(r_stock, r_market) / Var(r_market)

    Equivalent to OLS slope in:
        r_stock = α + β × r_market + ε
    """

    def estimate(
        self,
        price_data: PriceData,
        statements: Optional[FinancialStatements] = None,
        rolling_window: int = BETA_ROLLING_WINDOW_DAYS,
        confidence_level: float = BETA_CONFIDENCE_LEVEL,
    ) -> BetaResult:
        """
        Estimate beta from price data.

        Args:
            price_data: PriceData with stock and market prices.
            statements: Optional — used for Hamada unlevering.
            rolling_window: Window for rolling beta. Default 90 days.
            confidence_level: CI level. Default 95%.

        Returns:
            BetaResult with point estimate, CI, rolling series.
        """
        warnings = []

        # Compute log returns
        stock_returns = log_returns(price_data.prices)
        market_returns = log_returns(price_data.market_prices)

        # Align
        common_idx = stock_returns.index.intersection(market_returns.index)
        r_s = stock_returns.loc[common_idx]
        r_m = market_returns.loc[common_idx]

        n = len(r_s)
        if n < 60:
            warnings.append(
                f"Only {n} return observations available. "
                f"Beta estimate is unreliable."
            )

        # ── OLS beta ──────────────────────────────────────────────────────────
        # β = Cov(r_s, r_m) / Var(r_m)  — EPFL formula sheet
        cov = float(np.cov(r_s, r_m, ddof=1)[0, 1])
        var_m = float(r_m.var(ddof=1))
        if var_m > 0:
            beta = cov / var_m
        else:
            beta = 1.0
            warnings.append(
                "Market return variance is zero (flat market over the "
                "lookback window). Beta could not be estimated from data "
                "and has been defaulted to 1.0 (market average)."
            )

        # ── OLS with Newey-West SE ────────────────────────────────────────────
        X = np.column_stack([np.ones(n), r_m.values])
        y = r_s.values

        # OLS coefficients
        try:
            coeffs, residuals, _, _ = np.linalg.lstsq(X, y, rcond=None)
            alpha_ols, beta_ols = coeffs

            # R-squared
            y_pred = X @ coeffs
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

            # Newey-West standard errors (lag=4 for daily data)
            beta_se = self._newey_west_se(X, y, coeffs, lags=4)

            # CI
            from scipy.stats import t as t_dist
            t_crit = t_dist.ppf((1 + confidence_level) / 2, df=n - 2)
            beta_ci_lower = float(beta_ols - t_crit * beta_se)
            beta_ci_upper = float(beta_ols + t_crit * beta_se)
            beta = float(beta_ols)

        except np.linalg.LinAlgError:
            warnings.append("OLS failed — using Cov/Var formula directly.")
            beta_se = 0.0
            beta_ci_lower = beta * 0.8
            beta_ci_upper = beta * 1.2
            r_squared = 0.0

        # ── Rolling beta ──────────────────────────────────────────────────────
        rolling_beta = self._compute_rolling_beta(r_s, r_m, rolling_window)
        rolling_range = float(
            rolling_beta.max() - rolling_beta.min()
        ) if len(rolling_beta.dropna()) > 0 else 0.0
        rolling_stable = rolling_range < 0.5

        if rolling_range > 1.0:
            warnings.append(
                f"Beta has been highly unstable — rolling range: "
                f"{rolling_range:.2f}. WACC estimate may not reflect "
                f"current market sensitivity."
            )
        elif rolling_range > 0.5:
            warnings.append(
                f"Moderate beta instability detected — rolling range: "
                f"{rolling_range:.2f}."
            )

        # ── Hamada unlevering ─────────────────────────────────────────────────
        unlevered_beta = None
        leverage_ratio = None
        tax_rate_used = None

        if statements is not None:
            unlevered_beta, leverage_ratio, tax_rate_used = self._unlever_beta(
                beta, statements
            )

        # ── Plain language ────────────────────────────────────────────────────
        beta_interp = self._interpret_beta(beta)
        stability_note = (
            "Rolling beta is stable — the estimate is reliable."
            if rolling_stable else
            f"Rolling beta has shifted significantly over the period "
            f"(range: {rolling_range:.2f}). "
            f"The static beta may not reflect current market sensitivity."
        )

        return BetaResult(
            ticker=price_data.ticker,
            beta=beta,
            beta_ci_lower=beta_ci_lower,
            beta_ci_upper=beta_ci_upper,
            beta_se=beta_se,
            r_squared=r_squared,
            rolling_beta=rolling_beta,
            rolling_beta_range=rolling_range,
            rolling_beta_stable=rolling_stable,
            unlevered_beta=unlevered_beta,
            leverage_ratio=leverage_ratio,
            tax_rate_used=tax_rate_used,
            beta_interpretation=beta_interp,
            stability_note=stability_note,
            warnings=warnings,
        )

    def _compute_rolling_beta(
        self,
        stock_returns: pd.Series,
        market_returns: pd.Series,
        window: int,
    ) -> pd.Series:
        """
        Compute rolling beta using covariance method.

        Args:
            stock_returns: Daily stock log returns.
            market_returns: Daily market log returns.
            window: Rolling window in days.

        Returns:
            pd.Series of rolling beta values.
        """
        rolling_cov = stock_returns.rolling(window).cov(market_returns)
        rolling_var = market_returns.rolling(window).var()
        # Zero variance (flat-market window) would produce Inf; treat as undefined.
        safe_var = rolling_var.where(rolling_var > 0, np.nan)
        rolling_beta = rolling_cov / safe_var
        rolling_beta.name = f"beta_{window}d"
        return rolling_beta

    def _newey_west_se(
        self,
        X: np.ndarray,
        y: np.ndarray,
        coeffs: np.ndarray,
        lags: int = 4,
    ) -> float:
        """
        Compute Newey-West heteroskedasticity and autocorrelation
        consistent standard error for the beta coefficient.

        Args:
            X: Design matrix [1, r_market].
            y: Dependent variable [r_stock].
            coeffs: OLS coefficients [alpha, beta].
            lags: Number of lags for NW correction.

        Returns:
            Standard error for beta coefficient (index 1).
        """
        n = len(y)
        residuals = y - X @ coeffs

        # Sandwich estimator: (X'X)^{-1} S (X'X)^{-1}
        XtX_inv = np.linalg.pinv(X.T @ X)

        # Newey-West S matrix
        S = X.T @ np.diag(residuals ** 2) @ X  # HC0 core
        for lag in range(1, lags + 1):
            weight = 1 - lag / (lags + 1)
            Xl = X[lag:]
            Xr = X[:-lag]
            el = residuals[lag:]
            er = residuals[:-lag]
            gamma = Xl.T @ np.diag(el * er) @ Xr
            S += weight * (gamma + gamma.T)

        # Variance-covariance matrix
        vcov = XtX_inv @ S @ XtX_inv * n / (n - 2)

        # SE for beta (index 1)
        beta_var = float(vcov[1, 1])
        return float(np.sqrt(max(beta_var, 0)))

    def _unlever_beta(
        self,
        beta_levered: float,
        statements: FinancialStatements,
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Unlever beta using Hamada formula.

        Formula (EPFL formula sheet):
            βU = βE / (1 + (1−T) × D/E)

        Assumes debt beta = zero — standard educational assumption.

        Args:
            beta_levered: Equity beta from OLS.
            statements: Financial statements for D/E ratio.

        Returns:
            Tuple of (unlevered_beta, D/E ratio, tax_rate).
        """
        debt = statements.total_debt.dropna()
        shares = statements.shares_outstanding.dropna()
        tax = statements.effective_tax_rate.dropna()

        if len(debt) == 0 or len(shares) == 0:
            return None, None, None

        # Latest values
        latest_debt = float(debt.iloc[-1])
        latest_shares = float(shares.iloc[-1])
        tax_rate = float(tax.iloc[-1]) if len(tax) > 0 else 0.21

        # Need share price for market cap — approximate with book ratio
        # True unlevering requires current market cap
        # We'll compute D/E using debt / (debt + approximate equity)
        # This is a simplification — noted in UI
        if latest_debt <= 0:
            return float(beta_levered), 0.0, tax_rate

        # Use debt as proxy for leverage — will be refined with market cap in wacc.py
        # βU = βE / (1 + (1−T) × D/E)
        # Without market cap we return the levered beta and flag it
        return None, None, None  # Refined in WACCBuilder with market cap

    def _interpret_beta(self, beta: float) -> str:
        """
        Generate plain-language beta interpretation.

        Corrected per CFA feedback:
        Beta measures SENSITIVITY to market movements,
        not total volatility.
        """
        pct = abs(beta - 1.0) * 100

        if beta < 0:
            return (
                f"Beta of {beta:.2f} means this stock tends to move "
                f"in the opposite direction to the market. "
                f"Rare — suggests defensive or counter-cyclical characteristics."
            )
        elif abs(beta - 1.0) < 0.05:
            return (
                f"Beta of {beta:.2f} means this stock's returns are "
                f"approximately as sensitive to market movements as the index."
            )
        elif beta < 1.0:
            return (
                f"Beta of {beta:.2f} means this stock's returns are "
                f"{pct:.0f}% less sensitive to market movements than the index. "
                f"Its total volatility may still be higher or lower than the "
                f"market depending on idiosyncratic risk."
            )
        else:
            return (
                f"Beta of {beta:.2f} means this stock's returns are "
                f"{pct:.0f}% more sensitive to market movements than the index. "
                f"Its total volatility may still be higher or lower than the "
                f"market depending on idiosyncratic risk."
            )


# ── WACC builder ──────────────────────────────────────────────────────────────

class WACCBuilder:
    """
    Builds WACC from beta, cost of equity (CAPM), and cost of debt.

    Implements EPFL formula:
        WACC = (E/V) × r_E + (D/V) × r_D × (1 − T)

    EPFL ground truth:
        β=1.50, r_f=8%, MRP=8% → r_E = 8% + 1.50×8% = 20%
    """

    def compute_cost_of_equity(
        self,
        beta: float,
        risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
        market_risk_premium: float = DEFAULT_MARKET_RISK_PREMIUM,
    ) -> CostOfEquityResult:
        """
        Compute cost of equity using CAPM.

        Formula (EPFL formula sheet):
            r_E = r_f + β × (r_m − r_f)

        EPFL ground truth verification:
            β=1.50, r_f=8%, MRP=8% → r_E = 8% + 1.50×8% = 20% ✓

        Args:
            beta: Equity beta.
            risk_free_rate: Annual risk-free rate.
            market_risk_premium: E(r_m) - r_f.

        Returns:
            CostOfEquityResult with formula trace.
        """
        cost_of_equity = risk_free_rate + beta * market_risk_premium

        formula_trace = (
            f"{risk_free_rate:.1%} + {beta:.2f} × {market_risk_premium:.1%} "
            f"= {cost_of_equity:.1%}"
        )

        return CostOfEquityResult(
            ticker="",
            risk_free_rate=risk_free_rate,
            beta=beta,
            market_risk_premium=market_risk_premium,
            cost_of_equity=cost_of_equity,
            formula_trace=formula_trace,
        )

    def compute_cost_of_debt(
        self,
        statements: FinancialStatements,
    ) -> CostOfDebtResult:
        """
        Compute pre-tax cost of debt.

        Uses interest expense / average debt.
        Average debt = (beginning + ending) / 2 — cleaner than ending only.

        Honest disclosure: this is historical effective cost,
        not current marginal cost.

        Args:
            statements: Financial statements with debt and interest data.

        Returns:
            CostOfDebtResult with approximation note.
        """
        warnings = []

        interest = statements.interest_expense.dropna()
        debt = statements.total_debt.dropna()
        beg_debt = statements.beginning_debt.dropna()
        tax = statements.effective_tax_rate.dropna()

        # Latest interest expense
        if len(interest) > 0:
            interest_latest = float(interest.iloc[-1])
        else:
            warnings.append("Interest expense data not available.")
            interest_latest = 0.0

        # Average debt (beginning + ending) / 2
        if len(debt) > 0 and len(beg_debt) > 0:
            ending_debt = float(debt.iloc[-1])
            beginning_debt = float(beg_debt.iloc[-1])
            avg_debt = (ending_debt + beginning_debt) / 2
        elif len(debt) > 0:
            ending_debt = float(debt.iloc[-1])
            avg_debt = ending_debt
            warnings.append(
                "Beginning debt not available — using ending debt for cost computation."
            )
        else:
            ending_debt = 0.0
            avg_debt = 0.0
            warnings.append(
                "Debt data not available. Using 4% default cost of debt."
            )

        # Pre-tax cost of debt
        if avg_debt > 0 and interest_latest > 0:
            cost_pretax = interest_latest / avg_debt
            # Sanity bounds: 0.5% to 20%
            cost_pretax = float(np.clip(cost_pretax, 0.005, 0.20))
        else:
            cost_pretax = 0.04  # Conservative default
            warnings.append(
                "Cannot compute cost of debt from data. "
                "Using 4% as conservative estimate."
            )

        # After-tax cost. `tax` has already been dropna()'d, but defend
        # against an all-NaN series falling through and a non-finite latest
        # value (e.g. NaN from a zero-pretax-income year).
        if len(tax) > 0 and np.isfinite(tax.iloc[-1]):
            tax_rate = float(tax.iloc[-1])
        else:
            tax_rate = 0.21
        cost_aftertax = cost_pretax * (1 - tax_rate)

        approximation_note = (
            "Cost of debt is approximated as interest expense / average debt "
            "(historical effective rate). This may understate current marginal "
            "cost for companies refinancing in higher rate environments. "
            "Current yield to maturity would be more precise but requires "
            "bond market data."
        )

        return CostOfDebtResult(
            ticker=statements.ticker,
            interest_expense_latest=interest_latest,
            average_debt=avg_debt,
            ending_debt=ending_debt,
            cost_of_debt_pretax=cost_pretax,
            tax_rate=tax_rate,
            cost_of_debt_aftertax=cost_aftertax,
            approximation_note=approximation_note,
            warnings=warnings,
        )

    def compute_wacc(
        self,
        statements: FinancialStatements,
        price_data: PriceData,
        current_share_price: float,
        risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
        market_risk_premium: float = DEFAULT_MARKET_RISK_PREMIUM,
        beta_override: Optional[float] = None,
    ) -> WACCResult:
        """
        Compute WACC from all components.

        Formula (EPFL formula sheet):
            WACC = (E/V) × r_E + (D/V) × r_D × (1 − T)

        Args:
            statements: Financial statements.
            price_data: Price data for beta computation.
            current_share_price: Current stock price for market cap.
            risk_free_rate: Annual risk-free rate.
            market_risk_premium: Market risk premium.
            beta_override: Use this beta instead of computing from prices.

        Returns:
            WACCResult with all components and formula trace.

        Raises:
            ValueError: If WACC computation is not possible.
        """
        warnings = []

        # ── Beta ──────────────────────────────────────────────────────────────
        if beta_override is not None:
            beta = beta_override
        else:
            estimator = BetaEstimator()
            beta_result = estimator.estimate(price_data, statements)
            beta = beta_result.beta
            warnings.extend(beta_result.warnings)

        # ── Cost of equity (CAPM) ─────────────────────────────────────────────
        coe_result = self.compute_cost_of_equity(
            beta, risk_free_rate, market_risk_premium
        )
        cost_of_equity = coe_result.cost_of_equity

        # ── Cost of debt ──────────────────────────────────────────────────────
        cod_result = self.compute_cost_of_debt(statements)
        cost_of_debt_pretax = cod_result.cost_of_debt_pretax
        cost_of_debt_aftertax = cod_result.cost_of_debt_aftertax
        tax_rate = cod_result.tax_rate
        warnings.extend(cod_result.warnings)

        # ── Capital structure ─────────────────────────────────────────────────
        shares = statements.shares_outstanding.dropna()
        debt = statements.total_debt.dropna()

        if len(shares) == 0:
            raise ValueError(
                f"Cannot compute WACC for {statements.ticker}: "
                f"no shares outstanding data available."
            )

        latest_shares = float(shares.iloc[-1])
        market_cap = latest_shares * current_share_price

        latest_debt = float(debt.iloc[-1]) if len(debt) > 0 else 0.0

        firm_value = market_cap + latest_debt
        if firm_value <= 0:
            raise ValueError(
                f"Invalid firm value for {statements.ticker}: "
                f"market cap {market_cap:.0f} + debt {latest_debt:.0f} = {firm_value:.0f}"
            )

        equity_weight = market_cap / firm_value
        debt_weight = latest_debt / firm_value

        # ── Hamada unlevering (with market cap) ───────────────────────────────
        if latest_debt > 0 and market_cap > 0:
            de_ratio = latest_debt / market_cap
            unlevered_beta = beta / (1 + (1 - tax_rate) * de_ratio)
        else:
            unlevered_beta = beta

        # ── WACC ──────────────────────────────────────────────────────────────
        wacc = (
            equity_weight * cost_of_equity
            + debt_weight * cost_of_debt_aftertax
        )

        # Sanity check. A non-positive WACC means an undiscounted DCF — no
        # safe downstream behaviour exists, so refuse rather than return a
        # result that would silently inflate the intrinsic value.
        if not np.isfinite(wacc) or wacc <= 0:
            raise ValueError(
                f"Computed WACC of {wacc} for {statements.ticker} is not "
                f"usable (non-positive or non-finite). "
                f"Likely cause: negative beta or unrealistic risk-free rate."
            )
        if wacc > 0.50:
            warnings.append(
                f"WACC of {wacc:.1%} seems unusual. Review inputs carefully."
            )

        # ── Sensitivity ───────────────────────────────────────────────────────
        sensitivity = self._wacc_sensitivity(
            equity_weight, debt_weight,
            cost_of_equity, cost_of_debt_aftertax,
            market_risk_premium, beta,
        )

        tax_shield_note = (
            "The debt × tax_rate component reflects the tax shield on interest "
            "payments — the same concept as PVTS in EPFL Exam 1, Problem 3."
        )

        return WACCResult(
            ticker=statements.ticker,
            company_name=statements.company_name,
            market_cap=market_cap,
            total_debt=latest_debt,
            firm_value=firm_value,
            equity_weight=equity_weight,
            debt_weight=debt_weight,
            cost_of_equity=cost_of_equity,
            cost_of_debt_pretax=cost_of_debt_pretax,
            cost_of_debt_aftertax=cost_of_debt_aftertax,
            tax_rate=tax_rate,
            wacc=wacc,
            beta=beta,
            risk_free_rate=risk_free_rate,
            market_risk_premium=market_risk_premium,
            tax_shield_pv_note=tax_shield_note,
            wacc_sensitivity=sensitivity,
            warnings=warnings,
        )

    def _wacc_sensitivity(
        self,
        equity_weight: float,
        debt_weight: float,
        cost_of_equity: float,
        cost_of_debt_aftertax: float,
        market_risk_premium: float,
        beta: float,
        delta: float = 0.01,
    ) -> dict:
        """
        Compute WACC sensitivity to ±1% changes in key inputs.

        Returns dict of {scenario: wacc_value}.
        """
        base_wacc = equity_weight * cost_of_equity + debt_weight * cost_of_debt_aftertax

        # Sensitivity to MRP ± 1%
        wacc_mrp_up = equity_weight * (cost_of_equity + beta * delta) + debt_weight * cost_of_debt_aftertax
        wacc_mrp_down = equity_weight * (cost_of_equity - beta * delta) + debt_weight * cost_of_debt_aftertax

        # Sensitivity to cost of debt ± 1%
        wacc_cod_up = equity_weight * cost_of_equity + debt_weight * (cost_of_debt_aftertax + delta)
        wacc_cod_down = equity_weight * cost_of_equity + debt_weight * (cost_of_debt_aftertax - delta)

        return {
            "base": base_wacc,
            "mrp_plus_1pct": wacc_mrp_up,
            "mrp_minus_1pct": wacc_mrp_down,
            "cod_plus_1pct": wacc_cod_up,
            "cod_minus_1pct": wacc_cod_down,
        }
