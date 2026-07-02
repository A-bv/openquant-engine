"""OpenQuant API package."""
import os
import sys

# Make the repo root importable so `core` resolves no matter how the app is
# launched (uvicorn from repo root, pytest, etc.).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
