import pytest
from pydantic import ValidationError

from agent_service.models import GraphConfig, IncidentState, LogEvent, RootCauseAnalysis


class TestRootCauseAnalysis:
    def test_valid_analysis(self):
        rca = RootCauseAnalysis(
            root_cause="nginx config missing",
            confidence=0.9,
            severity="high",
            affected_components=["nginx", "frontend"],
            recommended_playbook="restart-nginx",
            reasoning="Config file was deleted",
        )
        assert rca.confidence == 0.9
        assert rca.severity == "high"
        assert rca.affected_components == ["nginx", "frontend"]

    def test_confidence_must_be_float(self):
        with pytest.raises(ValidationError):
            RootCauseAnalysis(
                root_cause="test",
                confidence="not_a_number",
                severity="low",
                affected_components=[],
                recommended_playbook="test",
                reasoning="test",
            )

    def test_affected_components_must_be_list_of_strings(self):
        with pytest.raises(ValidationError):
            RootCauseAnalysis(
                root_cause="test",
                confidence=0.5,
                severity="low",
                affected_components="not_a_list",
                recommended_playbook="test",
                reasoning="test",
            )


class TestIncidentState:
    def test_valid_state(self):
        state = IncidentState(raw_event="pod crashloop")
        assert state.raw_event == "pod crashloop"
        assert state.context_snippets == []
        assert state.root_cause_analysis is None
        assert state.decision == ""
        assert state.execution_result == ""
        assert state.notifications_sent == []
        assert state.awaiting_human_approval is False

    def test_new_fields_have_defaults(self):
        state = IncidentState(raw_event="pod crashloop")
        assert state.log_event is None
        assert state.incident_id != ""
        assert state.incident_start_ms > 0
        assert state.confidence_override is None

    def test_state_with_log_event(self):
        event = LogEvent(
            timestamp="2024-01-01T00:00:00Z",
            message="crash",
            level="error",
            namespace="prod",
            pod_name="nginx-abc",
            container="nginx",
            edge_site_id="edge-01",
            kafka_offset=1,
            raw="raw",
        )
        state = IncidentState(raw_event="pod crashloop", log_event=event)
        assert state.log_event.message == "crash"

    def test_state_with_root_cause_analysis(self):
        rca = RootCauseAnalysis(
            root_cause="OOM",
            confidence=0.95,
            severity="critical",
            affected_components=["nginx"],
            recommended_playbook="restart-nginx",
            reasoning="Memory limit exceeded",
        )
        state = IncidentState(raw_event="pod crashloop", root_cause_analysis=rca)
        assert state.root_cause_analysis.confidence == 0.95


class TestLogEvent:
    def test_valid_log_event(self):
        event = LogEvent(
            timestamp="2024-01-01T00:00:00Z",
            message="pod crash detected",
            level="error",
            namespace="prod",
            pod_name="nginx-abc123",
            container="nginx",
            edge_site_id="edge-01",
            kafka_offset=42,
            raw='{"msg": "pod crash detected"}',
        )
        assert event.message == "pod crash detected"
        assert event.kafka_offset == 42

    def test_kafka_offset_must_be_int(self):
        with pytest.raises(ValidationError):
            LogEvent(
                timestamp="2024-01-01T00:00:00Z",
                message="test",
                level="info",
                namespace="default",
                pod_name="test",
                container="test",
                edge_site_id="edge-01",
                kafka_offset="not_an_int",
                raw="raw",
            )


class TestGraphConfig:
    def test_defaults(self):
        config = GraphConfig()
        assert config.remediate_threshold == 0.8
        assert config.escalate_threshold == 0.7

    def test_custom_thresholds(self):
        config = GraphConfig(remediate_threshold=0.9, escalate_threshold=0.6)
        assert config.remediate_threshold == 0.9
        assert config.escalate_threshold == 0.6
