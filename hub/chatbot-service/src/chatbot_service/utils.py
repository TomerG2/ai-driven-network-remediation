"""Shared utility functions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def normalize_session_id(session_id: str | None) -> str:
    return session_id.strip() if session_id and session_id.strip() else str(uuid4())


def get_mcp_items(integrations_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract MCP-group integrations from the integrations payload."""
    return [i for i in integrations_data.get("integrations", []) if i.get("group") == "mcp"]


def build_deps(checks: dict[str, bool]) -> dict[str, Any]:
    """Build the _deps envelope from named dependency checks.

    checks: {"kafka": True, "servicenow": False, "llm": True}
    returns: {"status": "ok"} or {"status": "degraded", "unavailable": ["servicenow"]}
    """
    unavailable = [name for name, ok in checks.items() if not ok]
    if not unavailable:
        return {"status": "ok"}
    return {"status": "degraded", "unavailable": sorted(unavailable)}
