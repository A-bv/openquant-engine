"""
OpenQuant — Portfolio risk & diversification engine.

Pure Python (numpy / pandas only). No network, no Streamlit. Fully testable.

Turns the EPFL "Risk & Return" block (Berk-DeMarzo Ch. 10-12, Sample Exam 2
Problems 3-5) into one concrete, real-data deliverable:

    "You think you hold N positions. In risk terms you hold X independent bets."

The covariance matrix is the machinery; the *useful result* a person reads is
the effective number of bets, the risk multiple versus an uncorrelated book,
and which single holding secretly drives the risk.

Two-layer design:
  Layer 1 (simple)  — DiversificationReport.summary_lines(): the verdict.
  Layer 2 (deep)    — .detail_lines(): per-holding risk contributions,
                      correlation summary, formulas + EPFL sources.

Validated against EPFL Sample Exam 2 P4 in tests/test_portfolio.py: the
two-asset reduction reproduces σ_p = 0.07 (ρ = -1) and ω_Y = 0.20 (MVP).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Union

import numpy as np
import pandas as pd

from openquant.config import DEFAULT_TRADING_DAYS, DEFAULT_RISK_FREE_RATE
from openquant.common import annualise_returns_series, sharpe_from_stats

Matrix = Union[pd.DataFrame, np.ndarray]


# ── Covariance / correlation ──────────────────────────────────────────────────

def covariance_matrix(
    returns: pd.DataFrame,
    trading_days: int = DEFAULT_TRADING_DAYS,
) -> pd.DataFrame:
    """
    Annualised covariance matrix Σ from a DataFrame of daily log returns.

    Berk-DeMarzo Ch. 11.3: Cov(R_i, R_j); annualised by × trading_days
    (covariance scales linearly with the horizon under the iid assumption).
    """
    if returns.shape[1] < 2:
        raise ValueError("Need at least 2 assets for a covariance matrix.")
    if len(returns) < 2:
        raise ValueError("Need at least 2 return observations.")
    return returns.cov() * trading_days


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation matrix ρ (scale-free — annualising does not change it)."""
    if returns.shape[1] < 2:
        raise ValueError("Need at least 2 assets for a correlation matrix.")
    return returns.corr()


def covariance_from_vols_and_corr(
    vols: Sequence[float],
    corr: Matrix,
) -> pd.DataFrame:
    """
    Build Σ from standalone vols and a correlation matrix: Σ_ij = ρ_ij · σ_i · σ_j.

    Lets the same engine consume textbook/exam inputs (σ, ρ given directly) as
    well as live return series — this is how we pin against EPFL Sample Exam 2.
    """
    sigma = np.asarray(vols, dtype=float)
    rho = np.asarray(corr.values if isinstance(corr, pd.DataFrame) else corr, dtype=float)
    n = len(sigma)
    if rho.shape != (n, n):
        raise ValueError(f"corr must be {n}x{n} to match {n} vols, got {rho.shape}")
    return pd.DataFrame(rho * np.outer(sigma, sigma))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _as_matrix(cov: Matrix) -> np.ndarray:
    return cov.values if isinstance(cov, pd.DataFrame) else np.asarray(cov, dtype=float)


def _normalise_weights(weights: Optional[Sequence[float]], n: int) -> np.ndarray:
    """Equal-weight when None; otherwise rescale to sum to 1."""
    if weights is None:
        return np.full(n, 1.0 / n)
    w = np.asarray(weights, dtype=float)
    if w.shape != (n,):
        raise ValueError(f"weights must have length {n}, got {w.shape}")
    total = w.sum()
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    return w / total


# ── Portfolio risk ────────────────────────────────────────────────────────────

def portfolio_variance(weights: Optional[Sequence[float]], cov: Matrix) -> float:
    """Var(R_p) = wᵀ Σ w. Berk-DeMarzo Ch. 11.4."""
    S = _as_matrix(cov)
    w = _normalise_weights(weights, S.shape[0])
    return float(w @ S @ w)


def portfolio_volatility(weights: Optional[Sequence[float]], cov: Matrix) -> float:
    """σ_p = sqrt(wᵀ Σ w)."""
    return float(np.sqrt(portfolio_variance(weights, cov)))


def standalone_vols(cov: Matrix) -> np.ndarray:
    """Per-asset volatility σ_i = sqrt(Σ_ii)."""
    return np.sqrt(np.diag(_as_matrix(cov)))


def independent_volatility(weights: Optional[Sequence[float]], cov: Matrix) -> float:
    """
    Portfolio vol *if the holdings were uncorrelated*: sqrt(Σ w_i² σ_i²).

    The benchmark that makes diversification visible: idiosyncratic risk only
    averages away when assets are independent (Berk-DeMarzo Ch. 11.4-11.5).
    """
    S = _as_matrix(cov)
    w = _normalise_weights(weights, S.shape[0])
    sig = np.sqrt(np.diag(S))
    return float(np.sqrt(np.sum((w * sig) ** 2)))


def diversification_ratio(weights: Optional[Sequence[float]], cov: Matrix) -> float:
    """
    DR = (Σ w_i σ_i) / σ_p ≥ 1  (Choueifaty & Coignard, 2008).

    Equals 1 when everything moves together (no diversification); grows as the
    book becomes more independent.
    """
    S = _as_matrix(cov)
    w = _normalise_weights(weights, S.shape[0])
    sig = np.sqrt(np.diag(S))
    port_vol = np.sqrt(w @ S @ w)
    if port_vol <= 0:
        return 1.0
    return float((w @ sig) / port_vol)


def effective_number_of_bets(weights: Optional[Sequence[float]], cov: Matrix) -> float:
    """
    How many *independent* bets the book really is: N_eff = DR².

    For n equal-weight assets with equal vol and pairwise correlation ρ:
        N_eff = n / (1 + (n-1)·ρ)
    e.g. 8 names at ρ = 0.7  →  N_eff ≈ 1.4.
    """
    return diversification_ratio(weights, cov) ** 2


def risk_contributions(weights: Optional[Sequence[float]], cov: Matrix) -> np.ndarray:
    """
    Each holding's share of total portfolio variance (sums to 1).

    Euler / component decomposition: CCR_i = w_i · (Σ w)_i / (wᵀ Σ w).
    Reveals the position that drives risk regardless of its capital weight.
    """
    S = _as_matrix(cov)
    w = _normalise_weights(weights, S.shape[0])
    var = w @ S @ w
    if var <= 0:
        return np.full(len(w), 1.0 / len(w))
    return (w * (S @ w)) / var


def min_variance_weights(cov: Matrix) -> np.ndarray:
    """
    Global minimum-variance weights: w = Σ⁻¹·1 / (1ᵀ·Σ⁻¹·1).

    n-asset generalisation of the EPFL two-asset closed form
    (min_variance_two_asset_weight in openquant.common). Long/short allowed.
    """
    S = _as_matrix(cov)
    ones = np.ones(S.shape[0])
    w = np.linalg.solve(S, ones)
    return w / w.sum()


# ── Two-layer deliverable ─────────────────────────────────────────────────────

@dataclass
class DiversificationReport:
    """
    The "X independent bets" deliverable, structured for two-layer rendering.

    Layer 1 = summary_lines(); Layer 2 = detail_lines() / to_dict().
    """
    tickers: list[str]
    weights: np.ndarray
    n_holdings: int
    effective_bets: float
    portfolio_vol: float          # annualised
    independent_vol: float        # annualised, if uncorrelated
    risk_multiple: float          # portfolio_vol / independent_vol
    diversification_ratio: float
    mean_correlation: float
    standalone_vols: np.ndarray   # annualised, per holding
    risk_contributions: np.ndarray
    expected_return: float        # annualised
    sharpe: float
    risk_free_rate: float
    correlation: pd.DataFrame
    covariance: pd.DataFrame

    @property
    def top_risk_idx(self) -> int:
        return int(np.argmax(self.risk_contributions))

    def summary_lines(self) -> list[str]:
        """Layer 1 — the plain-language verdict for the general public."""
        ti = self.top_risk_idx
        return [
            f"You hold {self.n_holdings} positions. In risk terms, that is "
            f"{self.effective_bets:.1f} independent bets.",
            f"Real volatility: {self.portfolio_vol * 100:.1f}%/yr.",
            f"If they were uncorrelated: {self.independent_vol * 100:.1f}%. "
            f"You carry {self.risk_multiple:.1f}x the risk you'd think.",
            f"Risk is driven by {self.tickers[ti]}: "
            f"{self.weights[ti] * 100:.0f}% of capital but "
            f"{self.risk_contributions[ti] * 100:.0f}% of the risk.",
            "Honest limit: in a crisis, holdings tend to move together, so your real "
            "diversification is even weaker than this calm-times snapshot.",
        ]

    def detail_lines(self) -> list[str]:
        """Layer 2 — the depth: per-holding decomposition, formulas, sources."""
        order = np.argsort(self.risk_contributions)[::-1]
        rows = [
            f"  {self.tickers[i]:<8} weight {self.weights[i] * 100:5.1f}%   "
            f"vol {self.standalone_vols[i] * 100:5.1f}%   "
            f"risk share {self.risk_contributions[i] * 100:5.1f}%"
            for i in order
        ]
        return [
            "Per-holding risk decomposition (Euler: CCR_i = w_i·(Σw)_i / wᵀΣw):",
            *rows,
            "",
            f"Average pairwise correlation: {self.mean_correlation:.2f}",
            f"Diversification ratio (Σ w_i σ_i)/σ_p = {self.diversification_ratio:.2f} "
            f"→ effective bets = DR² = {self.effective_bets:.2f}",
            f"Expected return (Σ w_i·E[R_i], annualised): "
            f"{self.expected_return * 100:.1f}%",
            f"Sharpe = (E[R_p] − r_f)/σ_p = "
            f"({self.expected_return * 100:.1f}% − {self.risk_free_rate * 100:.1f}%)"
            f"/{self.portfolio_vol * 100:.1f}% = {self.sharpe:.2f}",
            "",
            "Formulas: Berk-DeMarzo Ch. 11.3-11.5 · formula sheet p.2-3",
            "  Var(R_p) = wᵀ Σ w        (portfolio variance)",
            "  σ_indep  = sqrt(Σ w_i² σ_i²)   (if holdings were independent)",
            "Pinned by tests/test_portfolio.py against the Sample Exam 2 portfolio "
            "problem (σ_p = 0.07 at ρ = −1; min-variance ω_Y = 0.20).",
        ]

    def to_dict(self) -> dict:
        return {
            "tickers": list(self.tickers),
            "weights": [float(x) for x in self.weights],
            "n_holdings": int(self.n_holdings),
            "effective_bets": float(self.effective_bets),
            "portfolio_vol": float(self.portfolio_vol),
            "independent_vol": float(self.independent_vol),
            "risk_multiple": float(self.risk_multiple),
            "diversification_ratio": float(self.diversification_ratio),
            "mean_correlation": float(self.mean_correlation),
            "standalone_vols": [float(x) for x in self.standalone_vols],
            "risk_contributions": [float(x) for x in self.risk_contributions],
            "expected_return": float(self.expected_return),
            "sharpe": float(self.sharpe),
            "risk_free_rate": float(self.risk_free_rate),
            "correlation": self.correlation.round(4).to_dict(),
        }


def analyse_diversification(
    returns: pd.DataFrame,
    weights: Optional[Sequence[float]] = None,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    trading_days: int = DEFAULT_TRADING_DAYS,
) -> DiversificationReport:
    """
    Run the full diversification deliverable on a DataFrame of daily log returns.

    Args:
        returns: columns = tickers, rows = aligned daily log returns.
        weights: portfolio weights (equal-weight if None). Rescaled to sum to 1.
        risk_free_rate: annual risk-free rate for the Sharpe ratio.
        trading_days: trading days per year for annualisation.

    Returns:
        DiversificationReport (Layer 1 + Layer 2).
    """
    if returns.shape[1] < 2:
        raise ValueError("Need at least 2 holdings to analyse diversification.")

    tickers = [str(c) for c in returns.columns]
    n = len(tickers)
    w = _normalise_weights(weights, n)

    cov = covariance_matrix(returns, trading_days)
    corr = correlation_matrix(returns)

    port_vol = portfolio_volatility(w, cov)
    indep_vol = independent_volatility(w, cov)
    rc = risk_contributions(w, cov)
    sa_vols = standalone_vols(cov)
    eff_bets = effective_number_of_bets(w, cov)
    dr = diversification_ratio(w, cov)

    # mean off-diagonal correlation
    rho = corr.values
    off_diag = rho[~np.eye(n, dtype=bool)]
    mean_corr = float(off_diag.mean())

    # expected return = Σ w_i · annualised return of holding i
    ann_returns = np.array([
        annualise_returns_series(returns[c], trading_days) for c in returns.columns
    ])
    expected_return = float(w @ ann_returns)
    sharpe = sharpe_from_stats(expected_return, risk_free_rate, port_vol)

    return DiversificationReport(
        tickers=tickers,
        weights=w,
        n_holdings=n,
        effective_bets=eff_bets,
        portfolio_vol=port_vol,
        independent_vol=indep_vol,
        risk_multiple=(port_vol / indep_vol) if indep_vol > 0 else 1.0,
        diversification_ratio=dr,
        mean_correlation=mean_corr,
        standalone_vols=sa_vols,
        risk_contributions=rc,
        expected_return=expected_return,
        sharpe=sharpe,
        risk_free_rate=risk_free_rate,
        correlation=corr,
        covariance=cov,
    )
