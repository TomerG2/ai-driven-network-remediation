"""Opt-in live fixture → AD → Kafka → RCA → RAG/Granite → API/chat probe.

Run this test in order: used with threshold 0, low_confidence with threshold 1,
then disabled with an empty classify URL. Set RCA_EVIDENCE_FILE to the same
JSON path for all runs. The first run pins the real prediction; subsequent runs
must match it. Set RCA_GUIDANCE_THRESHOLD and RCA_DEPLOYMENT_NAMESPACE for each
deployment. Set RCA_EXPECTED_CLASSIFY_URL and RCA_EXPECTED_CLASSIFY_TOKEN to the
values deployed in the RCA container; leave both empty for disabled mode when
appropriate. For failure and recovery, run failed with the classify URL
still configured and its endpoint unreachable, then run used after restoring
the predictor, without restarting RCA. The test reads the running RCA
container's environment and records the order in RCA_EVIDENCE_FILE.
"""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx
import jsonschema
import pytest

pytestmark = [pytest.mark.telco, pytest.mark.integration]

ROOT = Path(__file__).resolve().parents[4]
SCENARIO = os.getenv("RCA_FIXTURE_SCENARIO", "antenna_failure")
FIXTURE = ROOT / "hub/telco-oran/src/telco_oran/fixtures" / f"{SCENARIO}.json"
REFERENCE = json.loads((ROOT / "model-serving/ran-ml-service/tests/fixtures/rca_reference.json").read_text())
PINNED_RCA_PREDICTION = next(case for case in REFERENCE["cases"] if case["fixture"] == FIXTURE.name)
TEMPLATES = {
    "antenna_misalignment": "ran-antenna-tilt-adjust",
    "interference": "ran-interference-mitigation",
    "scheduler_degradation": "ran-scheduler-optimize",
    "congestion": "ran-load-balance",
    "capacity_exhaustion": "ran-capacity-expand",
    "cell_failure": "ran-cell-recovery",
    "unknown": "ran-generic-remediation",
}


def _rca_exec(*command: str) -> str:
    result = subprocess.run(
        [
            "oc",
            "-n",
            os.environ["RCA_DEPLOYMENT_NAMESPACE"],
            "exec",
            f"deployment/{os.environ.get('RCA_DEPLOYMENT_NAME', 'hub-ran-rca-service')}",
            "-c",
            "ran-rca-service",
            "--",
            *command,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _rca_instance() -> str:
    return _rca_exec("sh", "-c", "hostname; awk '{print $22}' /proc/1/stat")


def _publish_invalid_anomalies() -> tuple[str, str]:
    invalid_id = f"invalid-rca-{uuid4().hex}"
    malformed = f"not-json-{invalid_id}"
    script = (
        "import json,os,sys; from kafka import KafkaProducer; "
        "p=KafkaProducer(bootstrap_servers=os.environ['KAFKA_BOOTSTRAP']); "
        "topic=os.environ['KAFKA_ANOMALIES_TOPIC']; "
        "bad={'incident_id':sys.argv[1],'zone':'A','application':'File',"
        "'kpi_window':[],'ad_label':'anomalous','ad_confidence':0.9}; "
        "p.send(topic,sys.argv[2].encode()).get(timeout=10); "
        "p.send(topic,json.dumps(bad).encode()).get(timeout=10); p.close()"
    )
    _rca_exec("python", "-c", script, invalid_id, malformed)
    return invalid_id, hashlib.sha256(malformed.encode()).hexdigest()[:12]


def _wait_for_invalid_rejection(invalid_id: str, malformed_hash: str, pod: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        logs = subprocess.run(
            [
                "oc",
                "-n",
                os.environ["RCA_DEPLOYMENT_NAMESPACE"],
                "logs",
                f"pod/{pod}",
                "-c",
                "ran-rca-service",
                "--since=5m",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        if (
            f"Skipping invalid RAN anomaly message incident_id={invalid_id}" in logs
            and f"Skipping malformed RAN anomaly message sha256={malformed_hash}" in logs
        ):
            return
        time.sleep(2)
    pytest.fail(f"RCA consumer did not log rejection of {invalid_id}")


def _assert_running_rca_config(mode: str, threshold: str) -> None:
    namespace = os.environ["RCA_DEPLOYMENT_NAMESPACE"]
    deployment = os.environ.get("RCA_DEPLOYMENT_NAME", "hub-ran-rca-service")
    result = subprocess.run(
        [
            "oc",
            "-n",
            namespace,
            "exec",
            f"deployment/{deployment}",
            "-c",
            "ran-rca-service",
            "--",
            "printenv",
            "CLASSIFY_INFERENCE_URL",
            "CLASSIFY_TOKEN",
            "CLASSIFY_CONFIDENCE_THRESHOLD",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    actual_url, actual_token, actual_threshold = result.stdout.splitlines()
    expected_url = os.environ.get("RCA_EXPECTED_CLASSIFY_URL", "")
    assert (actual_url == expected_url) and (bool(actual_url) is (mode != "disabled"))
    assert actual_token == os.environ.get("RCA_EXPECTED_CLASSIFY_TOKEN", "")
    assert actual_threshold == threshold


@pytest.mark.skipif(os.getenv("RCA_REAL_E2E") != "1", reason="Requires the deployed RCA predictor")
def test_pinned_fixture_reaches_chat_in_expected_guidance_mode(ran_chatbot_client):
    rca_url = os.environ["RAN_RCA_SERVICE_URL"]
    remediation_url = os.environ["RAN_REMEDIATION_SERVICE_URL"]
    mode = os.environ.get("RCA_EXPECTED_MODE", "used")
    assert mode in {"used", "low_confidence", "disabled", "failed"}
    threshold = os.environ["RCA_GUIDANCE_THRESHOLD"]
    _assert_running_rca_config(mode, threshold)
    evidence_path = Path(os.environ["RCA_EVIDENCE_FILE"])
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {"runs": {}}
    if mode in {"low_confidence", "disabled"}:
        assert "used" in evidence["runs"], "Run the guided scenario first to pin the model prediction"
    if mode == "disabled":
        assert "low_confidence" in evidence["runs"], "Run the unsteered scenario before disabled mode"
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == PINNED_RCA_PREDICTION["fixture_sha256"]
    fixture = json.loads(FIXTURE.read_text())
    rca_instance = _rca_instance()
    with httpx.Client(base_url=rca_url, timeout=20.0) as client:
        assert client.get("/ready").json() == {"ready": True}
    invalid_id, malformed_hash = _publish_invalid_anomalies()
    _wait_for_invalid_rejection(invalid_id, malformed_hash, rca_instance.splitlines()[0])
    trigger = ran_chatbot_client.post("/api/demo/trigger", json={"scenario": SCENARIO})
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
    assert all(
        item["incident_id"] != invalid_id for item in ran_chatbot_client.get("/api/anomalies").json()["anomalies"]
    )
    assert anomaly["zone"] == fixture["zone"]
    assert anomaly["application"] == fixture["application"]
    assert anomaly["kpi_window"] == fixture["kpi_window"]
    assert anomaly["ad_label"] == "anomalous"
    assert anomaly["ml_status"] == mode
    assert anomaly["ml_steer_used"] is (mode == "used")
    if mode in {"disabled", "failed"}:
        assert anomaly["ml_class"] == ""
        assert anomaly["ml_class_index"] is None
        assert anomaly["ml_confidence"] == 0
    else:
        assert anomaly["ml_class_index"] in range(10)
        confidence = anomaly["ml_confidence"]
        assert 0 < confidence < 1
        assert anomaly["ml_class"] == PINNED_RCA_PREDICTION["class"]
        assert anomaly["ml_class_index"] == PINNED_RCA_PREDICTION["class_index"]
        assert confidence == pytest.approx(PINNED_RCA_PREDICTION["confidence"], abs=1e-4)
        assert (confidence >= float(threshold)) is (mode == "used")
        if mode == "low_confidence":
            pinned = evidence["prediction"]
            assert anomaly["ml_class"] == pinned["class"]
            assert anomaly["ml_class_index"] == pinned["class_index"]
            assert confidence == pytest.approx(pinned["confidence"], abs=1e-6)
    assert anomaly["root_cause_category"] in {
        "antenna_misalignment",
        "interference",
        "scheduler_degradation",
        "congestion",
        "capacity_exhaustion",
        "cell_failure",
        "unknown",
    }
    assert anomaly["root_cause"]
    assert anomaly["recommended_fix"]
    schema = json.loads((ROOT / "contracts/ran-anomaly-enriched.schema.json").read_text())
    # The chatbot API receives this record only through enriched Kafka.
    jsonschema.Draft202012Validator(schema).validate(anomaly)

    with httpx.Client(base_url=rca_url, timeout=20.0) as client:
        published = client.get("/anomalies").json()["anomalies"]
    kafka_projection = next(item for item in published if item["incident_id"] == incident_id)
    assert all(item["incident_id"] != invalid_id for item in published)
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
        "failed": "failed; no valid classifier prediction",
    }[mode] in reply
    if mode == "used":
        evidence["prediction"] = {
            "class": anomaly["ml_class"],
            "class_index": anomaly["ml_class_index"],
            "confidence": anomaly["ml_confidence"],
        }
    evidence["runs"][mode] = {
        "incident_id": incident_id,
        "zone": anomaly["zone"],
        "application": anomaly["application"],
        "threshold": threshold,
        "classify_url": os.environ.get("RCA_EXPECTED_CLASSIFY_URL", ""),
        "ml_status": anomaly["ml_status"],
        "ml_steer_used": anomaly["ml_steer_used"],
        "ml_class": anomaly["ml_class"],
        "ml_confidence": anomaly["ml_confidence"],
        "root_cause_category": anomaly["root_cause_category"],
        "root_cause": anomaly["root_cause"],
        "recommended_fix": anomaly["recommended_fix"],
        "remediation_template": remediation["template_name"],
        "chat_reply": reply,
        "rca_instance": rca_instance,
        "invalid_incident_id": invalid_id,
    }
    evidence.setdefault("sequence", []).append({"mode": mode, "incident_id": incident_id})
    if mode == "used" and len(evidence["sequence"]) >= 2 and evidence["sequence"][-2]["mode"] == "failed":
        assert rca_instance == evidence["runs"]["failed"]["rca_instance"], "RCA consumer restarted during recovery"
        evidence["recovery_confirmed"] = True
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
