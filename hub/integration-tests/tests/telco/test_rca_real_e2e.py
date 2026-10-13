"""Opt-in live fixture → AD → Kafka → RCA → RAG/Granite → API/chat probe.

Run this test once per deployed configuration with RCA_EXPECTED_MODE set to
used, low_confidence, or disabled. Set RCA_GUIDANCE_THRESHOLD to the deployed
threshold for classifier-enabled runs. RCA_PINNED_CONFIDENCE can be set to the
actual confidence observed in the first run to prove the same prediction is
used for the second run. No model result is fabricated here.
"""

import json
import os
import time
from pathlib import Path

import httpx
import jsonschema
import pytest

pytestmark = [pytest.mark.telco, pytest.mark.integration]

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "hub/telco-oran/src/telco_oran/fixtures/antenna_failure.json"
TEMPLATES = {
    "antenna_misalignment": "ran-antenna-tilt-adjust",
    "interference": "ran-interference-mitigation",
    "scheduler_degradation": "ran-scheduler-optimize",
    "congestion": "ran-load-balance",
    "capacity_exhaustion": "ran-capacity-expand",
    "cell_failure": "ran-cell-recovery",
    "unknown": "ran-generic-remediation",
}


@pytest.mark.skipif(os.getenv("RCA_REAL_E2E") != "1", reason="Requires the deployed RCA predictor")
def test_pinned_fixture_reaches_chat_in_expected_guidance_mode(ran_chatbot_client):
    rca_url = os.environ["RAN_RCA_SERVICE_URL"]
    remediation_url = os.environ["RAN_REMEDIATION_SERVICE_URL"]
    mode = os.environ.get("RCA_EXPECTED_MODE", "used")
    assert mode in {"used", "low_confidence", "disabled"}
    fixture = json.loads(FIXTURE.read_text())
    trigger = ran_chatbot_client.post("/api/demo/trigger", json={"scenario": "antenna_failure"})
    assert trigger.status_code == 200
    incident_id = trigger.json()["incident_id"]

    deadline = time.monotonic() + 240
    anomaly = None
    while time.monotonic() < deadline:
        response = ran_chatbot_client.get("/api/anomalies")
        assert response.status_code == 200
        anomaly = next((item for item in response.json()["anomalies"] if item["incident_id"] == incident_id), None)
        if anomaly is not None:
            break
        time.sleep(5)
    assert anomaly is not None, f"incident {incident_id} did not reach enriched API"
    assert anomaly["zone"] == fixture["zone"]
    assert anomaly["application"] == fixture["application"]
    assert anomaly["kpi_window"] == fixture["kpi_window"]
    assert anomaly["ad_label"] == "anomalous"
    assert anomaly["ml_status"] == mode
    assert anomaly["ml_steer_used"] is (mode == "used")
    if mode == "disabled":
        assert anomaly["ml_class"] == ""
        assert anomaly["ml_class_index"] is None
        assert anomaly["ml_confidence"] == 0
    else:
        assert anomaly["ml_class_index"] in range(10)
        confidence = anomaly["ml_confidence"]
        assert 0 < confidence < 1
        threshold = float(os.environ.get("RCA_GUIDANCE_THRESHOLD", "0.6"))
        assert (confidence >= threshold) is (mode == "used")
        pinned = os.environ.get("RCA_PINNED_CONFIDENCE")
        if pinned is not None:
            assert confidence == pytest.approx(float(pinned), abs=1e-6)
    assert anomaly["root_cause_category"] in {
        "antenna_misalignment", "interference", "scheduler_degradation", "congestion",
        "capacity_exhaustion", "cell_failure", "unknown",
    }
    assert anomaly["root_cause"]
    assert anomaly["recommended_fix"]
    schema = json.loads((ROOT / "contracts/ran-anomaly-enriched.schema.json").read_text())
    # The chatbot API receives this record only through enriched Kafka.
    jsonschema.Draft202012Validator(schema).validate(anomaly)

    with httpx.Client(base_url=rca_url, timeout=20.0) as client:
        published = client.get("/anomalies").json()["anomalies"]
    kafka_projection = next(item for item in published if item["incident_id"] == incident_id)
    jsonschema.Draft202012Validator(schema).validate(kafka_projection)
    assert {key: kafka_projection[key] for key in ("kpi_window", "ml_class", "ml_status", "root_cause_category")} == {
        key: anomaly[key] for key in ("kpi_window", "ml_class", "ml_status", "root_cause_category")
    }

    remediation = None
    remediation_deadline = time.monotonic() + 240
    with httpx.Client(base_url=remediation_url, timeout=20.0) as client:
        while time.monotonic() < remediation_deadline:
            results = client.get("/remediation-results").json()["results"]
            remediation = next((item for item in results if item["incident_id"] == incident_id), None)
            if remediation:
                break
            time.sleep(5)
    assert remediation is not None, f"incident {incident_id} did not reach remediation"
    assert remediation["template_name"] == TEMPLATES[anomaly["root_cause_category"]]

    chat = ran_chatbot_client.post("/api/chat", json={"message": f"Explain incident {incident_id}"})
    assert chat.status_code == 200
    reply = chat.json()["reply"]
    assert incident_id in reply
    assert "Mantis RCA Prediction" in reply
    assert "Final LLM Operational Category" in reply
    assert anomaly["root_cause_category"] in reply
    assert {
        "used": "accepted advisory prediction",
        "low_confidence": "low-confidence prediction",
        "disabled": "disabled; no classifier request or prediction",
    }[mode] in reply
