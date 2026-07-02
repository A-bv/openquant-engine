"""
OpenQuant — data layer cache.

A small file-based cache (JSON for financial data, CSV for price series) that
lets the data layer skip repeat fetches and work offline. Pulled out of
``openquant/data/data.py``; re-exported by ``openquant.data`` for backward compatibility.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import pandas as pd

from openquant.config import CACHE_DIR, CACHE_TTL_RECENT_SECONDS

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Simple file-based cache for fetched data.
    JSON for financial data, CSV for price series.
    """

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str, ext: str = "json") -> Path:
        """Convert cache key to file path."""
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{safe_key}.{ext}"

    def get(self, key: str, ttl_seconds: Optional[int] = CACHE_TTL_RECENT_SECONDS) -> Optional[dict]:
        """
        Retrieve cached value if it exists and is not expired.

        Args:
            key: Cache key string.
            ttl_seconds: TTL in seconds. None means permanent.

        Returns:
            Cached data dict or None if miss/expired.
        """
        path = self._key_to_path(key)
        if not path.exists():
            return None

        if ttl_seconds is not None:
            age = time.time() - path.stat().st_mtime
            if age > ttl_seconds:
                path.unlink(missing_ok=True)
                return None

        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            path.unlink(missing_ok=True)
            return None

    def set(self, key: str, data: dict) -> None:
        """Store data in cache atomically — write to a temp file in the same
        directory and os.replace into place so concurrent writers cannot
        observe a truncated file."""
        path = self._key_to_path(key)
        tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
        try:
            with open(tmp_path, "w") as f:
                json.dump(data, f, default=str)
            os.replace(tmp_path, path)
        except IOError as e:
            logger.warning(f"Cache write failed for key {key}: {e}")
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def get_prices(self, key: str, ttl_seconds: Optional[int] = CACHE_TTL_RECENT_SECONDS) -> Optional[pd.Series]:
        """Retrieve cached price series."""
        path = self._key_to_path(key, ext="csv")
        if not path.exists():
            return None

        age = time.time() - path.stat().st_mtime
        if ttl_seconds is not None and age > ttl_seconds:
            path.unlink(missing_ok=True)
            return None

        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            return df.iloc[:, 0]
        except Exception:
            path.unlink(missing_ok=True)
            return None

    def set_prices(self, key: str, prices: pd.Series) -> None:
        """Store price series in cache atomically."""
        path = self._key_to_path(key, ext="csv")
        tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
        try:
            prices.to_csv(tmp_path)
            os.replace(tmp_path, path)
        except IOError as e:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            logger.warning(f"Price cache write failed: {e}")
