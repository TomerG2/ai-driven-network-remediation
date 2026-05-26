"""Kafka MCP server configuration."""

import os
from typing import Literal

from mcp.server.fastmcp import FastMCP

MCP_TRANSPORT: Literal["stdio", "sse", "streamable-http"] = os.environ.get(
    "MCP_TRANSPORT", "sse"
)  # type: ignore[assignment]
MCP_PORT = int(os.environ.get("MCP_PORT", "8003"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "dark-noc-kafka-kafka-bootstrap.dark-noc-kafka.svc:9092")

mcp = FastMCP(
    "noc-kafka",
    instructions=(
        "Kafka streaming tools for the NOC remediation agent. "
        "Use consume_topic to read recent messages for analysis. "
        "Use produce_message to send remediation events or audit records. "
        "Use get_consumer_lag to check if the agent is keeping up with log volume."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=(MCP_TRANSPORT == "streamable-http"),
)
