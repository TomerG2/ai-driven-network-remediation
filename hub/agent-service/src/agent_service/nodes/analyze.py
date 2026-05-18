from loguru import logger

from agent_service.models import RootCauseAnalysis


def analyze_node(state: dict) -> dict:
    logger.info("Analyze node invoked")
    rca = RootCauseAnalysis(
        root_cause="placeholder root cause",
        confidence=0.85,
        severity="medium",
        affected_components=["placeholder-component"],
        recommended_playbook="placeholder-playbook",
        reasoning="placeholder reasoning",
    )
    return {"root_cause_analysis": rca}
