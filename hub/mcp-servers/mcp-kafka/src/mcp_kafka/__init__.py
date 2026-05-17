"""
Kafka MCP Server
=================
MCP server for Kafka operations.
Allows the AI remediation agent to read from topics and produce messages.

Tools:
    consume_topic   - Read recent messages from a topic
    produce_message - Write a message to a topic
    get_consumer_lag - Check consumer group lag
    list_topics     - List all available topics

Transport: Configurable via MCP_TRANSPORT env var (default: sse)
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

from kafka import KafkaConsumer, KafkaProducer
from kafka.structs import TopicPartition
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

MCP_TRANSPORT: Literal["stdio", "sse", "streamable-http"] = os.environ.get(
    "MCP_TRANSPORT", "sse"
)  # type: ignore[assignment]
MCP_PORT = int(os.environ.get("MCP_PORT", "8003"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")

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

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "dark-noc-kafka-kafka-bootstrap.dark-noc-kafka.svc:9092")


@mcp.custom_route("/health", methods=["GET"])  # type: ignore
async def health(request: Any) -> JSONResponse:
    """Health check endpoint for Kubernetes probes."""
    return JSONResponse({"status": "OK"})


@mcp.tool()
def consume_topic(
    topic: str,
    max_messages: int = 20,
    timeout_ms: int = 5000,
) -> dict:
    """
    Read recent messages from a Kafka topic.

    Args:
        topic:        Kafka topic name (e.g., "nginx-logs", "noc-alerts")
        max_messages: Maximum number of messages to return (default: 20)
        timeout_ms:   Consumer poll timeout in ms (default: 5000)

    Returns:
        Dict with messages list: [{partition, offset, timestamp, value}]
    """
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        consumer_timeout_ms=timeout_ms,
        value_deserializer=lambda m: m.decode("utf-8", errors="replace"),
    )

    messages = []
    try:
        consumer.poll(timeout_ms=1000)
        partitions = consumer.assignment()

        for tp in partitions:
            end_offset = consumer.end_offsets([tp])[tp]
            start_offset = max(0, end_offset - max_messages)
            consumer.seek(tp, start_offset)

        for msg in consumer:
            try:
                value = json.loads(msg.value)
            except json.JSONDecodeError:
                value = msg.value

            messages.append(
                {
                    "partition": msg.partition,
                    "offset": msg.offset,
                    "timestamp": datetime.fromtimestamp(msg.timestamp / 1000, tz=timezone.utc).isoformat(),
                    "value": value,
                }
            )

            if len(messages) >= max_messages:
                break
    finally:
        consumer.close()

    return {"topic": topic, "messages": messages, "count": len(messages)}


@mcp.tool()
def produce_message(
    topic: str,
    message: dict,
    key: str = "",
) -> dict:
    """
    Produce a message to a Kafka topic.

    Args:
        topic:   Target topic (e.g., "noc-alerts", "remediation-jobs", "incident-audit")
        message: Dict to serialize as JSON and send
        key:     Optional message key (for partitioning)

    Returns:
        Dict with delivery confirmation
    """
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",
    )

    try:
        future = producer.send(topic, value=message, key=key if key else None)
        record_metadata = future.get(timeout=10)
        producer.flush()
    finally:
        producer.close()

    return {
        "success": True,
        "topic": record_metadata.topic,
        "partition": record_metadata.partition,
        "offset": record_metadata.offset,
    }


@mcp.tool()
def get_consumer_lag(
    group_id: str = "dark-noc-agent",
    topic: str = "nginx-logs",
) -> dict:
    """
    Get the current consumer lag for a consumer group.
    High lag means the agent is falling behind on processing logs.

    Args:
        group_id: Consumer group ID (default: dark-noc-agent)
        topic:    Topic to check lag for (default: nginx-logs)

    Returns:
        Dict with lag per partition and total lag
    """
    consumer = KafkaConsumer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=group_id,
        enable_auto_commit=False,
    )

    try:
        tp_list = [TopicPartition(topic, p) for p in consumer.partitions_for_topic(topic) or [0]]

        end_offsets = consumer.end_offsets(tp_list)
        committed = {tp: consumer.committed(tp) for tp in tp_list}

        partitions = []
        total_lag = 0
        for tp in tp_list:
            end = end_offsets[tp]
            committed_offset = committed[tp] or 0
            lag = max(0, end - committed_offset)
            total_lag += lag
            partitions.append(
                {
                    "partition": tp.partition,
                    "end_offset": end,
                    "committed_offset": committed_offset,
                    "lag": lag,
                }
            )
    finally:
        consumer.close()

    return {
        "group_id": group_id,
        "topic": topic,
        "total_lag": total_lag,
        "partitions": partitions,
        "status": "healthy" if total_lag < 100 else "behind",
    }


@mcp.tool()
def list_topics() -> dict:
    """
    List all available Kafka topics.

    Returns:
        Dict with topics list: [{name, partitions}]
    """
    consumer = KafkaConsumer(bootstrap_servers=KAFKA_BOOTSTRAP)
    try:
        topics = list(consumer.topics())
        result = []
        for topic in sorted(topics):
            if topic.startswith("_"):
                continue
            partitions = consumer.partitions_for_topic(topic) or set()
            result.append({"name": topic, "partitions": len(partitions)})
    finally:
        consumer.close()

    return {"topics": result, "count": len(result)}


def main() -> None:
    """Run the Kafka MCP server."""
    mcp.run(transport=MCP_TRANSPORT)


app = mcp.streamable_http_app()
