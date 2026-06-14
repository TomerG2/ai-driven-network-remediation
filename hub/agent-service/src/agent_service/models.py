import time
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

FailureType = Literal[
    "OOMKilled",
    "CrashLoopBackOff",
    "ConfigError",
    "NetworkTimeout",
    "StorageFull",
    "CertificateExpired",
    "DNSFailure",
    "KafkaLag",
    "PostgresConnPool",
    "AAPJobFailure",
    "Unknown",
]


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
    failure_type: FailureType
    confidence: float
    summary: str
    evidence: list[str]
    recommended_actions: list[str]
    estimated_severity: Literal["critical", "high", "medium", "low"]
    runbook_reference: str


class RemediationResult(BaseModel):
    action_taken: str
    tool_used: str
    success: bool
    job_id: str
    duration_seconds: float
    output_summary: str
    timestamp: str
    generated_template_name: Optional[str] = None
    generated_template_id: Optional[str] = None
    generated_playbook_name: Optional[str] = None
    generated_playbook_preview: Optional[str] = None


class GraphConfig(BaseModel):
    remediate_threshold: float = 0.8
    escalate_threshold: float = 0.7


class IncidentState(BaseModel):
    raw_event: str
    log_event: Optional[LogEvent] = None
    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_start_ms: float = Field(default_factory=lambda: time.time() * 1000)
    confidence_override: Optional[float] = None
    failure_type_override: Optional[FailureType] = None
    context_snippets: list[str] = []
    rag_query_used: str = ""
    root_cause_analysis: Optional[RootCauseAnalysis] = None
    analysis_tokens_used: int = 0
    analysis_latency_ms: float = 0.0
    decision: str = ""
    remediation_result: Optional[RemediationResult] = None
