"""HTTP health probes for MCP servers and ServiceNow."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import (
    SERVICENOW_API_KEY,
    SERVICENOW_MODE,
    SERVICENOW_PASSWORD,
    SERVICENOW_URL,
    SERVICENOW_USERNAME,
    SSL_VERIFY,
)

logger = logging.getLogger(__name__)


def is_real_servicenow() -> bool:
    return SERVICENOW_MODE == "real" or bool(SERVICENOW_USERNAME and SERVICENOW_PASSWORD)


async def probe_http(url: str, timeout: float = 4.0) -> dict[str, Any]:
    """Probe a service endpoint. Treats 200/401/403/404/405 as reachable."""
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=SSL_VERIFY) as client:
            resp = await client.get(url)
            reachable = resp.status_code in {200, 401, 403, 404, 405}
            return {
                "status": "up" if reachable else f"http-{resp.status_code}",
                "http_code": resp.status_code,
                "reachable": reachable,
            }
    except Exception:
        logger.debug("Probe failed for %s", url, exc_info=True)
        return {"status": "down", "http_code": None, "reachable": False}


async def fetch_servicenow_incident_count() -> tuple[int, str]:
    """Get open incident count from ServiceNow (real or mock).

    NOTE: Direct HTTP for now (single query). Consider a ServiceNow SDK or
    dedicated client wrapper if we expand to creating/updating tickets or CMDB queries.
    """
    try:
        async with httpx.AsyncClient(timeout=8.0, verify=SSL_VERIFY) as client:
            if is_real_servicenow():
                logger.debug("Querying real ServiceNow at %s", SERVICENOW_URL)
                resp = await client.get(
                    f"{SERVICENOW_URL}/api/now/table/incident?sysparm_limit=100&sysparm_fields=number",
                    auth=(SERVICENOW_USERNAME, SERVICENOW_PASSWORD),
                )
                if resp.status_code == 200:
                    return len(resp.json().get("result", [])), "up"
                logger.warning("ServiceNow returned HTTP %d", resp.status_code)
                return 0, f"http-{resp.status_code}"

            resp = await client.get(
                f"{SERVICENOW_URL}/api/now/table/incident",
                headers={"X-API-Key": SERVICENOW_API_KEY} if SERVICENOW_API_KEY else {},
            )
            if resp.status_code == 200:
                data = resp.json()
                return int(data.get("count", 0)), "up"
            return 0, f"http-{resp.status_code}"
    except Exception:
        logger.warning("ServiceNow unreachable at %s", SERVICENOW_URL, exc_info=True)
        return 0, "down"
