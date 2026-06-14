from loguru import logger

from agent_service.models import LogEvent


def normalize_node(state: dict) -> dict:
    logger.info("Normalize node invoked")
    raw_event = state.raw_event
    log_event = LogEvent(
        timestamp="1970-01-01T00:00:00Z",
        message=raw_event,
        level="error",
        namespace="unknown",
        pod_name="unknown",
        container="unknown",
        edge_site_id="unknown",
        kafka_offset=0,
        raw=raw_event,
    )
    return {"log_event": log_event}
