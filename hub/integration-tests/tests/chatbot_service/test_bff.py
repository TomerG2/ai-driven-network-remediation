"""Integration tests for the chatbot BFF service.

These run against a deployed chatbot service (via port-forward or direct URL).
Set CHATBOT_SERVICE_URL env var to override the default http://localhost:8080.
"""


def test_health(chatbot_client):
    """Service is alive and reports correct identity."""
    response = chatbot_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "noc-chatbot-bff"


def test_summary(chatbot_client):
    """Summary endpoint returns agent state and incident count."""
    response = chatbot_client.get("/api/summary")
    assert response.status_code == 200
    data = response.json()
    assert "agent_status" in data
    assert "open_incidents" in data
    assert "site" in data
    assert "cluster" in data
    assert "timestamp" in data
    assert data["agent_status"] == "running"


def test_integrations(chatbot_client):
    """Integrations endpoint returns probed service statuses."""
    response = chatbot_client.get("/api/integrations")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "up" in data
    assert "down" in data
    assert "integrations" in data
    assert "slo" in data
    assert "incident_movie" in data
    assert "business_impact" in data
    assert data["total"] >= 1
    assert isinstance(data["integrations"], list)


def test_chat(chatbot_client):
    """Chat endpoint accepts a message and returns a structured reply."""
    response = chatbot_client.post(
        "/api/chat",
        json={"message": "What is the current MCP status?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "session_id" in data
    assert "model_name" in data
    assert "model_source" in data
    assert len(data["reply"]) > 0


def test_chat_empty_message(chatbot_client):
    """Chat endpoint handles empty message gracefully."""
    response = chatbot_client.post("/api/chat", json={"message": ""})
    assert response.status_code == 200
    data = response.json()
    assert "Please enter a question" in data["reply"]


def test_demo_trigger(chatbot_client):
    """Demo trigger queues a Kafka event (may fail if Kafka is unreachable)."""
    response = chatbot_client.post(
        "/api/demo/trigger",
        json={"scenario": "crashloop", "site": "edge-01"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("queued", "error")
    if data["status"] == "queued":
        assert data["scenario"] == "crashloop"
        assert "kafka_offset" in data
