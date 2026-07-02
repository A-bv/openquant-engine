"""Portfolio lab — diversification / effective number of bets (/diversification)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.models import DiversificationRequest
from api.sanitize import _sanitize

router = APIRouter()


@router.post("/diversification")
def diversification(req: DiversificationRequest):
    """
    Turn the EPFL Risk & Return block into a concrete, real-data deliverable:
    "you hold N positions — in risk terms, X independent bets."

    Equal-weighted. Pure orchestration here; the maths lives in openquant.portfolio
    (pinned against EPFL Sample Exam 2 P4 in tests/test_portfolio.py).
    """
    import pandas as pd
    from openquant.data import DataFetcher, DataFetchError
    from openquant.common import log_returns
    from openquant.portfolio import analyse_diversification

    tickers = req.tickers  # already cleaned/validated/deduped
    fetcher = DataFetcher()

    price_map: dict[str, Any] = {}
    failed: list[str] = []
    for t in tickers:
        try:
            series = fetcher.price_fetcher.fetch(t, years=req.years)
            if series is not None and len(series) > 0:
                price_map[t] = series
            else:
                failed.append(t)
        except DataFetchError:
            failed.append(t)
        except Exception:
            failed.append(t)

    if len(price_map) < 2:
        raise HTTPException(status_code=400, detail={
            "error": "Need at least 2 tickers with valid price data.",
            "failed": failed,
        })

    prices = pd.DataFrame(price_map).dropna(how="any")
    if len(prices) < 60:
        raise HTTPException(status_code=422, detail={
            "error": "Not enough overlapping trading days for these tickers.",
            "overlapping_days": int(len(prices)),
        })

    returns = pd.DataFrame(
        {col: log_returns(prices[col]) for col in prices.columns}
    ).dropna()

    try:
        report = analyse_diversification(returns, risk_free_rate=req.risk_free_rate)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": str(e)})

    payload = report.to_dict()
    payload.update({
        "summary_lines": report.summary_lines(),
        "detail_lines": report.detail_lines(),
        "years": req.years,
        "trading_days": int(len(returns)),
        "failed_tickers": failed,
    })
    return _sanitize(payload)
