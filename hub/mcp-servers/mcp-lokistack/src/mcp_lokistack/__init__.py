"""
LokiStack MCP Server
======================
MCP server for querying LokiStack via the LogQL API.
Gives the AI remediation agent access to historical log data.

Tools:
    query_logs        - Run a LogQL query against LokiStack
    get_recent_errors - Get recent error logs from a namespace/app
    count_errors      - Count error occurrences in a time window

Transport: Configurable via MCP_TRANSPORT env var (default: sse)
"""

import os
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

MCP_TRANSPORT: Literal["stdio", "sse", "streamable-http"] = os.environ.get(
    "MCP_TRANSPORT", "sse"
)  # type: ignore[assignment]
MCP_PORT = int(os.environ.get("MCP_PORT", "8002"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")

mcp = FastMCP(
    "noc-lokistack",
    instructions=(
        "LokiStack log query tools using LogQL. "
        "Use get_recent_errors for quick error lookups. "
        "Use query_logs for complex LogQL queries. "
        "Time range: use relative durations like '1h', '30m', '7d'."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=(MCP_TRANSPORT == "streamable-http"),
)

LOKI_URL = os.getenv("LOKI_URL", "http://logging-loki-gateway.openshift-logging.svc:8080")
LOKI_TOKEN = os.getenv("LOKI_TOKEN", "")
DEFAULT_NAMESPACE = os.getenv("DEFAULT_NAMESPACE", "dark-noc-edge")

_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


@mcp.custom_route("/health", methods=["GET"])  # type: ignore
async def health(request: Any) -> JSONResponse:
    """Health check endpoint for Kubernetes probes."""
    return JSONResponse({"status": "OK"})


def _loki_client() -> httpx.Client:
    """Create httpx client for LokiStack API."""
    headers = {}
    if LOKI_TOKEN:
        headers["Authorization"] = f"Bearer {LOKI_TOKEN}"
    return httpx.Client(base_url=f"{LOKI_URL}/loki/api/v1", headers=headers, timeout=30)


def _parse_duration_ns(duration: str) -> int:
    """Convert duration string (e.g. '1h', '30m') to nanoseconds."""
    unit = duration[-1]
    value = int(duration[:-1])
    return value * _DURATION_UNITS.get(unit, 3600) * 1_000_000_000


@mcp.tool()
def query_logs(
    logql_query: str,
    duration: str = "1h",
    limit: int = 100,
) -> dict:
    """
    Run a LogQL query against LokiStack and return matching log lines.

    Args:
        logql_query: LogQL query string, e.g.:
                     '{namespace="dark-noc-edge", app="nginx"} |= "error"'
        duration:    Time range to search (e.g., "1h", "30m", "6h", "1d")
        limit:       Maximum log lines to return (default: 100)

    Returns:
        Dict with log lines list: [{timestamp, line, labels}]
    """
    try:
        end_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        start_ns = end_ns - _parse_duration_ns(duration)

        with _loki_client() as client:
            resp = client.get(
                "/query_range",
                params={
                    "query": logql_query,
                    "start": start_ns,
                    "end": end_ns,
                    "limit": limit,
                    "direction": "backward",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("data", {}).get("result", [])
        log_lines = []
        for stream in results:
            labels = stream.get("stream", {})
            for ts_val, line in stream.get("values", []):
                log_lines.append(
                    {
                        "timestamp": datetime.fromtimestamp(int(ts_val) / 1_000_000_000, tz=timezone.utc).isoformat(),
                        "line": line,
                        "labels": labels,
                    }
                )

        log_lines.sort(key=lambda x: x["timestamp"], reverse=True)

        return {
            "query": logql_query,
            "duration": duration,
            "count": len(log_lines),
            "logs": log_lines[:limit],
        }
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"LokiStack API error: {e.response.status_code} – {e.response.text[:200]}"}
    except httpx.HTTPError as e:
        return {"success": False, "error": f"LokiStack connection error: {e}"}


@mcp.tool()
def get_recent_errors(
    namespace: str = DEFAULT_NAMESPACE,
    app: str = "nginx",
    duration: str = "30m",
    limit: int = 50,
) -> dict:
    """
    Get recent error logs from a specific application.
    Convenience wrapper for the most common NOC query pattern.

    Args:
        namespace: Kubernetes namespace (default: dark-noc-edge)
        app:       Application label (default: nginx)
        duration:  Look-back window (default: 30m)
        limit:     Max lines (default: 50)

    Returns:
        Dict with error log lines
    """
    logql = f'{{namespace="{namespace}", app="{app}"}} |= "error" or |= "ERROR" or |= "warn" or |= "WARN"'
    return query_logs(logql, duration, limit)


@mcp.tool()
def count_errors(
    namespace: str = DEFAULT_NAMESPACE,
    app: str = "nginx",
    duration: str = "1h",
) -> dict:
    """
    Count error occurrences in a time window (for trend analysis).

    Args:
        namespace: Kubernetes namespace
        app:       Application label
        duration:  Time window (e.g., "1h", "24h")

    Returns:
        Dict with error counts per 5-minute buckets and total
    """
    try:
        end_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        start_ns = end_ns - _parse_duration_ns(duration)

        metric_query = f'sum(count_over_time({{namespace="{namespace}", app="{app}"}} |= "error" [5m]))'

        with _loki_client() as client:
            resp = client.get(
                "/query_range",
                params={
                    "query": metric_query,
                    "start": start_ns,
                    "end": end_ns,
                    "step": "300",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("data", {}).get("result", [])
        buckets = []
        for series in results:
            for ts_val, count in series.get("values", []):
                buckets.append(
                    {
                        "time": datetime.fromtimestamp(int(ts_val), tz=timezone.utc).isoformat(),
                        "error_count": int(float(count)),
                    }
                )

        total = sum(b["error_count"] for b in buckets)
        return {
            "namespace": namespace,
            "app": app,
            "duration": duration,
            "total_errors": total,
            "buckets": buckets,
            "avg_errors_per_5min": total / max(len(buckets), 1),
        }
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"LokiStack API error: {e.response.status_code} – {e.response.text[:200]}"}
    except httpx.HTTPError as e:
        return {"success": False, "error": f"LokiStack connection error: {e}"}


def main() -> None:
    """Run the LokiStack MCP server."""
    mcp.run(transport=MCP_TRANSPORT)


app = mcp.streamable_http_app()
