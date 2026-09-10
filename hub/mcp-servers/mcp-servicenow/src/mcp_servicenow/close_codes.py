"""Shared ServiceNow incident close_code fallbacks."""

import json
from functools import lru_cache
from importlib import resources


@lru_cache
def load_close_code_fallbacks() -> list[str]:
    """Return ordered close_code values to try when resolving incidents."""
    payload = resources.files("mcp_servicenow").joinpath("close_codes.json").read_text(encoding="utf-8")
    data = json.loads(payload)
    return list(data["close_code_fallbacks"])
