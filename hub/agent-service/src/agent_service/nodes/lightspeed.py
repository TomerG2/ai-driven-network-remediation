from loguru import logger

from agent_service.models import RemediationResult


def lightspeed_node(state: dict) -> dict:
    logger.info("Lightspeed node invoked")
    result = RemediationResult(
        action_taken="generate-playbook",
        tool_used="lightspeed",
        success=True,
        job_id="placeholder-lightspeed-job-id",
        duration_seconds=0.0,
        output_summary="placeholder-lightspeed-result",
        timestamp="1970-01-01T00:00:00Z",
        generated_template_name="placeholder-template",
        generated_template_id="placeholder-template-id",
        generated_playbook_name="placeholder-playbook",
        generated_playbook_preview="- hosts: all\n  tasks:\n    - name: placeholder",
    )
    return {"decision": "lightspeed", "remediation_result": result}
