"""Shared response helpers for the OpenQuant API."""
from __future__ import annotations

import math
from typing import Any


def _sanitize(obj: Any) -> Any:
    """Recursively replace NaN/Inf floats with None so the response is valid JSON."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj
