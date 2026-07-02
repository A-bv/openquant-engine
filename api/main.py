"""
OpenQuant — FastAPI backend.

Thin app: CORS, health, and the per-lab routers. All computation lives in
openquant/; every endpoint lives in api/routers/ (money · portfolio · stock).
The repo-root sys.path bootstrap lives in api/__init__.py.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import money, portfolio, stock

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(title="OpenQuant API", version="1.0.0")

# CORS — explicit local dev origins plus an anchored regex for this project's
# Vercel deployments (override via ALLOWED_ORIGIN_REGEX for other hosts).
_ALLOWED_ORIGIN_REGEX = os.getenv(
    "ALLOWED_ORIGIN_REGEX",
    # This project's static hosts only: its Vercel deployments and its own
    # GitHub Pages site — not all of github.io. Override for other hosts.
    r"^https://(openquant(-[a-z0-9-]+)?\.vercel\.app|a-bv\.github\.io)$",
)
# No cookies or auth anywhere in this API, so credentials stay disabled —
# credentialed CORS with pattern-matched origins is a foot-gun with no upside.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=_ALLOWED_ORIGIN_REGEX,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


app.include_router(money.router)
app.include_router(portfolio.router)
app.include_router(stock.router)


# Facade: re-export the public surface that tests and callers import from
# `api.main` (endpoints/helpers now live in api/routers, schemas in api/models,
# the JSON helper in api/sanitize).
from api.models import (  # noqa: E402,F401
    AnalyseRequest,
    DiversificationRequest,
    NowOrLaterRequest,
)
from api.sanitize import _sanitize  # noqa: E402,F401
from api.routers.stock import (  # noqa: E402,F401
    analyse,
    calibration,
    _diagnostic_payload,
    _red_flags_payload,
    _audit_payload,
)
