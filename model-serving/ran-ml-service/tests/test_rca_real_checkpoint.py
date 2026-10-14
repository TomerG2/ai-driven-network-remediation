"""Opt-in parity check for the recovered issue-196 RCA checkpoint."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from ran_ml_service.model import MantisPredictor
from ran_ml_service.server import app

ROOT = Path(__file__).resolve().parents[3]
CHECKPOINT_SHA256 = "0ecd02d50eed50130476c0c543503f9f3d1595507502664d3e5b8fb01c3eccfe"
PREPROCESSING_SHA256 = "1a8e0144bb4a65f48133c4ad36491aba6432b817d64b8d3521a3c8de913ddeae"


@pytest.mark.skipif(not os.getenv("RCA_CHECKPOINT_PATH"), reason="RCA_CHECKPOINT_PATH is required")
def test_recovered_checkpoint_classifies_pinned_real_fixture():
    checkpoint = Path(os.environ["RCA_CHECKPOINT_PATH"])
    preprocessing = checkpoint.with_name("rca_preprocessing.json")
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == CHECKPOINT_SHA256
    assert hashlib.sha256(preprocessing.read_bytes()).hexdigest() == PREPROCESSING_SHA256

    fixture = json.loads((ROOT / "hub/telco-oran/src/telco_oran/fixtures/antenna_failure.json").read_text())
    predictor = MantisPredictor()
    with (
        patch("ran_ml_service.model.MANTIS_MODEL_PATH", str(checkpoint)),
        patch("ran_ml_service.model.TASK", "classify"),
        patch("ran_ml_service.server.TASK", "classify"),
        patch("ran_ml_service.server.predictor", predictor),
        TestClient(app) as client,
    ):
        assert client.get("/ready").json() == {"ready": True, "task": "classify"}
        response = client.post("/v1/classify", json={"kpi_window": fixture["kpi_window"]})

    assert response.status_code == 200
    assert response.json() == {
        "class": "Antenna Failure",
        "class_index": 0,
        "confidence": pytest.approx(0.9293, abs=1e-4),
    }
