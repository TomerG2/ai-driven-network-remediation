from fastapi.testclient import TestClient

from agent_service.server import app


client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestReadyEndpoint:
    def test_ready_returns_true(self):
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"ready": True}


REMEDIATION_STATE_FIELDS = {
    "raw_event",
    "confidence_override",
    "context_snippets",
    "root_cause_analysis",
    "decision",
    "execution_result",
    "notifications_sent",
    "awaiting_human_approval",
}


class TestRemediateEndpoint:
    def test_post_remediate_returns_full_state(self):
        response = client.post("/remediate", json={"raw_event": "test event"})
        assert response.status_code == 200
        body = response.json()
        assert body["raw_event"] == "test event"
        assert set(body.keys()) == REMEDIATION_STATE_FIELDS
        assert body["decision"] != ""

    def test_post_remediate_rejects_missing_raw_event(self):
        response = client.post("/remediate", json={})
        assert response.status_code == 422
