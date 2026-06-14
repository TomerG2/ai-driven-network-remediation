from loguru import logger

from agent_service.models import RootCauseAnalysis


def analyze_node(state: dict) -> dict:
    logger.info("Analyze node invoked")
    confidence = state.confidence_override if state.confidence_override is not None else 0.85
    rca = RootCauseAnalysis(
        failure_type="CrashLoopBackOff",
        confidence=confidence,
        summary="placeholder summary",
        evidence=["placeholder evidence"],
        recommended_actions=["placeholder action"],
        estimated_severity="medium",
        runbook_reference="placeholder-runbook",
    )
    return {"root_cause_analysis": rca}
