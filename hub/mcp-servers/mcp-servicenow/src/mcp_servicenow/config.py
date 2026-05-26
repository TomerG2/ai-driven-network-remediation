"""ServiceNow MCP server configuration."""

import os
from typing import Literal

from mcp.server.fastmcp import FastMCP

MCP_TRANSPORT: Literal["stdio", "sse", "streamable-http"] = os.environ.get(
    "MCP_TRANSPORT", "sse"
)  # type: ignore[assignment]
MCP_PORT = int(os.environ.get("MCP_PORT", "8006"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")

SNOW_URL = os.getenv("SERVICENOW_URL", "http://servicenow-mock.dark-noc-servicenow-mock.svc:8080").rstrip("/")
SNOW_API_KEY = os.environ["SERVICENOW_API_KEY"]
SNOW_USERNAME = os.getenv("SERVICENOW_USERNAME", "")
SNOW_PASSWORD = os.getenv("SERVICENOW_PASSWORD", "")
SNOW_MODE = os.getenv("SERVICENOW_MODE", "auto").lower()
SNOW_CALLER_NAME = os.getenv("SERVICENOW_CALLER_NAME", "NOC Agent")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_NOC_CHANNEL = os.getenv("SLACK_NOC_CHANNEL", "#dark-noc-alerts")
SLACK_BASE_URL = "https://slack.com/api"

mcp = FastMCP(
    "noc-servicenow",
    instructions=(
        "ServiceNow incident management tools. "
        "Create incidents for issues that cannot be auto-remediated. "
        "Priority guide: 1=Critical(site down), 2=High(degraded), 3=Medium(warning), 4=Low(informational). "
        "Always resolve the incident once the issue is fixed."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=(MCP_TRANSPORT == "streamable-http"),
)
