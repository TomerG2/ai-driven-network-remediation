from pydantic import BaseModel


class RootCauseAnalysis(BaseModel):
    root_cause: str
    confidence: float
    severity: str
    affected_components: list[str]
    recommended_playbook: str
    reasoning: str


class GraphConfig(BaseModel):
    remediate_threshold: float = 0.8
    escalate_threshold: float = 0.7


class RemediationState(BaseModel):
    raw_event: str
    context_snippets: list[str] = []
    root_cause_analysis: RootCauseAnalysis | None = None
    decision: str = ""
    execution_result: str = ""
    notifications_sent: list[str] = []
    awaiting_human_approval: bool = False
