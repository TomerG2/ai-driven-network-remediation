"""Slack MCP server configuration."""

import os
from typing import Literal

from mcp.server.fastmcp import FastMCP

MCP_TRANSPORT: Literal["stdio", "sse", "streamable-http"] = os.environ.get(
    "MCP_TRANSPORT", "sse"
)  # type: ignore[assignment]
MCP_PORT = int(os.environ.get("MCP_PORT", "8005"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_NOC_CHANNEL = os.getenv("SLACK_NOC_CHANNEL", "#dark-noc-alerts")
SLACK_BASE_URL = os.getenv("SLACK_BASE_URL", "https://slack.com/api")

mcp = FastMCP(
    "noc-slack",
    instructions=(
        "Slack notification tools for the NOC remediation agent. "
        "Always use send_alert for incidents with severity. "
        "Use send_remediation after a fix is applied. "
        "Keep messages concise — engineers read them on mobile."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=(MCP_TRANSPORT == "streamable-http"),
)
