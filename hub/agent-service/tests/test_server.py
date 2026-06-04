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
