"""Request models for the OpenQuant API endpoints."""
from __future__ import annotations

import math
import re

from pydantic import BaseModel, Field, field_validator


class AnalyseRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10, pattern=r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")
    risk_free_rate: float = Field(default=0.045, ge=0.0, le=0.20)
    market_risk_premium: float = Field(default=0.055, ge=0.0, le=0.20)
    terminal_growth: float = Field(default=0.025, ge=-0.05, le=0.05)

    @field_validator("risk_free_rate", "market_risk_premium", "terminal_growth")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("must be a finite number")
        return v


_TICKER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-^]{0,9}$")


class DiversificationRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=15)
    years: int = Field(default=3, ge=1, le=10)
    risk_free_rate: float = Field(default=0.045, ge=0.0, le=0.20)

    @field_validator("tickers")
    @classmethod
    def _valid_tickers(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in v:
            t = raw.upper().strip()
            if not _TICKER_RE.match(t):
                raise ValueError(f"invalid ticker: {raw!r}")
            if t not in cleaned:
                cleaned.append(t)
        if len(cleaned) < 2:
            raise ValueError("need at least 2 distinct tickers")
        return cleaned


class NowOrLaterRequest(BaseModel):
    lump_sum: float = Field(ge=0)
    payment: float = Field(ge=0)
    n_payments: int = Field(ge=1, le=600)
    rate: float = Field(gt=-1.0, le=2.0)   # per-period discount rate
    growth: float = Field(default=0.0, ge=-0.5, le=1.0)
    first_payment_today: bool = True
    kind: str = Field(default="receive")
    currency: str = Field(default="$", max_length=3)

    @field_validator("kind")
    @classmethod
    def _valid_kind(cls, v: str) -> str:
        if v not in ("receive", "pay"):
            raise ValueError("kind must be 'receive' or 'pay'")
        return v

    @field_validator("lump_sum", "payment", "rate", "growth")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("must be a finite number")
        return v
