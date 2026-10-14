"""Tests for the RAN RCA service FastAPI server."""

from __future__ import annotations

import json
from collections import deque
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import SAMPLE_ANOMALY, make_llm_response
from ran_rca_service.server import _handle_anomaly_message, app


def stream_graph(*updates, failure=None):
    graph = MagicMock()
    graph.inputs = []

    async def stream(anomaly, *, stream_mode):
        graph.inputs.append((anomaly, stream_mode))
        for update in updates:
            yield update
        if failure is not None:
            raise failure

    graph.astream = stream
    return graph


@pytest.fixture
def client():
    with (
        patch("ran_rca_service.server.TopicConsumer"),
        patch("ran_rca_service.server.KafkaProducer"),
        TestClient(app) as test_client,
    ):
        yield test_client


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestReadyEndpoint:
    @patch("ran_rca_service.server.KAFKA_CONSUMER_ENABLED", False)
    def test_ready_skips_kafka_when_consumer_disabled(self, client):
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"ready": True}

    def test_ready_returns_true_when_consumer_connected(self, client):
        mock_consumer = MagicMock()
        mock_consumer.is_connected = True
        client.app.state.kafka_consumer = mock_consumer
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"ready": True}

    def test_ready_returns_503_when_consumer_not_connected(self, client):
        mock_consumer = MagicMock()
        mock_consumer.is_connected = False
        client.app.state.kafka_consumer = mock_consumer
        response = client.get("/ready")
        assert response.status_code == 503
        assert "kafka" in response.json()["reason"]


class TestAnomaliesEndpoint:
    def test_low_confidence_survives_kafka_publication_and_api(self, client):
        from pathlib import Path

        import jsonschema

        result = {
            **SAMPLE_ANOMALY,
            "root_cause_category": "unknown",
            "root_cause": "cause",
            "recommended_fix": "fix",
            "ml_class": "Antenna Failure",
            "ml_class_index": 0,
            "ml_confidence": 0.4,
            "ml_status": "low_confidence",
            "ml_steer_used": False,
        }
        graph = stream_graph({"analyze": result})
        producer = MagicMock()
        _handle_anomaly_message(
            json.dumps(SAMPLE_ANOMALY).encode(),
            graph,
            producer,
            "ran-anomalies-enriched",
            client.app.state.recent_enriched,
        )
        published = json.loads(producer.send.call_args.args[1])
        schema_path = Path(__file__).resolve().parents[3] / "contracts/ran-anomaly-enriched.schema.json"
        jsonschema.Draft202012Validator(json.loads(schema_path.read_text())).validate(published)
        api_record = client.get("/anomalies").json()["anomalies"][0]
        assert api_record == published
        assert api_record["ml_class"] == "Antenna Failure"
        assert api_record["ml_confidence"] == 0.4
        assert api_record["ml_status"] == "low_confidence"
        assert api_record["ml_steer_used"] is False

    def test_anomalies_empty_by_default(self, client):
        response = client.get("/anomalies")
        assert response.status_code == 200
        assert response.json() == {"count": 0, "anomalies": []}

    def test_anomalies_returns_enriched_items(self, client):
        client.app.state.recent_enriched.append({**SAMPLE_ANOMALY, "root_cause": "stub", "recommended_fix": "stub"})

        response = client.get("/anomalies")
        body = response.json()
        assert body["count"] == 1
        assert body["anomalies"][0]["root_cause"] == "stub"

    def test_anomalies_respects_limit(self, client):
        for i in range(5):
            client.app.state.recent_enriched.append(
                {
                    "cell_id": i,
                    "band": "Band 29",
                    "anomaly_type": "X",
                    "anomaly": "x",
                    "root_cause": "r",
                    "recommended_fix": "f",
                }
            )

        response = client.get("/anomalies", params={"limit": 2})
        body = response.json()
        assert body["count"] == 2
        assert [a["cell_id"] for a in body["anomalies"]] == [3, 4]

    def test_anomalies_limit_zero_returns_empty(self, client):
        client.app.state.recent_enriched.append({**SAMPLE_ANOMALY, "root_cause": "r", "recommended_fix": "f"})

        response = client.get("/anomalies", params={"limit": 0})
        body = response.json()
        assert body["count"] == 0
        assert body["anomalies"] == []


class TestHandleAnomalyMessage:
    @pytest.mark.parametrize(
        "channel",
        json.loads((Path(__file__).resolve().parents[3] / "contracts/ran-anomalies.schema.json").read_text())[
            "properties"
        ]["kpi_window"]["items"]["required"],
    )
    def test_every_contract_channel_is_required_before_graph(self, channel):
        invalid = deepcopy(SAMPLE_ANOMALY)
        del invalid["kpi_window"][0][channel]
        graph = stream_graph()
        producer = MagicMock()
        buffer = deque(maxlen=100)
        _handle_anomaly_message(json.dumps(invalid).encode(), graph, producer, "topic", buffer)
        assert graph.inputs == []
        producer.send.assert_not_called()
        assert not buffer

    @pytest.mark.parametrize("first_failure", ["connection", "malformed_response"])
    def test_classifier_outage_then_recovery_on_same_graph(self, first_failure):
        from ran_rca_service.graph import build_graph
        from ran_rca_service.nodes.classify import RCA_CLASSES

        response = MagicMock()
        response.json.return_value = {"class": RCA_CLASSES[0], "class_index": 0, "confidence": 0.91}
        classifier_client = AsyncMock()
        malformed = MagicMock()
        malformed.json.return_value = {"class": RCA_CLASSES[0], "class_index": True, "confidence": 0.9}
        first_result = httpx.ConnectError("outage") if first_failure == "connection" else malformed
        classifier_client.post.side_effect = [first_result, response]
        classifier_client.__aenter__.return_value = classifier_client
        rag = MagicMock()
        rag.search = AsyncMock(return_value=[])
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=make_llm_response())
        producer = MagicMock()
        buffer = deque(maxlen=100)
        with (
            patch("ran_rca_service.config.CLASSIFY_INFERENCE_URL", "https://example/v1/classify"),
            patch("ran_rca_service.nodes.classify.httpx.AsyncClient", return_value=classifier_client),
            patch("ran_rca_service.nodes.rag_retrieval._rag_client", rag),
            patch("ran_rca_service.nodes.analyze.get_llm", return_value=llm),
        ):
            graph = build_graph()
            for incident_id in ("outage", "recovered"):
                anomaly = {**SAMPLE_ANOMALY, "incident_id": incident_id}
                _handle_anomaly_message(json.dumps(anomaly).encode(), graph, producer, "topic", buffer)

        assert len(buffer) == 2
        assert [record["ml_status"] for record in buffer] == ["failed", "used"]
        assert [record["ml_class"] for record in buffer] == ["", RCA_CLASSES[0]]
        assert all(record["root_cause_category"] == "antenna_misalignment" for record in buffer)
        assert all(record["root_cause"] and record["recommended_fix"] for record in buffer)
        assert producer.send.call_count == 2

    def test_real_graph_stage_error_preserves_completed_classification(self):
        from langgraph.graph import START, StateGraph
        from ran_rca_service.models import RCAState

        async def classify(_state):
            return {
                "ml_class": "Antenna Failure",
                "ml_class_index": 0,
                "ml_confidence": 0.9,
                "ml_status": "used",
                "ml_steer_used": True,
            }

        async def broken_rag(_state):
            raise RuntimeError("fault-injected graph stage")

        builder = StateGraph(RCAState)
        builder.add_node("classify", classify)
        builder.add_node("rag_retrieval", broken_rag)
        builder.add_edge(START, "classify")
        builder.add_edge("classify", "rag_retrieval")
        producer = MagicMock()
        buffer = deque(maxlen=100)
        _handle_anomaly_message(json.dumps(SAMPLE_ANOMALY).encode(), builder.compile(), producer, "topic", buffer)
        published = json.loads(producer.send.call_args.args[1])
        assert published["ml_status"] == "used"
        assert published["ml_class"] == "Antenna Failure"
        assert published["root_cause_category"] == "unknown"

    @pytest.mark.parametrize(
        "change",
        [
            lambda a: a.pop("incident_id"),
            lambda a: a.update(zone=""),
            lambda a: a.update(ad_label="normal"),
            lambda a: a.update(ad_confidence=float("nan")),
            lambda a: a.update(kpi_window=[]),
            lambda a: a["kpi_window"][0].pop("RSRP"),
            lambda a: a["kpi_window"][0].update(RSRP=None),
            lambda a: a["kpi_window"][0].update(RSRP="bad"),
        ],
    )
    def test_invalid_anomaly_is_skipped_before_graph_and_next_real_fixture_reaches_api(self, change):
        invalid = deepcopy(SAMPLE_ANOMALY)
        change(invalid)
        graph = stream_graph({"analyze": {"root_cause_category": "interference"}})
        producer = MagicMock()
        buffer = deque(maxlen=100)

        _handle_anomaly_message(json.dumps(invalid).encode(), graph, producer, "topic", buffer)
        assert graph.inputs == []
        producer.send.assert_not_called()
        assert len(buffer) == 0

        _handle_anomaly_message(json.dumps(SAMPLE_ANOMALY).encode(), graph, producer, "topic", buffer)
        assert len(buffer) == 1
        assert buffer[0]["incident_id"] == "test-001"

    @pytest.mark.parametrize(
        "classification, expected_status, expected_class",
        [
            (
                {
                    "ml_status": "used",
                    "ml_class": "Antenna Failure",
                    "ml_class_index": 0,
                    "ml_confidence": 0.9,
                    "ml_steer_used": True,
                },
                "used",
                "Antenna Failure",
            ),
            (
                {
                    "ml_status": "failed",
                    "ml_class": "",
                    "ml_class_index": None,
                    "ml_confidence": 0.0,
                    "ml_steer_used": False,
                },
                "failed",
                "",
            ),
        ],
    )
    def test_graph_failure_publishes_truthful_partial_classification(
        self, classification, expected_status, expected_class
    ):
        from pathlib import Path

        import jsonschema

        graph = stream_graph({"classify": classification}, failure=RuntimeError("rag failed"))
        producer = MagicMock()
        buffer = deque(maxlen=100)
        _handle_anomaly_message(json.dumps(SAMPLE_ANOMALY).encode(), graph, producer, "topic", buffer)
        published = json.loads(producer.send.call_args.args[1])
        schema_path = Path(__file__).resolve().parents[3] / "contracts/ran-anomaly-enriched.schema.json"
        schema = json.loads(schema_path.read_text())
        jsonschema.Draft202012Validator(schema).validate(published)
        assert published["kpi_window"] == SAMPLE_ANOMALY["kpi_window"]
        assert published["root_cause_category"] == "unknown"
        assert published["root_cause"] == published["recommended_fix"] == ""
        assert published["ml_status"] == expected_status
        assert published["ml_class"] == expected_class

    @pytest.mark.parametrize(
        "classify_url, expected_status",
        [
            ("", "disabled"),
            ("https://example/v1/classify", "failed"),
        ],
    )
    def test_graph_failure_before_classification_uses_configured_status(self, classify_url, expected_status):
        graph = stream_graph(failure=RuntimeError("classify stage failed"))
        buffer = deque(maxlen=100)
        with patch("ran_rca_service.config.CLASSIFY_INFERENCE_URL", classify_url):
            _handle_anomaly_message(json.dumps(SAMPLE_ANOMALY).encode(), graph, None, "topic", buffer)
        assert buffer[0]["ml_status"] == expected_status
        assert buffer[0]["root_cause_category"] == "unknown"

    def test_invokes_graph_and_appends_to_buffer(self):
        from collections import deque

        graph = stream_graph(
            {
                "analyze": {
                    **SAMPLE_ANOMALY,
                    "context_snippets": [],
                    "rag_query_used": "5G anomaly detection",
                    "root_cause_category": "antenna_misalignment",
                    "root_cause": "stub root cause",
                    "recommended_fix": "stub fix",
                }
            }
        )
        producer = MagicMock()
        buffer: deque = deque(maxlen=100)

        raw = json.dumps(SAMPLE_ANOMALY).encode("utf-8")
        _handle_anomaly_message(raw, graph, producer, "ran-anomalies-enriched", buffer)

        assert graph.inputs == [(SAMPLE_ANOMALY, "updates")]
        assert len(buffer) == 1
        assert buffer[0]["root_cause_category"] == "antenna_misalignment"
        assert buffer[0]["root_cause"] == "stub root cause"

    def test_publishes_enriched_to_kafka(self):
        from collections import deque

        graph = stream_graph(
            {
                "analyze": {
                    **SAMPLE_ANOMALY,
                    "context_snippets": [],
                    "rag_query_used": "",
                    "root_cause_category": "antenna_misalignment",
                    "root_cause": "cause",
                    "recommended_fix": "fix",
                    "ml_class": "Antenna Failure",
                    "ml_class_index": 0,
                    "ml_confidence": 0.91,
                    "ml_status": "used",
                    "ml_steer_used": True,
                }
            }
        )
        producer = MagicMock()
        buffer: deque = deque(maxlen=100)

        raw = json.dumps(SAMPLE_ANOMALY).encode("utf-8")
        _handle_anomaly_message(raw, graph, producer, "ran-anomalies-enriched", buffer)

        producer.send.assert_called_once()
        topic, payload = producer.send.call_args[0]
        assert topic == "ran-anomalies-enriched"
        enriched = json.loads(payload)
        assert enriched["root_cause_category"] == "antenna_misalignment"
        assert enriched["root_cause"] == "cause"
        assert enriched["recommended_fix"] == "fix"
        assert enriched["kpi_window"] == SAMPLE_ANOMALY["kpi_window"]
        assert enriched["ml_class"] == "Antenna Failure"
        assert enriched["ml_status"] == "used"
        assert enriched["ml_steer_used"] is True
        from pathlib import Path

        import jsonschema

        schema_path = Path(__file__).resolve().parents[3] / "contracts/ran-anomaly-enriched.schema.json"
        jsonschema.Draft202012Validator(json.loads(schema_path.read_text())).validate(enriched)

    def test_skips_malformed_json(self):
        from collections import deque

        graph = stream_graph()
        producer = MagicMock()
        buffer: deque = deque(maxlen=100)

        _handle_anomaly_message(b"not json", graph, producer, "topic", buffer)

        assert graph.inputs == []
        producer.send.assert_not_called()
        assert len(buffer) == 0

    def test_works_without_producer(self):
        from collections import deque

        graph = stream_graph(
            {
                "analyze": {
                    **SAMPLE_ANOMALY,
                    "context_snippets": [],
                    "rag_query_used": "",
                    "root_cause": "cause",
                    "recommended_fix": "fix",
                }
            }
        )
        buffer: deque = deque(maxlen=100)

        raw = json.dumps(SAMPLE_ANOMALY).encode("utf-8")
        _handle_anomaly_message(raw, graph, None, "topic", buffer)

        assert len(buffer) == 1

    def test_graph_error_forwards_anomaly_unenriched(self):
        from collections import deque

        graph = stream_graph(failure=RuntimeError("graph failure"))
        buffer: deque = deque(maxlen=100)

        raw = json.dumps(SAMPLE_ANOMALY).encode("utf-8")
        _handle_anomaly_message(raw, graph, None, "topic", buffer)

        assert len(buffer) == 1
        assert buffer[0]["incident_id"] == "test-001"
        assert buffer[0]["root_cause_category"] == "unknown"
        assert buffer[0]["root_cause"] == ""
        assert buffer[0]["recommended_fix"] == ""


class TestKafkaLifespan:
    @patch("ran_rca_service.server.KafkaProducer")
    @patch("ran_rca_service.server.TopicConsumer")
    @patch.multiple(
        "ran_rca_service.server",
        KAFKA_CONSUMER_ENABLED=True,
        KAFKA_BOOTSTRAP="kafka.test:9092",
        KAFKA_ANOMALIES_TOPIC="ran-anomalies",
        KAFKA_GROUP_ID="test-group",
    )
    def test_lifespan_starts_consumer_when_enabled(self, TopicConsumer, KafkaProducer):
        mock_consumer = MagicMock()
        TopicConsumer.return_value = mock_consumer

        with TestClient(app):
            pass

        TopicConsumer.assert_called_once()
        _, kwargs = TopicConsumer.call_args
        assert kwargs["bootstrap_servers"] == "kafka.test:9092"
        assert kwargs["topic"] == "ran-anomalies"
        assert kwargs["group_id"] == "test-group"
        mock_consumer.start.assert_called_once()
        mock_consumer.stop.assert_called_once()

    @patch("ran_rca_service.server.KafkaProducer")
    @patch("ran_rca_service.server.TopicConsumer")
    @patch("ran_rca_service.server.KAFKA_CONSUMER_ENABLED", False)
    def test_lifespan_skips_consumer_when_disabled(self, TopicConsumer, KafkaProducer):
        with TestClient(app):
            pass

        TopicConsumer.assert_not_called()

    @patch("ran_rca_service.server.KafkaProducer")
    @patch("ran_rca_service.server.TopicConsumer")
    @patch("ran_rca_service.server.KAFKA_CONSUMER_ENABLED", True)
    def test_lifespan_wires_handler_into_enriched_buffer(self, TopicConsumer, KafkaProducer):
        captured_handler = {}

        def _capture(handler, **kwargs):
            captured_handler["handler"] = handler
            return MagicMock()

        TopicConsumer.side_effect = _capture

        mock_rag = MagicMock()
        mock_rag.search = AsyncMock(return_value=[])

        with (
            patch("ran_rca_service.nodes.rag_retrieval._rag_client", mock_rag),
            TestClient(app) as client,
        ):
            raw = json.dumps(SAMPLE_ANOMALY).encode("utf-8")
            captured_handler["handler"](raw)

            response = client.get("/anomalies")
            assert response.json()["count"] == 1
