"""Money lab — everyday time-value-of-money decision (/now-or-later)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.models import NowOrLaterRequest
from api.sanitize import _sanitize

router = APIRouter()


@router.post("/now-or-later")
def now_or_later(req: NowOrLaterRequest):
    """
    The everyday-money front door: "take the money now, or spread over time?"

    No market data, cannot fail on a ticker. Pure orchestration; the maths
    lives in openquant.money (pinned against the PFEM lottery in tests/test_money.py).
    """
    from openquant.money import compare_now_vs_later

    try:
        result = compare_now_vs_later(
            lump_sum=req.lump_sum,
            payment=req.payment,
            n_payments=req.n_payments,
            rate=req.rate,
            growth=req.growth,
            first_payment_today=req.first_payment_today,
            kind=req.kind,
            currency=req.currency,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": str(e)})

    payload = result.to_dict()
    payload.update({
        "summary_lines": result.summary_lines(),
        "detail_lines": result.detail_lines(),
    })
    return _sanitize(payload)
