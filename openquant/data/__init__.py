"""
OpenQuant data layer — clean, importable, offline-testable.

One package, one job: turn a ticker into the data the engine needs. It is split
so each piece can be imported and tested on its own:

- ``models``     — what the layer returns (FinancialStatements, PriceData, TickerValidation)
- ``errors``     — the failure modes (DataFetchError, ...)
- ``cache``      — the file-based cache (CacheManager)
- ``providers``  — one module per source (EDGARClient, PriceFetcher)
- ``data``       — the orchestrator (DataFetcher)
- ``fetcher``    — the functional interface (get_fundamentals / get_prices / ...)
- ``fixtures``   — offline sample data + a self-check (verify_financials)

Everything is re-exported here, so ``from openquant.data import X`` keeps working.
"""

from .data import *  # noqa: F401,F403  (re-exports models, errors, cache, providers, DataFetcher)
from .fetcher import (  # noqa: F401
    validate_ticker,
    get_fundamentals,
    get_prices,
    get_current_price,
)
from .fixtures import (  # noqa: F401
    sample_financials,
    sample_prices,
    verify_financials,
    REQUIRED_STATEMENT_FIELDS,
)
