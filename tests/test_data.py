"""
Tests for openquant/data

All external API calls mocked — no real network calls in tests.
Tests focus on:
- Cache hit/miss behaviour
- Same-source enforcement
- Ticker validation logic
- Serialisation/deserialisation round-trip
- Error handling
"""

import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from openquant.data import (
    CacheManager,
    DataFetcher,
    DataFetchError,
    InsufficientDataError,
    UnsupportedTickerError,
    TickerValidation,
    FinancialStatements,
    PriceData,
)


# ── CacheManager tests ────────────────────────────────────────────────────────

class TestCacheManager:

    def test_set_and_get(self, tmp_path):
        """Basic set/get round-trip."""
        cache = CacheManager(str(tmp_path))
        cache.set("test_key", {"value": 42})
        result = cache.get("test_key", ttl_seconds=None)
        assert result == {"value": 42}

    def test_miss_returns_none(self, tmp_path):
        """Cache miss returns None."""
        cache = CacheManager(str(tmp_path))
        result = cache.get("nonexistent_key")
        assert result is None

    def test_ttl_expiry(self, tmp_path):
        """Expired cache returns None."""
        cache = CacheManager(str(tmp_path))
        cache.set("expiring_key", {"value": 1})
        # Manually age the file
        path = list(tmp_path.glob("*.json"))[0]
        old_time = time.time() - 100
        import os
        os.utime(path, (old_time, old_time))
        result = cache.get("expiring_key", ttl_seconds=50)
        assert result is None

    def test_permanent_cache(self, tmp_path):
        """TTL=None means permanent — never expires."""
        cache = CacheManager(str(tmp_path))
        cache.set("permanent_key", {"value": 99})
        path = list(tmp_path.glob("*.json"))[0]
        old_time = time.time() - 999_999
        import os
        os.utime(path, (old_time, old_time))
        result = cache.get("permanent_key", ttl_seconds=None)
        assert result == {"value": 99}

    def test_prices_round_trip(self, tmp_path):
        """Price series cache round-trip preserves values."""
        cache = CacheManager(str(tmp_path))
        prices = pd.Series(
            [100.0, 105.0, 98.0],
            index=pd.date_range("2020-01-01", periods=3, freq="D"),
        )
        cache.set_prices("price_key", prices)
        result = cache.get_prices("price_key", ttl_seconds=None)
        assert result is not None
        pd.testing.assert_series_equal(
            result.astype(float),
            prices.astype(float),
            check_names=False,
            check_freq=False,
        )

    def test_different_keys_isolated(self, tmp_path):
        """Different keys do not interfere."""
        cache = CacheManager(str(tmp_path))
        cache.set("key_a", {"val": 1})
        cache.set("key_b", {"val": 2})
        assert cache.get("key_a")["val"] == 1
        assert cache.get("key_b")["val"] == 2

    def test_corrupted_cache_returns_none(self, tmp_path):
        """Corrupted cache file returns None gracefully."""
        cache = CacheManager(str(tmp_path))
        cache.set("corrupt_key", {"val": 1})
        # Corrupt the file
        path = list(tmp_path.glob("*.json"))[0]
        path.write_text("not valid json")
        result = cache.get("corrupt_key")
        assert result is None


# ── DataFetcher — ticker validation tests ────────────────────────────────────

class TestTickerValidation:

    def _make_fetcher(self, tmp_path):
        """Create DataFetcher with temp cache."""
        fetcher = DataFetcher(cache_dir=str(tmp_path))
        return fetcher

    def test_unknown_ticker_returns_red(self, tmp_path):
        """Ticker not in EDGAR returns red badge."""
        fetcher = self._make_fetcher(tmp_path)
        with patch.object(fetcher.edgar, 'get_cik', return_value=None):
            result = fetcher.validate_ticker("XXXX_FAKE")
        assert result.badge == "red"
        assert result.is_valid is False
        assert "not found" in result.message.lower()

    def test_valid_us_ticker_returns_green(self, tmp_path):
        """Valid ticker with sufficient data returns green."""
        fetcher = self._make_fetcher(tmp_path)

        mock_prices = pd.Series(
            np.random.randn(1000) + 150,
            index=pd.date_range("2020-01-01", periods=1000, freq="D"),
        )

        with patch.object(fetcher.edgar, 'get_cik', return_value="0000320193"), \
             patch.object(fetcher.edgar, 'get_company_info', return_value={
                 "name": "Apple Inc.", "sic_description": "Technology"
             }), \
             patch.object(fetcher.edgar, 'get_facts', return_value={
                 "facts": {"us-gaap": {f"tag_{i}": {} for i in range(20)}}
             }), \
             patch.object(fetcher.price_fetcher, 'fetch', return_value=mock_prices):
            result = fetcher.validate_ticker("AAPL")

        assert result.badge == "green"
        assert result.is_valid is True
        assert result.company_name == "Apple Inc."
        assert result.cik == "0000320193"

    def test_insufficient_price_history_amber(self, tmp_path):
        """Ticker with few trading days returns amber."""
        fetcher = self._make_fetcher(tmp_path)

        short_prices = pd.Series(
            [100.0] * 100,  # Only 100 days
            index=pd.date_range("2023-01-01", periods=100, freq="D"),
        )

        with patch.object(fetcher.edgar, 'get_cik', return_value="0000320193"), \
             patch.object(fetcher.edgar, 'get_company_info', return_value={
                 "name": "Small Co", "sic_description": "Technology"
             }), \
             patch.object(fetcher.edgar, 'get_facts', return_value={
                 "facts": {"us-gaap": {f"tag_{i}": {} for i in range(20)}}
             }), \
             patch.object(fetcher.price_fetcher, 'fetch', return_value=short_prices):
            result = fetcher.validate_ticker("SMAL")

        assert result.badge == "amber"

    def test_validation_cached(self, tmp_path):
        """Second validation call uses cache — EDGAR not called twice."""
        fetcher = self._make_fetcher(tmp_path)

        mock_prices = pd.Series(
            [100.0] * 1000,
            index=pd.date_range("2020-01-01", periods=1000, freq="D"),
        )

        with patch.object(fetcher.edgar, 'get_cik', return_value="0000320193") as mock_cik, \
             patch.object(fetcher.edgar, 'get_company_info', return_value={
                 "name": "Apple Inc.", "sic_description": "Technology"
             }), \
             patch.object(fetcher.edgar, 'get_facts', return_value={
                 "facts": {"us-gaap": {f"tag_{i}": {} for i in range(20)}}
             }), \
             patch.object(fetcher.price_fetcher, 'fetch', return_value=mock_prices):
            fetcher.validate_ticker("AAPL")
            fetcher.validate_ticker("AAPL")  # Second call

        # CIK should only be looked up once (second call hits cache)
        assert mock_cik.call_count == 1


# ── DataFetcher — financial statements tests ─────────────────────────────────

class TestFinancialStatements:

    def _make_mock_facts(self) -> dict:
        """Create minimal mock XBRL facts for Apple-like company."""
        def _annual_records(values: list, tag: str) -> list:
            records = []
            for i, val in enumerate(values):
                year = 2019 + i
                records.append({
                    "end": f"{year}-09-30",
                    "val": val,
                    "form": "10-K",
                    "fp": "FY",
                    "filed": f"{year}-10-30",
                })
            return records

        revenues = [265_595_000_000, 274_515_000_000, 365_817_000_000,
                    394_328_000_000, 383_285_000_000]
        ocf =      [69_391_000_000,  80_674_000_000,  104_038_000_000,
                    122_151_000_000, 110_543_000_000]
        capex =    [10_495_000_000,  7_309_000_000,   11_085_000_000,
                    10_708_000_000,  10_959_000_000]
        debt =     [108_047_000_000, 112_436_000_000, 119_691_000_000,
                    120_069_000_000, 111_088_000_000]
        shares =   [17_772_944_000, 16_976_763_000,  16_426_786_000,
                    15_943_425_000, 15_634_232_000]

        return {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {"USD": _annual_records(revenues, "revenue")}
                    },
                    "NetCashProvidedByUsedInOperatingActivities": {
                        "units": {"USD": _annual_records(ocf, "ocf")}
                    },
                    "PaymentsToAcquirePropertyPlantAndEquipment": {
                        "units": {"USD": _annual_records(capex, "capex")}
                    },
                    "LongTermDebt": {
                        "units": {"USD": _annual_records(debt, "debt")}
                    },
                    "WeightedAverageNumberOfDilutedSharesOutstanding": {
                        "units": {"shares": _annual_records(shares, "shares")}
                    },
                    "OperatingIncomeLoss": {
                        "units": {"USD": _annual_records(
                            [63_930_000_000, 66_288_000_000, 108_949_000_000,
                             119_437_000_000, 114_301_000_000], "ebit"
                        )}
                    },
                }
            }
        }

    def test_fcf_computed_correctly(self, tmp_path):
        """FCF = OCF - CapEx, verified against known values."""
        fetcher = DataFetcher(cache_dir=str(tmp_path))
        mock_facts = self._make_mock_facts()

        with patch.object(fetcher.edgar, 'get_cik', return_value="0000320193"), \
             patch.object(fetcher.edgar, 'get_company_info', return_value={
                 "name": "Apple Inc.", "sic_description": "Technology"
             }), \
             patch.object(fetcher.edgar, 'get_facts', return_value=mock_facts):
            statements = fetcher.get_financial_statements("AAPL")

        # FCF should equal OCF - CapEx for each year
        expected_fcf = statements.operating_cash_flow - statements.capital_expenditure
        pd.testing.assert_series_equal(
            statements.free_cash_flow.dropna(),
            expected_fcf.dropna(),
            check_names=False,
        )

    def test_capex_always_positive(self, tmp_path):
        """Capital expenditure is always stored as positive outflow."""
        fetcher = DataFetcher(cache_dir=str(tmp_path))
        mock_facts = self._make_mock_facts()

        with patch.object(fetcher.edgar, 'get_cik', return_value="0000320193"), \
             patch.object(fetcher.edgar, 'get_company_info', return_value={
                 "name": "Apple Inc.", "sic_description": "Technology"
             }), \
             patch.object(fetcher.edgar, 'get_facts', return_value=mock_facts):
            statements = fetcher.get_financial_statements("AAPL")

        capex_clean = statements.capital_expenditure.dropna()
        assert (capex_clean >= 0).all(), "CapEx should always be positive"

    def test_unknown_ticker_raises(self, tmp_path):
        """Unknown ticker raises UnsupportedTickerError."""
        fetcher = DataFetcher(cache_dir=str(tmp_path))
        with patch.object(fetcher.edgar, 'get_cik', return_value=None):
            with pytest.raises(UnsupportedTickerError):
                fetcher.get_financial_statements("XXXX_FAKE")

    def test_serialisation_round_trip(self, tmp_path):
        """Serialise and deserialise preserves all values."""
        fetcher = DataFetcher(cache_dir=str(tmp_path))

        idx = pd.date_range("2019-09-30", periods=5, freq="YE")
        original = FinancialStatements(
            ticker="TEST",
            company_name="Test Co",
            cik="0000000001",
            source="edgar",
            fetched_at=datetime.now(),
            revenue=pd.Series([1e9, 2e9, 3e9, 4e9, 5e9], index=idx),
            ebit=pd.Series([1e8, 2e8, 3e8, 4e8, 5e8], index=idx),
            depreciation_amortisation=pd.Series([1e7]*5, index=idx),
            interest_expense=pd.Series([5e6]*5, index=idx),
            tax_expense=pd.Series([2e7]*5, index=idx),
            net_income=pd.Series([8e7]*5, index=idx),
            ebitda=pd.Series([1.1e8]*5, index=idx),
            total_assets=pd.Series([np.nan]*5, index=idx),
            total_debt=pd.Series([5e8]*5, index=idx),
            beginning_debt=pd.Series([4.5e8]*5, index=idx),
            cash_and_equivalents=pd.Series([1e8]*5, index=idx),
            shares_outstanding=pd.Series([1e9]*5, index=idx),
            net_working_capital=pd.Series([2e8]*5, index=idx),
            operating_cash_flow=pd.Series([1.5e8]*5, index=idx),
            capital_expenditure=pd.Series([5e7]*5, index=idx),
            free_cash_flow=pd.Series([1e8]*5, index=idx),
            stock_based_compensation=pd.Series([1e7]*5, index=idx),
            effective_tax_rate=pd.Series([0.21]*5, index=idx),
            fcf_margin=pd.Series([0.10]*5, index=idx),
            data_warnings=[],
        )

        serialised = fetcher._serialise_statements(original)
        restored = fetcher._deserialise_statements(serialised)

        assert restored.ticker == original.ticker
        assert restored.company_name == original.company_name
        pd.testing.assert_series_equal(
            restored.revenue.dropna(),
            original.revenue.dropna(),
            check_names=False,
            check_freq=False,
            rtol=1e-6,
        )
        pd.testing.assert_series_equal(
            restored.free_cash_flow.dropna(),
            original.free_cash_flow.dropna(),
            check_names=False,
            check_freq=False,
            rtol=1e-6,
        )


# ── Price alignment tests ─────────────────────────────────────────────────────

class TestPriceData:

    def test_prices_aligned_to_common_index(self, tmp_path):
        """Stock and market prices aligned to common trading days."""
        fetcher = DataFetcher(cache_dir=str(tmp_path))

        stock_prices = pd.Series(
            np.random.randn(500) + 150,
            index=pd.date_range("2021-01-01", periods=500, freq="D"),
        )
        market_prices = pd.Series(
            np.random.randn(480) + 4000,
            index=pd.date_range("2021-01-15", periods=480, freq="D"),
        )

        with patch.object(fetcher.price_fetcher, 'fetch') as mock_fetch:
            mock_fetch.side_effect = [stock_prices, market_prices]
            result = fetcher.get_prices("AAPL")

        assert len(result.prices) == len(result.market_prices)
        assert result.prices.index.equals(result.market_prices.index)

    def test_insufficient_overlap_raises(self, tmp_path):
        """Raises InsufficientDataError when overlap < 252 days."""
        fetcher = DataFetcher(cache_dir=str(tmp_path))

        stock_prices = pd.Series(
            [100.0] * 300,
            index=pd.date_range("2020-01-01", periods=300, freq="D"),
        )
        # Market prices with minimal overlap
        market_prices = pd.Series(
            [4000.0] * 300,
            index=pd.date_range("2021-06-01", periods=300, freq="D"),
        )

        with patch.object(fetcher.price_fetcher, 'fetch') as mock_fetch:
            mock_fetch.side_effect = [stock_prices, market_prices]
            with pytest.raises(InsufficientDataError):
                fetcher.get_prices("AAPL")


# ── net_debt fallback tests ───────────────────────────────────────────────────

class TestNetDebtFallback:
    """
    Tests for the net_debt / shares fallback logic in the valuation pipeline.

    Mirrors the guards in pages/1_Valuation.py:
        _debt_s  = statements.total_debt.dropna()
        _cash_s  = statements.cash_and_equivalents.dropna()
        net_debt = (
            (_debt_s.iloc[-1]  if not _debt_s.empty  else 0.0)
            - (_cash_s.iloc[-1] if not _cash_s.empty else 0.0)
        )
    """

    @staticmethod
    def _compute(debt_vals, cash_vals):
        """Run the exact fallback logic from the valuation page."""
        idx = pd.date_range("2019-01-01", periods=len(debt_vals), freq="YE")
        d = pd.Series(debt_vals, index=idx).dropna()
        c = pd.Series(cash_vals, index=idx).dropna()
        return (
            (d.iloc[-1] if not d.empty else 0.0)
            - (c.iloc[-1] if not c.empty else 0.0)
        )

    @staticmethod
    def _raises_for_empty_shares(shares_vals):
        """Run the exact shares guard from the valuation page."""
        idx = pd.date_range("2019-01-01", periods=len(shares_vals), freq="YE")
        s = pd.Series(shares_vals, index=idx).dropna()
        if s.empty:
            raise ValueError(
                "No shares outstanding data found in EDGAR. "
                "Cannot compute per-share intrinsic value."
            )
        return s.iloc[-1]

    def test_both_present(self):
        """Normal case: net_debt = most recent debt minus most recent cash."""
        assert self._compute(
            [80e9, 100e9, 120e9],
            [20e9, 25e9,  30e9],
        ) == pytest.approx(90e9)

    def test_uses_most_recent_value(self):
        """iloc[-1] is the latest year, not an earlier one."""
        assert self._compute(
            [50e9, 80e9, 120e9],
            [10e9, 20e9,  25e9],
        ) == pytest.approx(95e9)

    def test_debt_all_nan_defaults_to_zero(self):
        """No debt data → treated as 0; result is net cash (negative net_debt)."""
        result = self._compute(
            [np.nan, np.nan, np.nan],
            [20e9,   25e9,   30e9],
        )
        assert result == pytest.approx(-30e9)

    def test_cash_all_nan_defaults_to_zero(self):
        """No cash data → treated as 0; result equals full debt balance."""
        result = self._compute(
            [100e9, 110e9, 120e9],
            [np.nan, np.nan, np.nan],
        )
        assert result == pytest.approx(120e9)

    def test_both_all_nan_net_debt_is_zero(self):
        """No debt or cash data → net_debt = 0."""
        result = self._compute(
            [np.nan, np.nan],
            [np.nan, np.nan],
        )
        assert result == pytest.approx(0.0)

    def test_partial_nan_uses_latest_non_nan(self):
        """dropna() removes gaps; iloc[-1] picks the most recent valid value."""
        result = self._compute(
            [100e9, np.nan, 120e9],
            [np.nan, 25e9,  np.nan],
        )
        assert result == pytest.approx(120e9 - 25e9)

    def test_shares_present_returns_value(self):
        """Valid shares outstanding returns the most recent value."""
        val = self._raises_for_empty_shares([15e9, 15.5e9, 16e9])
        assert val == pytest.approx(16e9)

    def test_shares_all_nan_raises_value_error(self):
        """Empty shares series must raise ValueError with a clear message."""
        with pytest.raises(ValueError, match="shares outstanding"):
            self._raises_for_empty_shares([np.nan, np.nan, np.nan])
