"""Shared ServiceNow incident close_code fallbacks."""

import json
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CONTRACTS_FILE = _REPO_ROOT / "contracts" / "servicenow-close-codes.json"


@lru_cache
def load_close_code_fallbacks() -> list[str]:
    """Return ordered close_code values to try when resolving incidents."""
    with open(_CONTRACTS_FILE, encoding="utf-8") as handle:
        data = json.load(handle)
    return list(data["close_code_fallbacks"])
