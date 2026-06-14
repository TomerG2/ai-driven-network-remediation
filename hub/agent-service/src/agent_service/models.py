import time
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class LogEvent(BaseModel):
    timestamp: str
    message: str
    level: str
    namespace: str
    pod_name: str
    container: str
    edge_site_id: str
    kafka_offset: int
    raw: str


class RootCauseAnalysis(BaseModel):
    root_cause: str
    confidence: float
    severity: Severity
    affected_components: list[str]
    recommended_playbook: str
    reasoning: str


class GraphConfig(BaseModel):
    remediate_threshold: float = 0.8
    escalate_threshold: float = 0.7


class IncidentState(BaseModel):
    raw_event: str
    log_event: Optional[LogEvent] = None
    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_start_ms: float = Field(default_factory=lambda: time.time() * 1000)
    confidence_override: Optional[float] = None
    context_snippets: list[str] = []
    root_cause_analysis: Optional[RootCauseAnalysis] = None
    decision: str = ""
    execution_result: str = ""
    notifications_sent: list[str] = []
    awaiting_human_approval: bool = False
