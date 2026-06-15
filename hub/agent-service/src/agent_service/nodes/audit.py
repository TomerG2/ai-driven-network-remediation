from loguru import logger


def audit_node(state: dict) -> dict:
    logger.info(
        "Audit record",
        incident_id=state.incident_id,
        decision=state.decision,
    )
    return {}
