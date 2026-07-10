"""
OpenQuant — Data fetching layer.

Architecture:
- SEC EDGAR as primary source for financial statements (US companies)
  Unlimited, free, official, no API key required.
- yfinance as primary source for price data
- Local CSV cache to avoid repeat fetches and enable offline use
- FMP API as optional enhancement (user provides own key, v2 international)

Dependency rule: zero Streamlit imports. Pure Python. Fully testable.

All external calls wrapped in try/except.
Custom exceptions propagate cleanly to UI layer.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from openquant.config import (
    BETA_LOOKBACK_YEARS,
    CACHE_DIR,
    DEFAULT_MARKET_INDEX,
)

logger = logging.getLogger(__name__)


# ── Custom exceptions ─────────────────────────────────────────────────────────

# Moved to openquant/data/errors.py; re-exported here for backward compatibility.
# ── Cache manager ─────────────────────────────────────────────────────────────
# Moved to openquant/data/cache.py; re-exported here for backward compatibility.
from .cache import CacheManager
from .errors import (
    DataFetchError,
    InsufficientDataError,
    UnsupportedTickerError,
)

# ── Data structures ───────────────────────────────────────────────────────────
# Moved to openquant/data/models.py; re-exported here for backward compatibility.
from .models import FinancialStatements, PriceData, TickerValidation

# ── EDGAR client ──────────────────────────────────────────────────────────────
# Moved to openquant/data/providers/edgar.py; re-exported here for backward compatibility.
from .providers.edgar import EDGARClient

# ── yfinance price fetcher (mock-friendly interface) ─────────────────────────
# Moved to openquant/data/providers/prices.py; re-exported here for backward compatibility.
from .providers.prices import PriceFetcher

# ── Main DataFetcher ──────────────────────────────────────────────────────────

class DataFetcher:
    """
    Main data access object for OpenQuant.

    Orchestrates:
    1. SEC EDGAR for financial statements (US companies)
    2. yfinance for price data
    3. Local cache for all fetched data
    4. Cross-validation between sources

    Usage:
        fetcher = DataFetcher()
        validation = fetcher.validate_ticker("AAPL")
        if validation.is_valid:
            statements = fetcher.get_financial_statements("AAPL")
            prices = fetcher.get_prices("AAPL")
    """

    def __init__(
        self,
        cache_dir: str = CACHE_DIR,
        fmp_api_key: Optional[str] = None,
    ):
        self.cache = CacheManager(cache_dir)
        self.edgar = EDGARClient()
        self.price_fetcher = PriceFetcher()
        self.fmp_api_key = fmp_api_key or os.getenv("FMP_API_KEY")

    def validate_ticker(self, ticker: str) -> TickerValidation:
        """
        Pre-flight validation for a ticker.
        Fast check: 5-day price fetch + CIK lookup.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            TickerValidation with badge (green/amber/red) and message.
        """
        ticker = ticker.upper().strip()

        # Check cache first
        cache_key = f"validation_{ticker}"
        cached = self.cache.get(cache_key, ttl_seconds=3600)  # 1h TTL for validation
        if cached:
            return TickerValidation(**cached)

        # Step 1: CIK lookup — confirms US company
        cik = self.edgar.get_cik(ticker)
        if not cik:
            result = TickerValidation(
                ticker=ticker,
                is_valid=False,
                is_us_company=False,
                company_name="",
                sector="",
                cik=None,
                trading_days_available=0,
                has_financial_statements=False,
                badge="red",
                message=(
                    f"'{ticker}' not found in SEC EDGAR. "
                    f"OpenQuant currently supports US-listed companies only. "
                    f"International coverage coming in v2."
                ),
            )
            return result

        # Steps 2–4: company info, price history, and EDGAR facts in parallel
        def _fetch_company_info():
            try:
                info = self.edgar.get_company_info(cik)
                return info.get("name", ticker), info.get("sic_description", "Unknown")
            except DataFetchError:
                return ticker, "Unknown"

        def _fetch_trading_days():
            try:
                prices = self.price_fetcher.fetch(ticker, years=3)
                return len(prices)
            except DataFetchError:
                return 0

        def _fetch_has_financials():
            try:
                facts = self.edgar.get_facts(cik)
                us_gaap = facts.get("facts", {}).get("us-gaap", {})
                return len(us_gaap) > 10
            except DataFetchError:
                return False

        with ThreadPoolExecutor(max_workers=3) as executor:
            fut_info = executor.submit(_fetch_company_info)
            fut_days = executor.submit(_fetch_trading_days)
            fut_fin  = executor.submit(_fetch_has_financials)

        company_name, sector = fut_info.result()
        trading_days = fut_days.result()
        has_financials = fut_fin.result()

        # Determine badge
        from openquant.config import MIN_PRICE_HISTORY_YEARS, MIN_TRADING_DAYS
        min_days = MIN_TRADING_DAYS * MIN_PRICE_HISTORY_YEARS

        if not has_financials:
            badge = "red"
            message = f"{company_name}: No financial statement data found in EDGAR."
        elif trading_days < min_days:
            badge = "amber"
            message = (
                f"{company_name}: Only {trading_days} days of price history. "
                f"Beta computation may be unreliable (need {min_days}+ days)."
            )
        else:
            badge = "green"
            message = (
                f"{company_name}: Valid. "
                f"{trading_days} trading days available."
            )

        result = TickerValidation(
            ticker=ticker,
            is_valid=badge != "red",
            is_us_company=True,
            company_name=company_name,
            sector=sector,
            cik=cik,
            trading_days_available=trading_days,
            has_financial_statements=has_financials,
            badge=badge,
            message=message,
        )

        # Cache validation result
        self.cache.set(cache_key, {
            "ticker": result.ticker,
            "is_valid": result.is_valid,
            "is_us_company": result.is_us_company,
            "company_name": result.company_name,
            "sector": result.sector,
            "cik": result.cik,
            "trading_days_available": result.trading_days_available,
            "has_financial_statements": result.has_financial_statements,
            "badge": result.badge,
            "message": result.message,
        })

        return result

    def get_financial_statements(self, ticker: str) -> FinancialStatements:
        """
        Fetch and standardise financial statements for a US company.

        Uses SEC EDGAR as primary source.
        All values in USD, annual frequency, last 10 years max.

        Args:
            ticker: Stock ticker symbol (US company).

        Returns:
            FinancialStatements dataclass with all required fields.

        Raises:
            DataFetchError: If EDGAR fetch fails.
            InsufficientDataError: If insufficient history available.
            UnsupportedTickerError: If company not found in EDGAR.
        """
        ticker = ticker.upper().strip()

        # Check cache
        cache_key = f"financials_{ticker}"
        cached = self.cache.get(cache_key)
        if cached:
            return self._deserialise_statements(cached)

        # CIK lookup
        cik = self.edgar.get_cik(ticker)
        if not cik:
            raise UnsupportedTickerError(
                f"{ticker} not found in SEC EDGAR. "
                f"OpenQuant supports US-listed companies only."
            )

        # Company info
        info = self.edgar.get_company_info(cik)
        company_name = info.get("name", ticker)

        # Fetch all XBRL facts
        facts = self.edgar.get_facts(cik)
        warnings = []

        def _extract(concept: str) -> Optional[pd.Series]:
            tags = EDGARClient.TAG_MAPPINGS.get(concept, [])
            series = self.edgar.extract_annual_series(facts, tags)
            if series is None:
                warnings.append(f"Could not find '{concept}' in EDGAR data.")
            return series

        # Extract all components
        revenue = _extract("revenue")
        ebit = _extract("ebit")
        da = _extract("depreciation_amortisation")
        interest = _extract("interest_expense")
        tax = _extract("tax_expense")
        net_income = _extract("net_income")
        capex_raw = _extract("capital_expenditure")
        ocf = _extract("operating_cash_flow")
        debt = _extract("total_debt")
        cash = _extract("cash_and_equivalents")
        total_assets_raw = _extract("total_assets")
        shares_raw = self.edgar.extract_annual_series(
            facts, EDGARClient.TAG_MAPPINGS["shares_outstanding"], unit="shares"
        )
        if shares_raw is None:
            shares_raw = _extract("shares_outstanding")
        shares = shares_raw
        sbc = _extract("stock_based_compensation")
        current_assets = _extract("current_assets")
        current_liabilities = _extract("current_liabilities")

        # Validate minimum required fields
        required = {
            "revenue": revenue,
            "operating_cash_flow": ocf,
            "capital_expenditure": capex_raw,
            "total_debt": debt,
            "shares_outstanding": shares,
        }
        missing = [k for k, v in required.items() if v is None]
        if missing:
            raise InsufficientDataError(
                f"Missing required financial data for {ticker}: {missing}. "
                f"This company may not have sufficient EDGAR filings."
            )

        # Align all series to common index (fiscal year ends)
        # Use last 10 years. `revenue` is guaranteed non-None here by the
        # `missing` required-fields check above.
        assert revenue is not None
        common_idx = revenue.index[-10:] if len(revenue) >= 10 else revenue.index

        def _align(s: Optional[pd.Series]) -> pd.Series:
            if s is None:
                return pd.Series(np.nan, index=common_idx)
            # 45D tolerance: enough for fiscal-year-end date drift between
            # concepts (~2 weeks), but tight enough to reject cross-year
            # nearest-neighbour matches when a series has a gap year.
            return s.reindex(common_idx, method="nearest", tolerance="45D").fillna(np.nan)

        revenue_a = _align(revenue)
        ebit_a = _align(ebit)
        da_a = _align(da)
        interest_a = _align(interest)
        tax_a = _align(tax)
        net_income_a = _align(net_income)
        capex_a = _align(capex_raw).abs()   # Ensure positive
        ocf_a = _align(ocf)
        debt_a = _align(debt)
        cash_a = _align(cash)
        shares_a = _align(shares)
        sbc_a = _align(sbc)
        total_assets_a = _align(total_assets_raw)
        curr_assets_a = _align(current_assets)
        curr_liab_a = _align(current_liabilities)

        # Computed series
        fcf = ocf_a - capex_a
        nwc = curr_assets_a - curr_liab_a

        # Beginning debt (prior year) for average debt cost calculation
        beginning_debt = debt_a.shift(1)

        # Effective tax rate. Replace Inf (from zero-pretax-income years)
        # with NaN before clipping so we don't silently report a 60% rate
        # for what is actually undefined.
        pretax_income = net_income_a + tax_a
        eff_tax = (tax_a / pretax_income).replace([np.inf, -np.inf], np.nan).clip(0, 0.60)

        # FCF margin
        fcf_margin = (fcf / revenue_a).replace([np.inf, -np.inf], np.nan)

        # EBITDA
        ebitda_a = ebit_a + da_a if ebit is not None and da is not None else pd.Series(np.nan, index=common_idx)

        statements = FinancialStatements(
            ticker=ticker,
            company_name=company_name,
            cik=cik,
            source="edgar",
            fetched_at=datetime.now(),
            revenue=revenue_a,
            ebit=ebit_a,
            depreciation_amortisation=da_a,
            interest_expense=interest_a,
            tax_expense=tax_a,
            net_income=net_income_a,
            ebitda=ebitda_a,
            total_assets=total_assets_a,
            total_debt=debt_a,
            beginning_debt=beginning_debt,
            cash_and_equivalents=cash_a,
            shares_outstanding=shares_a,
            net_working_capital=nwc,
            operating_cash_flow=ocf_a,
            capital_expenditure=capex_a,
            free_cash_flow=fcf,
            stock_based_compensation=sbc_a,
            effective_tax_rate=eff_tax,
            fcf_margin=fcf_margin,
            data_warnings=warnings,
        )

        # Cache serialised version
        self.cache.set(cache_key, self._serialise_statements(statements))

        return statements

    def get_prices(
        self,
        ticker: str,
        market_index: str = DEFAULT_MARKET_INDEX,
        years: int = BETA_LOOKBACK_YEARS,
    ) -> PriceData:
        """
        Fetch daily adjusted prices for ticker and market index.

        Args:
            ticker: Stock ticker symbol.
            market_index: Market benchmark ticker. Default ^GSPC.
            years: Years of history.

        Returns:
            PriceData with aligned stock and market price series.

        Raises:
            DataFetchError: If prices cannot be fetched.
        """
        ticker = ticker.upper().strip()

        # Check cache for both series
        stock_key = f"prices_{ticker}_{years}y"
        market_key = f"prices_{market_index}_{years}y"

        stock_prices = self.cache.get_prices(stock_key)
        market_prices = self.cache.get_prices(market_key)

        if stock_prices is None:
            stock_prices = self.price_fetcher.fetch(ticker, years)
            self.cache.set_prices(stock_key, stock_prices)

        if market_prices is None:
            market_prices = self.price_fetcher.fetch(market_index, years)
            self.cache.set_prices(market_key, market_prices)

        # Align to common dates
        common_idx = stock_prices.index.intersection(market_prices.index)
        if len(common_idx) < 252:
            raise InsufficientDataError(
                f"Insufficient overlapping price data for {ticker} "
                f"and {market_index}. Need at least 252 days."
            )

        return PriceData(
            ticker=ticker,
            prices=stock_prices.loc[common_idx],
            market_prices=market_prices.loc[common_idx],
            source="yfinance",
            fetched_at=datetime.now(),
        )

    def get_current_price(self, ticker: str) -> Optional[float]:
        """
        Fetch the latest closing price for a ticker from yfinance.

        Returns None on any failure so callers can fall back gracefully.
        """
        try:
            prices = self.price_fetcher.fetch(ticker, years=0.05)  # ~18 days
            if prices.empty:
                return None
            return float(prices.iloc[-1])
        except Exception:
            return None

    def _serialise_statements(self, s: FinancialStatements) -> dict:
        """Convert FinancialStatements to JSON-serialisable dict."""
        def _series_to_dict(series: pd.Series) -> dict:
            return {str(k): v for k, v in series.items()}

        return {
            "ticker": s.ticker,
            "company_name": s.company_name,
            "cik": s.cik,
            "source": s.source,
            "fetched_at": s.fetched_at.isoformat(),
            "revenue": _series_to_dict(s.revenue),
            "ebit": _series_to_dict(s.ebit),
            "depreciation_amortisation": _series_to_dict(s.depreciation_amortisation),
            "interest_expense": _series_to_dict(s.interest_expense),
            "tax_expense": _series_to_dict(s.tax_expense),
            "net_income": _series_to_dict(s.net_income),
            "ebitda": _series_to_dict(s.ebitda),
            "total_assets": _series_to_dict(s.total_assets),
            "total_debt": _series_to_dict(s.total_debt),
            "beginning_debt": _series_to_dict(s.beginning_debt),
            "cash_and_equivalents": _series_to_dict(s.cash_and_equivalents),
            "shares_outstanding": _series_to_dict(s.shares_outstanding),
            "net_working_capital": _series_to_dict(s.net_working_capital),
            "operating_cash_flow": _series_to_dict(s.operating_cash_flow),
            "capital_expenditure": _series_to_dict(s.capital_expenditure),
            "free_cash_flow": _series_to_dict(s.free_cash_flow),
            "stock_based_compensation": _series_to_dict(s.stock_based_compensation),
            "effective_tax_rate": _series_to_dict(s.effective_tax_rate),
            "fcf_margin": _series_to_dict(s.fcf_margin),
            "data_warnings": s.data_warnings,
        }

    def _deserialise_statements(self, data: dict) -> FinancialStatements:
        """Reconstruct FinancialStatements from cached dict."""
        def _dict_to_series(d: dict) -> pd.Series:
            return pd.Series(
                {pd.Timestamp(k): float(v) if v is not None else np.nan
                 for k, v in d.items()}
            ).sort_index()

        return FinancialStatements(
            ticker=data["ticker"],
            company_name=data["company_name"],
            cik=data["cik"],
            source=data["source"],
            fetched_at=datetime.fromisoformat(data["fetched_at"]),
            revenue=_dict_to_series(data["revenue"]),
            ebit=_dict_to_series(data["ebit"]),
            depreciation_amortisation=_dict_to_series(data["depreciation_amortisation"]),
            interest_expense=_dict_to_series(data["interest_expense"]),
            tax_expense=_dict_to_series(data["tax_expense"]),
            net_income=_dict_to_series(data["net_income"]),
            ebitda=_dict_to_series(data["ebitda"]),
            total_assets=_dict_to_series(data["total_assets"]),
            total_debt=_dict_to_series(data["total_debt"]),
            beginning_debt=_dict_to_series(data["beginning_debt"]),
            cash_and_equivalents=_dict_to_series(data["cash_and_equivalents"]),
            shares_outstanding=_dict_to_series(data["shares_outstanding"]),
            net_working_capital=_dict_to_series(data["net_working_capital"]),
            operating_cash_flow=_dict_to_series(data["operating_cash_flow"]),
            capital_expenditure=_dict_to_series(data["capital_expenditure"]),
            free_cash_flow=_dict_to_series(data["free_cash_flow"]),
            stock_based_compensation=_dict_to_series(data["stock_based_compensation"]),
            effective_tax_rate=_dict_to_series(data["effective_tax_rate"]),
            fcf_margin=_dict_to_series(data["fcf_margin"]),
            data_warnings=data.get("data_warnings", []),
        )
