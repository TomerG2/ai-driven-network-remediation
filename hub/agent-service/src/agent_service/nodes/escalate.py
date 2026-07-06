from loguru import logger

from agent_service.utils import invoke_tool as _invoke_tool

_PRIORITY_MAP = {"critical": 1, "high": 2, "medium": 3, "low": 4}


async def escalate_node(state) -> dict:
    log_event = state.log_event
    rca = state.root_cause_analysis

    short_description = (
        f"[AI-NOC] {rca.failure_type} – {log_event.pod_name}"
        f" in {log_event.namespace} ({log_event.edge_site_id})"
    )

    description = (
        f"Failure Type: {rca.failure_type}\n"
        f"Confidence: {rca.confidence}\n"
        f"Severity: {rca.estimated_severity}\n"
        f"Edge Site: {log_event.edge_site_id}\n"
        f"Namespace: {log_event.namespace}\n"
        f"Pod: {log_event.pod_name}\n"
        f"Container: {log_event.container}\n"
        f"\n--- Root Cause Analysis ---\n"
        f"Summary: {rca.summary}\n"
        f"Evidence:\n"
    )
    for item in rca.evidence:
        description += f"  - {item}\n"
    description += "Recommended Actions:\n"
    for action in rca.recommended_actions:
        description += f"  - {action}\n"
    description += f"\n--- Original Log Message ---\n{log_event.message}\n"

    priority = _PRIORITY_MAP.get(rca.estimated_severity, 4)

    logger.info(f"Creating ServiceNow incident: {short_description}")
    try:
        response = await _invoke_tool("create_incident", {
            "short_description": short_description,
            "description": description,
            "priority": priority,
        })
    except Exception as exc:
        reason = str(exc)
        logger.warning(f"ServiceNow escalation failed: {reason}")
        return {"servicenow_ticket": "", "error_message": reason}

    if not response.get("success", True):
        reason = response.get("error", "unknown error")
        logger.warning(f"ServiceNow escalation failed: {reason}")
        return {"servicenow_ticket": "", "error_message": reason}

    ticket = response.get("number", "")
    logger.info(f"ServiceNow ticket created: {ticket}")
    return {"servicenow_ticket": ticket}
