"""
OpenQuant — live diversification demo.

Proves the Risk & Return block (EPFL Sample Exam 2) on REAL market data:
fetches daily adjusted closes from yfinance (the same price source the app
uses), then prints the two-layer "X independent bets" deliverable.

Usage:
    python scripts/demo_diversification.py                 # default tech basket
    python scripts/demo_diversification.py AAPL MSFT JPM XOM GLD TLT
"""

from __future__ import annotations

import os
import sys

# Make the repo root importable when run as `python scripts/demo_diversification.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import yfinance as yf

from openquant.common import log_returns
from openquant.portfolio import analyse_diversification

DEFAULT_BASKET = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META"]
YEARS = 3


def fetch_log_returns(tickers: list[str], years: int = YEARS) -> pd.DataFrame:
    """Daily log returns for the tickers, aligned on common dates."""
    raw = yf.download(
        tickers, period=f"{years}y", progress=False, auto_adjust=True
    )
    close = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw
    close = close[tickers].dropna(how="any")
    returns = pd.DataFrame({t: log_returns(close[t]) for t in tickers}).dropna()
    return returns


def render(report) -> None:
    print("\n" + "=" * 68)
    print(f"  DIVERSIFICATION — {', '.join(report.tickers)}")
    print("=" * 68)
    print("\nLAYER 1 — the result\n")
    for line in report.summary_lines():
        print("  • " + line)
    print("\nLAYER 2 — show your work\n")
    for line in report.detail_lines():
        print("  " + line)
    print()


def main() -> None:
    tickers = [t.upper() for t in sys.argv[1:]] or DEFAULT_BASKET
    print(f"Fetching {YEARS}y of real prices for {tickers} ...")
    returns = fetch_log_returns(tickers)
    print(f"Got {len(returns)} aligned trading days.")
    report = analyse_diversification(returns)
    render(report)


if __name__ == "__main__":
    main()
