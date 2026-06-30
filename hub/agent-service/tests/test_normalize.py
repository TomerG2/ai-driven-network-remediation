import json
from unittest.mock import patch

from agent_service.models import IncidentState
from agent_service.nodes.normalize import normalize_node

CANONICAL_EVENT = {
    "@timestamp": "2024-01-15T10:30:00Z",
    "message": "nginx CrashLoopBackOff in namespace prod",
    "level": "error",
    "kubernetes": {
        "namespace_name": "prod",
        "pod_name": "nginx-abc123",
        "container_name": "nginx",
    },
    "labels": {
        "edge_site_id": "edge-site-01",
    },
}


class TestCanonicalJsonParsing:
    def test_extracts_all_fields_from_canonical_json(self):
        raw = json.dumps(CANONICAL_EVENT)
        state = IncidentState(raw_event=raw)
        result = normalize_node(state)
        log_event = result["log_event"]

        assert log_event.timestamp == "2024-01-15T10:30:00Z"
        assert log_event.message == "nginx CrashLoopBackOff in namespace prod"
        assert log_event.level == "error"
        assert log_event.namespace == "prod"
        assert log_event.pod_name == "nginx-abc123"
        assert log_event.container == "nginx"
        assert log_event.edge_site_id == "edge-site-01"
        assert log_event.raw == raw

    def test_missing_labels_defaults_edge_site_id_to_unknown(self):
        event = {
            "@timestamp": "2024-01-15T10:30:00Z",
            "message": "some error",
            "level": "error",
            "kubernetes": {
                "namespace_name": "prod",
                "pod_name": "nginx-abc123",
                "container_name": "nginx",
            },
        }
        raw = json.dumps(event)
        state = IncidentState(raw_event=raw)
        result = normalize_node(state)
        log_event = result["log_event"]

        assert log_event.edge_site_id == "unknown"
        assert log_event.namespace == "prod"
        assert log_event.pod_name == "nginx-abc123"

    def test_missing_kubernetes_fields_default_to_unknown(self):
        event = {
            "@timestamp": "2024-01-15T10:30:00Z",
            "message": "some error",
            "level": "warn",
            "kubernetes": {},
            "labels": {"edge_site_id": "edge-02"},
        }
        raw = json.dumps(event)
        state = IncidentState(raw_event=raw)
        result = normalize_node(state)
        log_event = result["log_event"]

        assert log_event.namespace == "unknown"
        assert log_event.pod_name == "unknown"
        assert log_event.container == "unknown"
        assert log_event.edge_site_id == "edge-02"
        assert log_event.level == "warn"


class TestKafkaOffsetPassthrough:
    def test_nonzero_kafka_offset_passes_through_to_log_event(self):
        raw = json.dumps(CANONICAL_EVENT)
        state = IncidentState(raw_event=raw, kafka_offset=99)
        result = normalize_node(state)
        log_event = result["log_event"]

        assert log_event.kafka_offset == 99


class TestNonJsonFallback:
    def test_plain_text_uses_fallback(self):
        raw = "nginx CrashLoopBackOff in namespace prod"
        state = IncidentState(raw_event=raw)
        result = normalize_node(state)
        log_event = result["log_event"]

        assert log_event.message == raw
        assert log_event.raw == raw
        assert log_event.namespace == "unknown"
        assert log_event.pod_name == "unknown"
        assert log_event.container == "unknown"
        assert log_event.edge_site_id == "unknown"
        assert log_event.level == "unknown"
        assert log_event.timestamp == "unknown"

    def test_empty_string_uses_fallback(self):
        state = IncidentState(raw_event="")
        result = normalize_node(state)
        log_event = result["log_event"]

        assert log_event.message == ""
        assert log_event.raw == ""
        assert log_event.namespace == "unknown"
        assert log_event.pod_name == "unknown"
        assert log_event.container == "unknown"
        assert log_event.edge_site_id == "unknown"
        assert log_event.level == "unknown"
        assert log_event.timestamp == "unknown"

    def test_fallback_emits_loguru_warning(self):
        state = IncidentState(raw_event="not json")
        with patch("agent_service.nodes.normalize.logger") as mock_logger:
            normalize_node(state)
            mock_logger.warning.assert_called_once()

    def test_canonical_json_does_not_emit_warning(self):
        raw = json.dumps(CANONICAL_EVENT)
        state = IncidentState(raw_event=raw)
        with patch("agent_service.nodes.normalize.logger") as mock_logger:
            normalize_node(state)
            mock_logger.warning.assert_not_called()

    def test_broken_json_uses_fallback(self):
        raw = '{"message": "hello"'
        state = IncidentState(raw_event=raw)
        result = normalize_node(state)
        log_event = result["log_event"]

        assert log_event.message == raw
        assert log_event.raw == raw
        assert log_event.namespace == "unknown"
        assert log_event.pod_name == "unknown"
        assert log_event.container == "unknown"
        assert log_event.edge_site_id == "unknown"
        assert log_event.level == "unknown"
        assert log_event.timestamp == "unknown"
