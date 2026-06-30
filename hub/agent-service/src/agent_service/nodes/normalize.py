import json

from loguru import logger

from agent_service.models import LogEvent


def normalize_node(state: dict) -> dict:
    logger.info("Normalize node invoked")
    raw_event = state.raw_event
    kafka_offset = getattr(state, "kafka_offset", 0) or 0

    try:
        data = json.loads(raw_event)
    except (json.JSONDecodeError, TypeError):
        data = None

    if isinstance(data, dict) and "kubernetes" in data:
        k8s = data.get("kubernetes", {})
        labels = data.get("labels", {})
        log_event = LogEvent(
            timestamp=data.get("@timestamp", "unknown"),
            message=data.get("message", "unknown"),
            level=data.get("level", "unknown"),
            namespace=k8s.get("namespace_name", "unknown"),
            pod_name=k8s.get("pod_name", "unknown"),
            container=k8s.get("container_name", "unknown"),
            edge_site_id=labels.get("edge_site_id", "unknown"),
            kafka_offset=kafka_offset,
            raw=raw_event,
        )
    else:
        log_event = LogEvent(
            timestamp="1970-01-01T00:00:00Z",
            message=raw_event,
            level="error",
            namespace="unknown",
            pod_name="unknown",
            container="unknown",
            edge_site_id="unknown",
            kafka_offset=kafka_offset,
            raw=raw_event,
        )

    return {"log_event": log_event}
