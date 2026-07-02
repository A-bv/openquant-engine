"""
Regression tests for the bugs surfaced by the round 1-4 code review.

Each test pins the corrected behaviour for one fix. If a future refactor
silently reverts the fix, the corresponding test fails.

Grouped by module. Tests for negative-equity IV preservation and the
log-return annualisation formula already live in test_dcf.py and
test_utils.py respectively.
"""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from openquant.data import FinancialStatements
from openquant.valuation.dcf import DCFEngine
from openquant.valuation.fcf import FCFAnalyser
from openquant.valuation.suitability import (
    SuitabilityChecker,
    SuitabilityRating,
)
from openquant.valuation.wacc import WACCResult, WACCBuilder


# ── Helpers (mirrors test_dcf.make_statements) ───────────────────────────────

def make_statements(fcf_values, ticker="TEST", revenue_values=None):
    n = len(fcf_values)
    idx = pd.Index(list(range(2015, 2015 + n)), name="year")
    fcf = pd.Series(fcf_values, index=idx, dtype=float)
    if revenue_values is None:
        revenue = pd.Series([max(abs(v) * 5, 1e9) for v in fcf_values], index=idx, dtype=float)
    else:
        revenue = pd.Series(revenue_values, index=idx, dtype=float)
    zeros = pd.Series([0.0] * n, index=idx, dtype=float)
    ones_b = pd.Series([1e9] * n, index=idx, dtype=float)
    return FinancialStatements(
        ticker=ticker, company_name="Test Co", cik="0000000000", source="test",
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


# ── Fix #10: WACC <= 0 must raise, not silently produce inflated IV ──────────

class TestWACCRejectsBadValues:

    def test_zero_market_cap_raises_not_silent(self):
        """firm_value = 0 (no market cap, no debt) must raise ValueError
        rather than letting an unusable WACC propagate downstream."""
        from tests.test_dcf import make_statements as ts_make
        from openquant.data import PriceData
        st = ts_make([1e9] * 5)
        idx = pd.date_range("2020-01-01", periods=300)
        prices = pd.Series(np.linspace(100, 110, 300), index=idx)
        pd_data = PriceData(
            ticker="TEST", prices=prices, market_prices=prices,
            source="test", fetched_at=datetime(2025, 1, 1),
        )
        # current_price=0 → market_cap=0 → firm_value=0 → must raise
        with pytest.raises(ValueError, match="firm value|WACC"):
            WACCBuilder().compute_wacc(st, pd_data, current_share_price=0.0)


# Fix #13 (portfolio weights sum guard) was removed when the portfolio
# module was deleted as part of the v1.0 scope tightening (equity valuation
# only). The helper `min_variance_two_asset_weight` remains in openquant/common/utils.py
# and is tested in tests/test_epfl_exam2.py against the EPFL exam answer key.


# ── Fix #15: base_fcf fallback must not project from a negative base ─────────

class TestFCFProjectionPositiveBase:

    def test_all_negative_history_raises(self):
        """When no positive FCF year exists, project() must refuse."""
        st = make_statements([-1e9, -2e9, -3e9, -4e9, -5e9])
        analysis = FCFAnalyser().analyse(st)
        with pytest.raises(ValueError, match="no positive FCF"):
            FCFAnalyser().project(analysis, scenario="base")

    def test_recent_positive_year_used_as_base(self):
        """Negative latest year but positive history → use positive median."""
        st = make_statements([1e9, 1.2e9, 1.5e9, 1.8e9, -0.5e9])
        analysis = FCFAnalyser().analyse(st)
        proj = FCFAnalyser().project(analysis, scenario="base")
        # Base must be drawn from the positive years, never negative
        assert proj.base_fcf > 0


# ── Fix #11: RED diagnostic dimensions must still surface with blocking ─────

class TestRedFlagsSurfaceWithBlocking:

    def test_red_dimensions_not_suppressed_by_blocking(self):
        """A blocking suitability issue must not hide RED diagnostic dims."""
        from openquant.valuation.red_flags import RedFlagBuilder
        from openquant.valuation.suitability import (
            SuitabilityReport, SuitabilityCheck, SuitabilityCheckName,
        )
        from openquant.valuation.assumption_diagnostic import (
            AssumptionDiagnostic, DimensionScore, DiagnosticRating,
        )
        blocking = SuitabilityCheck(
            name=SuitabilityCheckName.SECTOR, passed=False,
            rating=SuitabilityRating.RED, message="Sector unsupported.",
        )
        # blocking_issues is a @property on SuitabilityReport derived from
        # checks; just pass the blocking check through `checks` and the
        # property surfaces it.
        report = SuitabilityReport(
            ticker="TEST", company_name="Test Co",
            overall_rating=SuitabilityRating.RED, is_suitable=False,
            checks=[blocking], recommendation="Do not proceed.",
        )
        red_dim = DimensionScore(
            name="FCF Quality", severity=2, rating=DiagnosticRating.RED,
            message="Persistent losses.",
        )
        diag = AssumptionDiagnostic(
            ticker="TEST",
            overall_rating=DiagnosticRating.RED,
            total_severity=2,
            dimensions=[red_dim],
        )
        summary = RedFlagBuilder().build(
            ticker="TEST", diagnostic=diag, suitability=report,
        )
        joined = " ".join(summary.flags)
        # Both the block and the RED dim must appear
        assert "Sector unsupported" in joined
        assert "FCF Quality" in joined, (
            "RED diagnostic dimension was suppressed by the blocking issue — "
            "regression of round-2 fix #11."
        )
        # has_blocking_issues bookkeeping must still be set
        assert summary.has_blocking_issues is True


# ── Fix #21: suitability cyclicality must filter sign-crossing pct_change ────

class TestCyclicalityIgnoresSignCross:

    def test_one_negative_year_does_not_flip_to_red(self):
        """
        A single negative-FCF year surrounded by growth should not produce
        a fake '-N00%/yr declining' median that paints the company RED.
        """
        # Healthy growing FCF with one transient loss year
        fcf = [1e9, 1.2e9, -0.3e9, 1.4e9, 1.7e9, 2.0e9]
        st = make_statements(fcf)
        check = SuitabilityChecker()._check_fcf_cyclicality(st)
        # Pre-fix: median of pct_change including sign-cross was ~ -1.25
        # which fired the < -0.10 RED branch. Post-fix: sign-crossing
        # transitions are excluded, so the check must NOT be RED.
        assert check.rating != SuitabilityRating.RED, (
            f"Sign-crossing pct_change was not filtered — got rating "
            f"{check.rating} with message: {check.message}"
        )


# ── Fix #7: AnalyseRequest validation ────────────────────────────────────────

class TestAnalyseRequestValidation:

    def _model(self):
        from api.main import AnalyseRequest
        return AnalyseRequest

    def test_rejects_negative_risk_free_rate(self):
        with pytest.raises(ValidationError):
            self._model()(ticker="AAPL", risk_free_rate=-0.05)

    def test_rejects_excessive_risk_free_rate(self):
        with pytest.raises(ValidationError):
            self._model()(ticker="AAPL", risk_free_rate=0.5)

    def test_rejects_oversized_ticker(self):
        with pytest.raises(ValidationError):
            self._model()(ticker="A" * 50)

    def test_rejects_path_traversal_ticker(self):
        with pytest.raises(ValidationError):
            self._model()(ticker="../etc/passwd")

    def test_rejects_nonfinite_rate(self):
        with pytest.raises(ValidationError):
            self._model()(ticker="AAPL", risk_free_rate=math.nan)

    def test_accepts_valid_request(self):
        # Sanity check the constraints don't reject legitimate inputs
        req = self._model()(
            ticker="AAPL", risk_free_rate=0.045,
            market_risk_premium=0.055, terminal_growth=0.025,
        )
        assert req.ticker == "AAPL"


# ── Fix #27: 500 handler must not leak internal exception messages ──────────

class TestErrorLeakage:

    def test_500_handler_returns_generic_message_with_request_id(self, monkeypatch):
        """An uncaught exception inside analyse() must return a generic
        message with a request_id, not the raw str(e)."""
        from fastapi import HTTPException
        from api.main import analyse, AnalyseRequest

        def _boom(self, ticker):
            raise RuntimeError(
                "internal path /Users/secret/file.py: full traceback here"
            )
        monkeypatch.setattr("openquant.data.DataFetcher.validate_ticker", _boom)

        req = AnalyseRequest(ticker="AAPL")
        with pytest.raises(HTTPException) as exc_info:
            analyse(req)
        assert exc_info.value.status_code == 500
        detail = exc_info.value.detail
        # Must not echo the raw internal message
        assert "/Users/secret" not in str(detail)
        assert "traceback" not in str(detail).lower()
        # Must give the caller something to quote
        assert "request_id" in detail


# ── Fix #3: NaN/Inf sanitization — unit test on the helper ──────────────────

class TestSanitizeHelper:

    def test_nan_becomes_none(self):
        from api.main import _sanitize
        assert _sanitize({"x": float("nan")}) == {"x": None}

    def test_inf_becomes_none(self):
        from api.main import _sanitize
        assert _sanitize({"x": float("inf"), "y": float("-inf")}) == {"x": None, "y": None}

    def test_recurses_into_nested_structures(self):
        from api.main import _sanitize
        obj = {"a": [1.0, float("nan"), {"b": float("inf")}], "c": (float("nan"),)}
        out = _sanitize(obj)
        assert out == {"a": [1.0, None, {"b": None}], "c": [None]}

    def test_preserves_finite_floats(self):
        from api.main import _sanitize
        assert _sanitize({"x": 1.5, "y": 0.0, "z": -3.14}) == {"x": 1.5, "y": 0.0, "z": -3.14}


# ── Fix #26: CORS regex must reject attacker-controlled subdomains ──────────

class TestCORSRegex:

    def test_regex_rejects_arbitrary_vercel_subdomain(self):
        import re
        from api.main import _ALLOWED_ORIGIN_REGEX
        pat = re.compile(_ALLOWED_ORIGIN_REGEX)
        # An attacker-controlled Vercel app must NOT match
        assert pat.fullmatch("https://attacker.vercel.app") is None
        assert pat.fullmatch("https://evil-app.vercel.app") is None

    def test_regex_accepts_project_subdomain(self):
        import re
        from api.main import _ALLOWED_ORIGIN_REGEX
        pat = re.compile(_ALLOWED_ORIGIN_REGEX)
        # The project's own Vercel deployments must match
        assert pat.fullmatch("https://openquant.vercel.app") is not None
        assert pat.fullmatch("https://openquant-abc123.vercel.app") is not None


# ── Fix #9: multiples must compute fcf_yield when fcf is exactly 0 ──────────

class TestMultiplesFalsyZero:

    def test_zero_fcf_does_not_skip_yield(self):
        """A company with exactly zero FCF should report 0% yield, not None."""
        from openquant.valuation.multiples import MultiplesAnalyser
        st = make_statements([0.0, 0.0, 0.0, 0.0, 0.0])
        result = MultiplesAnalyser().compute(
            st, current_price=10.0, total_debt=0.0, cash=0.0,
        )
        # fcf_latest=0 with shares=1e9 and price=10 → fcf_yield = 0/10 = 0
        # Pre-fix the `if fcf_latest` falsy check skipped the branch entirely.
        assert result.fcf_yield == 0.0
