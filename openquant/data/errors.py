"""
OpenQuant — data layer errors.

The failure modes of the data layer, pulled out of ``openquant/data/data.py`` so
they can be imported and tested on their own. Re-exported by ``openquant.data`` for
backward compatibility, so existing ``from openquant.data import DataFetchError``
imports keep working.
"""

from __future__ import annotations


class DataFetchError(Exception):
    """Raised when all data sources fail for a ticker."""
    pass


class InsufficientDataError(Exception):
    """Raised when data exists but is insufficient for analysis."""
    pass


class UnsupportedTickerError(Exception):
    """Raised when a ticker is not a supported US company."""
    pass


class DataInconsistencyWarning(UserWarning):
    """Raised when cross-validation detects source disagreement."""
    pass
