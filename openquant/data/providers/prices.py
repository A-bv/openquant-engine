"""
OpenQuant — price provider (yfinance).

Fetches daily adjusted closing prices via yfinance. One module, one source.
yfinance is imported lazily inside ``fetch()`` so importing this module has no
hard dependency. Pulled out of ``openquant/data/data.py``; re-exported by
``openquant.data`` for backward compatibility.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from openquant.config import BETA_LOOKBACK_YEARS

from ..errors import DataFetchError


class PriceFetcher:
    """
    Fetches daily adjusted closing prices.
    Uses yfinance when available, falls back to mock for testing.
    """

    def fetch(
        self,
        ticker: str,
        years: float = BETA_LOOKBACK_YEARS,
    ) -> pd.Series:
        """
        Fetch adjusted closing prices for a ticker.

        Args:
            ticker: Stock ticker symbol.
            years: Years of history to fetch.

        Returns:
            pd.Series of adjusted closing prices, date-indexed.

        Raises:
            DataFetchError: If prices cannot be fetched.
        """
        try:
            import yfinance as yf
            end = datetime.today()
            start = end - timedelta(days=years * 365 + 10)
            data = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
            )
            if data.empty:
                raise DataFetchError(f"No price data found for {ticker}")
            prices = data["Close"]
            if isinstance(prices, pd.DataFrame):
                prices = prices.iloc[:, 0]
            prices.name = ticker
            return prices.dropna()

        except DataFetchError:
            raise  # already typed — don't re-wrap our own error
        except ImportError:
            raise DataFetchError(
                "yfinance is not installed. Run: pip install yfinance"
            )
        except Exception as e:
            raise DataFetchError(f"Price fetch failed for {ticker}: {e}")
