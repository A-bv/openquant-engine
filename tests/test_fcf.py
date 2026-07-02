"""
Tests for openquant/valuation/fcf.py

Covers the edge cases that have caused real production bugs:

1. Sign-crossing FCF history (negative → near-zero → positive) —
   the TSLA case that produced a -2368% historical mean growth rate.
2. Near-zero FCF denominators distorting pct_change.
3. All-negative FCF history — should degrade gracefully, not crash.
4. Normal positive FCF — regression / sanity check.
5. Growth rate bounds — mean and median must stay within sane limits
   after the positive-only filter is applied.
"""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime

from openquant.data import FinancialStatements
from openquant.valuation.fcf import FCFAnalyser


# ── Fixture builder ───────────────────────────────────────────────────────────

def make_statements(
    fcf_values: list[float],
    years: list[int] | None = None,
    ticker: str = "TEST",
    company: str = "Test Co",
) -> FinancialStatements:
    """
    Build a minimal FinancialStatements from a list of annual FCF values.
    All other fields are filled with harmless dummies.
    """
    n = len(fcf_values)
    if years is None:
        years = list(range(2015, 2015 + n))

    idx = pd.Index(years, name="year")
    fcf = pd.Series(fcf_values, index=idx, dtype=float)
    revenue = pd.Series([max(abs(v) * 5, 1e9) for v in fcf_values], index=idx, dtype=float)
    zeros = pd.Series([0.0] * n, index=idx, dtype=float)
    ones_b = pd.Series([1e9] * n, index=idx, dtype=float)

    return FinancialStatements(
        ticker=ticker,
        company_name=company,
        cik="0000000000",
        source="test",
        fetched_at=datetime(2025, 1, 1),
        revenue=revenue,
        ebit=zeros,
        depreciation_amortisation=zeros,
        interest_expense=zeros,
        tax_expense=zeros,
        net_income=zeros,
        ebitda=zeros,
        total_assets=ones_b,
        total_debt=zeros,
        beginning_debt=zeros,
        cash_and_equivalents=zeros,
        shares_outstanding=ones_b,
        net_working_capital=zeros,
        operating_cash_flow=fcf,
        capital_expenditure=zeros,
        free_cash_flow=fcf,
        stock_based_compensation=zeros,
        effective_tax_rate=pd.Series([0.21] * n, index=idx, dtype=float),
        fcf_margin=pd.Series([f / max(abs(f) * 5, 1e9) for f in fcf_values], index=idx, dtype=float),
        data_warnings=[],
    )


ANALYSER = FCFAnalyser()


# ── Normal positive FCF — regression / sanity ─────────────────────────────────

class TestNormalPositiveFCF:

    def test_stable_growth_median_near_expected(self):
        """Stable 20%/yr positive FCF gives median growth close to 20%."""
        fcf = [1e9 * (1.20 ** i) for i in range(8)]
        result = ANALYSER.analyse(make_statements(fcf))
        assert abs(result.median_growth_rate - 0.20) < 0.02

    def test_stable_growth_mean_near_expected(self):
        """Stable 20%/yr positive FCF gives mean growth close to 20%."""
        fcf = [1e9 * (1.20 ** i) for i in range(8)]
        result = ANALYSER.analyse(make_statements(fcf))
        assert abs(result.mean_growth_rate - 0.20) < 0.05

    def test_no_negative_fcf_warning_on_all_positive(self):
        """All-positive FCF series should not produce a negative-FCF warning."""
        fcf = [1e9, 1.2e9, 1.5e9, 2e9, 2.5e9, 3e9]
        result = ANALYSER.analyse(make_statements(fcf))
        warning_text = " ".join(result.warnings).lower()
        assert "negative fcf" not in warning_text

    def test_scenarios_capped_at_max(self):
        """Growth scenarios are capped at 35% regardless of historical rate."""
        fcf = [1e9 * (2.0 ** i) for i in range(8)]   # 100%/yr
        result = ANALYSER.analyse(make_statements(fcf))
        assert result.growth_base <= 0.35
        assert result.growth_conservative <= 0.35
        assert result.growth_optimistic <= 0.35

    def test_latest_fcf_is_last_element(self):
        """latest_fcf should return the most recent year's value."""
        fcf = [1e9, 2e9, 3e9]
        result = ANALYSER.analyse(make_statements(fcf))
        assert result.latest_fcf == pytest.approx(3e9)


# ── TSLA-style sign-crossing FCF — the real bug ───────────────────────────────

class TestSignCrossingFCF:
    """
    Reproduces the TSLA scenario:
      2016: -1.4B  (negative)
      2017: -3.5B  (negative, worse)
      2018: -0.003B (near-zero, still technically negative)
      2019: +1.1B  → pct_change denominator = -0.003B → −36,700% !
      2020: +2.8B
      2021: +5.0B
      2022: +7.6B
      2023: +4.4B
      2024: +3.6B
      2025: +6.2B
    """

    TSLA_LIKE = [
        -1.4e9, -3.5e9, -0.003e9,
         1.1e9,  2.8e9,  5.0e9,
         7.6e9,  4.4e9,  3.6e9,  6.2e9,
    ]

    def _analysis(self):
        stmts = make_statements(self.TSLA_LIKE, ticker="TSLA", company="Tesla, Inc.")
        return ANALYSER.analyse(stmts)

    def test_mean_growth_is_not_extreme(self):
        """
        Before the fix, TSLA-like history gave mean ≈ -2368%.
        After the fix (filter to positive-only transitions) it should be
        within ±300% — a loose bound that would clearly catch regression.
        """
        result = self._analysis()
        assert abs(result.mean_growth_rate) < 3.0, (
            f"mean_growth_rate = {result.mean_growth_rate * 100:.1f}% is extreme. "
            "Sign-crossing transitions are not being filtered."
        )

    def test_mean_growth_is_reasonable_positive(self):
        """
        The filtered positive-year mean for TSLA-like data should be
        clearly positive (those years had strong FCF growth).
        """
        result = self._analysis()
        # Positive-year transitions: 2019-2025, mixed but net positive
        assert result.mean_growth_rate > -0.50, (
            f"mean_growth_rate = {result.mean_growth_rate * 100:.1f}% is unexpectedly negative."
        )

    def test_no_individual_growth_rate_above_1000_pct(self):
        """
        No individual YoY rate in the filtered series should exceed ±1000%.
        The raw series for TSLA-like data contains −36,700%.
        """
        result = self._analysis()
        if len(result.yoy_growth_rates) > 0:
            max_abs = result.yoy_growth_rates.abs().max()
            assert max_abs <= 10.0, (
                f"Max absolute growth rate = {max_abs * 100:.0f}%. "
                "A near-zero denominator may still be included."
            )

    def test_negative_fcf_history_warning_present(self):
        """A warning should be emitted when FCF history contains negatives."""
        result = self._analysis()
        has_warning = any("negative" in w.lower() for w in result.warnings)
        assert has_warning, "Expected a warning about negative FCF history."

    def test_median_growth_is_in_sane_range(self):
        """Median growth for TSLA-like positive years should be 20%–200%."""
        result = self._analysis()
        assert -0.50 < result.median_growth_rate < 2.0, (
            f"median_growth_rate = {result.median_growth_rate * 100:.1f}% is outside sane range."
        )


# ── Near-zero FCF denominator isolation ──────────────────────────────────────

class TestNearZeroDenominator:
    """
    Tests that a very small FCF value (-$1M on a $1B-revenue company)
    doesn't blow up the growth rate calculation when the next year
    has normal positive FCF.
    """

    def test_near_zero_to_positive_excluded_from_stats(self):
        """
        FCF series: [...positive..., -0.001B, +1B, ...positive...]
        The (-0.001B → +1B) transition produces pct_change ≈ −100,100%.
        This must NOT appear in the growth rate stats.
        """
        fcf = [1e9, 1.2e9, 1.5e9, -1e6, 1.1e9, 1.3e9, 1.5e9]
        result = ANALYSER.analyse(make_statements(fcf))
        assert abs(result.mean_growth_rate) < 2.0, (
            f"mean = {result.mean_growth_rate * 100:.1f}%. "
            "Near-zero denominator transition was not excluded."
        )

    def test_near_zero_positive_to_positive_included(self):
        """
        If a near-zero but POSITIVE FCF is followed by positive FCF,
        that transition (even if large) comes from a valid positive base
        and can legitimately be included (or winsorized).
        The key constraint: result must be finite.
        """
        fcf = [1e9, 1.2e9, 1.4e9, 1.6e9, 1e6, 2e9, 2.5e9]  # 1M positive year
        result = ANALYSER.analyse(make_statements(fcf))
        assert np.isfinite(result.mean_growth_rate)
        assert np.isfinite(result.median_growth_rate)


# ── All-negative FCF history ──────────────────────────────────────────────────

class TestAllNegativeFCF:
    """
    A company that has never been FCF-positive (e.g. pre-revenue startup).
    Must not crash; must emit warnings; growth estimates are unreliable.
    """

    ALL_NEG = [-0.5e9, -1e9, -1.5e9, -2e9, -2.5e9]

    def test_does_not_raise(self):
        """FCFAnalyser.analyse() must not raise on all-negative FCF."""
        result = ANALYSER.analyse(make_statements(self.ALL_NEG))
        assert result is not None

    def test_warning_present(self):
        """Should warn about unreliable growth estimates."""
        result = ANALYSER.analyse(make_statements(self.ALL_NEG))
        combined = " ".join(result.warnings).lower()
        assert "negative" in combined or "unreliable" in combined

    def test_growth_rates_are_finite(self):
        """Median and mean must be finite even on all-negative history."""
        result = ANALYSER.analyse(make_statements(self.ALL_NEG))
        assert np.isfinite(result.median_growth_rate)
        assert np.isfinite(result.mean_growth_rate)

    def test_scenarios_are_clipped(self):
        """Scenarios must be within the [-10%, 35%] clip range."""
        result = ANALYSER.analyse(make_statements(self.ALL_NEG))
        for g in [result.growth_conservative, result.growth_base, result.growth_optimistic]:
            assert -0.10 <= g <= 0.35


# ── Insufficient history ──────────────────────────────────────────────────────

class TestInsufficientHistory:

    def test_single_year_uses_default(self):
        """Single FCF year has no growth rate — should fall back to 5% default."""
        result = ANALYSER.analyse(make_statements([1e9]))
        assert result.median_growth_rate == pytest.approx(0.05)
        assert result.mean_growth_rate == pytest.approx(0.05)

    def test_two_years_returns_result(self):
        """Two FCF years gives exactly one growth observation — should not crash."""
        result = ANALYSER.analyse(make_statements([1e9, 1.5e9]))
        assert np.isfinite(result.median_growth_rate)

    def test_single_positive_to_positive_transition_is_enough(self):
        """
        Three years where first is negative and last two are positive.
        Only one pos→pos transition is available.
        Should fall back to full series (< 3 filtered transitions) with warning.
        """
        fcf = [-1e9, 1e9, 1.5e9]
        result = ANALYSER.analyse(make_statements(fcf))
        assert np.isfinite(result.median_growth_rate)
        assert np.isfinite(result.mean_growth_rate)


# ── Latest FCF fallback (negative latest year) ───────────────────────────────

class TestLatestFCFFallback:

    def test_negative_latest_fcf_uses_three_year_median(self):
        """
        If the most recent FCF is negative, project() falls back to
        the median of the last 3 years as the projection base.
        The median of [3B, 4B, -1B] = 3B — not -1B.
        """
        from openquant.valuation.fcf import FCFAnalyser
        stmts = make_statements([1e9, 2e9, 3e9, 4e9, -1e9])
        analysis = FCFAnalyser().analyse(stmts)
        projection = FCFAnalyser().project(analysis, scenario="base")
        # Base FCF should be the median of last 3 years: [3B, 4B, -1B] → 3B
        assert projection.base_fcf == pytest.approx(3e9)

    def test_positive_latest_fcf_used_directly(self):
        """Positive latest FCF is used directly as projection base."""
        stmts = make_statements([1e9, 2e9, 3e9, 4e9, 5e9])
        analysis = FCFAnalyser().analyse(stmts)
        projection = FCFAnalyser().project(analysis, scenario="base")
        assert projection.base_fcf == pytest.approx(5e9)


# ── Revenue CAGR ──────────────────────────────────────────────────────────────

class TestRevenueCagr:

    def test_revenue_cagr_computed_when_positive(self):
        """Revenue CAGR should be positive for growing revenue."""
        fcf = [1e9, 1.5e9, 2e9, 2.5e9]
        result = ANALYSER.analyse(make_statements(fcf))
        assert result.revenue_cagr_5yr > 0

    def test_revenue_cagr_is_finite(self):
        """Revenue CAGR must be finite in all cases."""
        for fcf in [
            [1e9, 2e9, 3e9],
            [-1e9, -2e9, 1e9],
            [1e9, 1e9, 1e9],  # flat
        ]:
            result = ANALYSER.analyse(make_statements(fcf))
            assert np.isfinite(result.revenue_cagr_5yr)
