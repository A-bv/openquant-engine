"""
Point-in-time EDGAR data fetcher for backtests.

Returns financial statements as they would have been visible to an analyst
on a specific historical date — filtering out:

  1. Filings made AFTER the as-of date (look-ahead bias)
  2. Restatements: keep the FIRST filed version of each fiscal year's data,
     not the most recently filed (which may incorporate post-as-of revisions)
  3. Fiscal years ending after the as-of date

Wraps `openquant.data.EDGARClient` — does not re-implement HTTP or auth.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd

from openquant.data import (
    EDGARClient,
    FinancialStatements,
    InsufficientDataError,
    PriceData,
    PriceFetcher,
    UnsupportedTickerError,
)

# Historical XBRL tags — companies switched tags over the years.
# Extending the live TAG_MAPPINGS with older variants so historical filings
# resolve cleanly. Do not modify openquant/data — keep production unchanged.
_HISTORICAL_EXTRA_TAGS: dict[str, list[str]] = {
    "capital_expenditure": [
        "PaymentsToAcquireProductiveAssets",      # AAPL pre-2018
        "PaymentsToAcquireOtherProductiveAssets",
        "PaymentsForProceedsFromProductiveAssets",
    ],
    "revenue": [
        "SalesRevenueNet",                         # very common pre-2018
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "shares_outstanding": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
    "total_debt": [
        "LongTermDebtAndShortTermBorrowings",
        "LongTermDebtCurrent",
    ],
    "tax_expense": [
        "IncomeTaxExpenseBenefitContinuingOperations",
    ],
    "interest_expense": [
        "InterestIncomeExpenseNet",
        "InterestExpenseDebt",
    ],
    "depreciation_amortisation": [
        "Depreciation",
        "DepreciationDepletionAndAmortization",
    ],
}


def _expanded_tags(concept: str) -> list[str]:
    """All tags for a concept: live mappings + historical variants."""
    base = list(EDGARClient.TAG_MAPPINGS.get(concept, []))
    extra = _HISTORICAL_EXTRA_TAGS.get(concept, [])
    # Preserve order, dedupe
    seen, out = set(), []
    for t in base + extra:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out


def _extract_balance_as_of(
    facts: dict,
    concept_tags: list[str],
    as_of: date,
    unit: str = "USD",
) -> Optional[pd.Series]:
    """
    Point-in-time extraction for BALANCE-SHEET concepts (shares, debt, cash).

    Pre-2014 XBRL adoption in 10-K filings was patchy; many companies only
    tagged balance-sheet items quarterly. For point-in-time concepts a
    10-Q reading is interchangeable with a 10-K reading — the value is
    the balance on the period-end date, not a duration.

    Accepts ANY form (10-K, 10-Q, 10-K/A, 10-Q/A) and any `fp` value.
    Returns a series indexed by period-end date.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    as_of_str = as_of.isoformat()
    candidates = []
    for tag in concept_tags:
        if tag not in us_gaap:
            continue
        tag_units = us_gaap[tag].get("units", {})
        unit_to_use = unit if unit in tag_units else next(iter(tag_units), None)
        if not unit_to_use:
            continue
        records = tag_units[unit_to_use]
        eligible = [
            r for r in records
            if "end" in r and "filed" in r
            and r["filed"] <= as_of_str
            and r["end"] <= as_of_str
        ]
        if not eligible:
            continue
        by_date: dict = {}
        for r in eligible:
            end = r["end"]
            if end not in by_date or r["filed"] < by_date[end]["filed"]:
                by_date[end] = r
        candidates.append(
            pd.Series({pd.Timestamp(end): r["val"] for end, r in by_date.items()}).sort_index()
        )
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.index.max())


def _extract_series_as_of(
    facts: dict,
    concept_tags: list[str],
    as_of: date,
    unit: str = "USD",
) -> Optional[pd.Series]:
    """
    Point-in-time variant of `EDGARClient.extract_annual_series`.

    Two changes vs the live version:
      - Reject records with `filed` date AFTER as_of (would be look-ahead)
      - For each fiscal year end, keep the FIRST filed value, not the most
        recent — restatements after as_of are invisible to an analyst standing
        at as_of
      - Reject fiscal periods ending AFTER as_of (forward data)
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    as_of_str = as_of.isoformat()

    candidates = []

    for tag in concept_tags:
        if tag not in us_gaap:
            continue

        tag_units = us_gaap[tag].get("units", {})
        unit_to_use = unit if unit in tag_units else next(iter(tag_units), None)
        if not unit_to_use:
            continue

        records = tag_units[unit_to_use]

        # Filter for annual 10-K filings, period not in future, filed before as_of
        annual = [
            r for r in records
            if r.get("form") in ("10-K", "10-K/A")
            and r.get("fp") == "FY"
            and "end" in r
            and "filed" in r
            and r["filed"] <= as_of_str          # ← reject post-as-of filings
            and r["end"] <= as_of_str            # ← reject future-ended periods
            and (
                "start" not in r
                or (pd.Timestamp(r["end"]) - pd.Timestamp(r["start"])).days >= 340
            )
        ]

        if not annual:
            continue

        # Deduplicate by period-end: keep the FIRST filing (oldest `filed` date).
        # This is the point-in-time version: an analyst at as_of saw the
        # earliest available filing of each fiscal year.
        by_date: dict = {}
        for r in annual:
            end = r["end"]
            if end not in by_date or r["filed"] < by_date[end]["filed"]:
                by_date[end] = r

        if not by_date:
            continue

        candidates.append(
            pd.Series(
                {pd.Timestamp(end): r["val"] for end, r in by_date.items()}
            ).sort_index()
        )

    if not candidates:
        return None

    return max(candidates, key=lambda s: s.index.max())


def fetch_statements_as_of(
    ticker: str,
    as_of: date,
    edgar: Optional[EDGARClient] = None,
) -> FinancialStatements:
    """
    Build a FinancialStatements object reflecting what was knowable on `as_of`.

    Args:
        ticker: US stock ticker (case-insensitive).
        as_of: The point-in-time date. Filings made after this date are
            ignored; restatements are filtered out.
        edgar: Optional injected EDGARClient (for testing). If None, a
            fresh client is created.

    Returns:
        FinancialStatements with up to 10 years of data ending on or before
        `as_of`.

    Raises:
        UnsupportedTickerError: If the company can't be found in EDGAR.
        InsufficientDataError: If <2 fiscal years of revenue are available
            by `as_of` (model can't run).
    """
    ticker = ticker.upper().strip()
    edgar = edgar or EDGARClient()

    cik = edgar.get_cik(ticker)
    if not cik:
        raise UnsupportedTickerError(f"{ticker} not in EDGAR.")

    info = edgar.get_company_info(cik)
    company_name = info.get("name", ticker)

    facts = edgar.get_facts(cik)

    def _ex(concept: str, unit: str = "USD") -> Optional[pd.Series]:
        tags = _expanded_tags(concept)
        return _extract_series_as_of(facts, tags, as_of, unit=unit)

    def _ex_balance(concept: str, unit: str = "USD") -> Optional[pd.Series]:
        """For point-in-time concepts: accept 10-Q in addition to 10-K."""
        tags = _expanded_tags(concept)
        return _extract_balance_as_of(facts, tags, as_of, unit=unit)

    revenue = _ex("revenue")
    if revenue is None or len(revenue.dropna()) < 2:
        raise InsufficientDataError(
            f"Not enough revenue history for {ticker} as of {as_of}."
        )

    ebit = _ex("ebit")
    da = _ex("depreciation_amortisation")
    interest = _ex("interest_expense")
    tax = _ex("tax_expense")
    net_income = _ex("net_income")
    capex_raw = _ex("capital_expenditure")
    ocf = _ex("operating_cash_flow")
    # Balance-sheet items: accept 10-Q in addition to 10-K (pre-2014 XBRL
    # adoption in 10-K filings was patchy for many companies, especially
    # energy and financials).
    debt = _ex_balance("total_debt")
    cash = _ex_balance("cash_and_equivalents")
    total_assets_raw = _ex_balance("total_assets")
    shares_raw = _extract_balance_as_of(
        facts, _expanded_tags("shares_outstanding"), as_of, unit="shares"
    )
    if shares_raw is None:
        shares_raw = _ex_balance("shares_outstanding")
    current_assets = _ex_balance("current_assets")
    current_liabilities = _ex_balance("current_liabilities")
    # Flows stay strict 10-K only:
    sbc = _ex("stock_based_compensation")

    required = {
        "revenue": revenue,
        "operating_cash_flow": ocf,
        "capital_expenditure": capex_raw,
        "total_debt": debt,
        "shares_outstanding": shares_raw,
    }
    missing = [k for k, v in required.items() if v is None]
    if missing:
        raise InsufficientDataError(
            f"As of {as_of}, {ticker} missing required fields: {missing}."
        )

    # Align all series to revenue's last-10-years index, just like openquant/data
    common_idx = revenue.index[-10:] if len(revenue) >= 10 else revenue.index

    def _align(s: Optional[pd.Series]) -> pd.Series:
        """Flow concepts (annual 10-K): require ≤45-day match to fiscal-year-end."""
        if s is None:
            return pd.Series(np.nan, index=common_idx)
        return s.reindex(common_idx, method="nearest", tolerance="45D").fillna(np.nan)

    def _align_balance(s: Optional[pd.Series]) -> pd.Series:
        """
        Point-in-time concepts (shares, debt, cash, etc.). For each
        fiscal-year-end date in common_idx, pick the most recent
        observation in `s` at or before that date — this is the
        "what was the balance reported by year-end" semantics, even
        when the data came from quarterly filings (Mar/Jun/Sep).
        """
        if s is None:
            return pd.Series(np.nan, index=common_idx)
        s_sorted = s.sort_index()
        out = []
        for fye in common_idx:
            candidates = s_sorted[s_sorted.index <= fye]
            out.append(float(candidates.iloc[-1]) if len(candidates) > 0 else np.nan)
        return pd.Series(out, index=common_idx, dtype=float)

    revenue_a = _align(revenue)
    ebit_a = _align(ebit)
    da_a = _align(da)
    interest_a = _align(interest)
    tax_a = _align(tax)
    net_income_a = _align(net_income)
    capex_a = _align(capex_raw).abs()
    ocf_a = _align(ocf)
    debt_a = _align_balance(debt)
    cash_a = _align_balance(cash)
    # Normalize XBRL unit inconsistencies: some companies (e.g. MRK 2012 10-K)
    # report shares in millions while other quarters of the same series use
    # raw counts. Detect this by comparing each value to the series median;
    # any reading more than 1000× smaller than the median is upscaled.
    if shares_raw is not None and len(shares_raw.dropna()) >= 3:
        med = shares_raw.dropna().median()
        if med > 1e7:  # series median in raw-units territory
            shares_raw = shares_raw.where(
                shares_raw > med / 1000.0,
                shares_raw * 1e6,  # presumed millions → upscale by 1M
            )

    # Scale shares up by cumulative post-as_of splits so downstream WACC /
    # DCF math (which reads `statements.shares_outstanding`) sees shares in
    # the same units as the yfinance split-adjusted prices used elsewhere.
    split_ratio = cumulative_split_ratio_after(ticker, as_of)
    shares_a = _align_balance(shares_raw) * split_ratio
    sbc_a = _align(sbc)
    total_assets_a = _align_balance(total_assets_raw)
    curr_assets_a = _align_balance(current_assets)
    curr_liab_a = _align_balance(current_liabilities)

    fcf = ocf_a - capex_a
    nwc = curr_assets_a - curr_liab_a
    beginning_debt = debt_a.shift(1)

    pretax_income = net_income_a + tax_a
    eff_tax = (
        (tax_a / pretax_income)
        .replace([np.inf, -np.inf], np.nan)
        .clip(0, 0.60)
    )
    fcf_margin = (fcf / revenue_a).replace([np.inf, -np.inf], np.nan)
    ebitda_a = ebit_a + da_a if ebit is not None and da is not None else pd.Series(np.nan, index=common_idx)

    return FinancialStatements(
        ticker=ticker,
        company_name=company_name,
        cik=cik,
        source="edgar-historical",
        fetched_at=datetime.combine(as_of, datetime.min.time()),
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
        data_warnings=[],
    )


def fetch_prices_as_of(
    ticker: str,
    as_of: date,
    lookback_years: int = 5,
    price_fetcher: Optional[PriceFetcher] = None,
) -> PriceData:
    """
    Fetch daily prices ending on `as_of`, with `lookback_years` of history.

    Returns prices for both the stock and ^GSPC (S&P 500). The
    final close on or before `as_of` is the "current price" at that time.
    """
    import yfinance as yf
    from dateutil.relativedelta import relativedelta

    end = pd.Timestamp(as_of)
    start = end - relativedelta(years=lookback_years)

    stock = yf.Ticker(ticker).history(
        start=start.strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
    )["Close"]
    market = yf.Ticker("^GSPC").history(
        start=start.strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
    )["Close"]

    if stock.empty:
        raise InsufficientDataError(f"No price data for {ticker} before {as_of}.")

    # Strip timezone if present for safe joining
    if stock.index.tz is not None:
        stock.index = stock.index.tz_localize(None)
    if market.index.tz is not None:
        market.index = market.index.tz_localize(None)

    return PriceData(
        ticker=ticker,
        prices=stock,
        market_prices=market,
        source="yfinance-historical",
        fetched_at=datetime.combine(as_of, datetime.min.time()),
    )


def cumulative_split_ratio_after(ticker: str, as_of: date) -> float:
    """
    Return the product of all split ratios that occurred STRICTLY AFTER `as_of`.

    yfinance always returns split-adjusted closes. EDGAR returns raw share
    counts as filed. To reconcile: scale EDGAR shares UP by this ratio so
    they match adjusted-price space.

    Example: AAPL Jan 2014 — after Jan 31, 2014 there was a 7:1 split (June 2014)
    and a 4:1 split (August 2020). Cumulative ratio = 28.
    EDGAR shares of 925M × 28 = 25,900M (matches today's "as-if-all-splits"
    equivalent of FY2013 shares).
    """
    import yfinance as yf
    splits = yf.Ticker(ticker).splits
    if splits.empty:
        return 1.0
    as_of_ts = pd.Timestamp(as_of)
    if splits.index.tz is not None:
        as_of_ts = as_of_ts.tz_localize(splits.index.tz)
    after = splits[splits.index > as_of_ts]
    if after.empty:
        return 1.0
    return float(after.prod())


def get_price_on(ticker: str, as_of: date, adjusted: bool = False) -> float:
    """
    The last close on or before `as_of`.

    Two modes:
      - adjusted=False (default): RAW close in the dollars of `as_of`.
        Use this for market-cap calculations (raw close × raw shares).
      - adjusted=True: split- and dividend-adjusted close. Use for
        computing total return between dates.

    EDGAR reports raw share counts (pre-split), so mixing adjusted prices
    with EDGAR shares produces a nonsense market cap. Always use raw for
    market cap.
    """
    import yfinance as yf
    end = pd.Timestamp(as_of)
    start = end - pd.Timedelta(days=10)
    hist = yf.Ticker(ticker).history(
        start=start.strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=adjusted,
    )["Close"]
    if hist.empty:
        raise InsufficientDataError(f"No price for {ticker} near {as_of}.")
    return float(hist.iloc[-1])


def realized_total_return(ticker: str, start_date: date, end_date: date) -> float:
    """
    Adjusted total return between two dates (price + dividends, split-adjusted).
    Returns the gross multiple (1.0 = breakeven, 2.0 = +100%).
    """
    import yfinance as yf
    hist = yf.Ticker(ticker).history(
        start=(pd.Timestamp(start_date) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        end=(pd.Timestamp(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,    # adjusted for TSR
    )["Close"]
    if hist.empty:
        raise InsufficientDataError(f"No price data for {ticker} between {start_date} and {end_date}.")
    # yfinance returns tz-aware index — normalize for comparison
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    if hist.index.tz is not None:
        start_ts = start_ts.tz_localize(hist.index.tz)
        end_ts = end_ts.tz_localize(hist.index.tz)
    p_start = float(hist[hist.index <= start_ts].iloc[-1])
    p_end = float(hist[hist.index <= end_ts].iloc[-1])
    return p_end / p_start
