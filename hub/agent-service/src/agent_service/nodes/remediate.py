from loguru import logger

from agent_service.models import RemediationResult


def remediate_node(state: dict) -> dict:
    logger.info("Remediate node invoked")
    result = RemediationResult(
        action_taken="placeholder-action",
        tool_used="placeholder-tool",
        success=True,
        job_id="placeholder-job-id",
        duration_seconds=0.0,
        output_summary="placeholder-remediation-result",
        timestamp="1970-01-01T00:00:00Z",
    )
    return {"decision": "remediate", "remediation_result": result}
