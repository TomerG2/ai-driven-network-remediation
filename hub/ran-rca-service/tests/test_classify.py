"""Classifier boundary, guidance threshold, and category independence."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from helpers import make_state
from ran_rca_service.config import parse_classify_confidence_threshold
from ran_rca_service.nodes.classify import RCA_CLASSES, classify_node


@pytest.mark.asyncio
async def test_confident_prediction_uses_only_window_and_optional_token():
    response = MagicMock()
    response.json.return_value = {"class": RCA_CLASSES[0], "class_index": 0, "confidence": 0.6}
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client
    with (
        patch("ran_rca_service.config.CLASSIFY_INFERENCE_URL", "https://example/v1/classify"),
        patch("ran_rca_service.config.CLASSIFY_TOKEN", "secret"),
        patch("ran_rca_service.config.CLASSIFY_CONFIDENCE_THRESHOLD", 0.6),
        patch("ran_rca_service.nodes.classify.httpx.AsyncClient", return_value=client),
    ):
        state = make_state()
        result = await classify_node(state)
    assert result["ml_status"] == "used"
    assert result["ml_steer_used"] is True
    assert client.post.call_args.kwargs["json"] == {"kpi_window": state.kpi_window}
    assert client.post.call_args.kwargs["headers"] == {"Authorization": "Bearer secret"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prediction",
    [
        [],
        {"class": RCA_CLASSES[0], "class_index": 0, "confidence": 0.59},
        {"class": RCA_CLASSES[1], "class_index": 0, "confidence": 0.99},
        {"class": RCA_CLASSES[0], "class_index": True, "confidence": 0.99},
        {"class": RCA_CLASSES[0], "class_index": 0, "confidence": float("nan")},
    ],
)
async def test_untrusted_or_low_confidence_prediction_does_not_steer(prediction):
    response = MagicMock()
    response.json.return_value = prediction
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client
    with (
        patch("ran_rca_service.config.CLASSIFY_INFERENCE_URL", "https://example/v1/classify"),
        patch("ran_rca_service.config.CLASSIFY_TOKEN", ""),
        patch("ran_rca_service.nodes.classify.httpx.AsyncClient", return_value=client),
    ):
        result = await classify_node(make_state())
    assert result["ml_steer_used"] is False
    assert result["ml_status"] in {"low_confidence", "failed"}
    assert client.post.call_args.kwargs["headers"] == {}


@pytest.mark.asyncio
async def test_disabled_classifier_preserves_llm_only_mode():
    with (
        patch("ran_rca_service.config.CLASSIFY_INFERENCE_URL", ""),
        patch("ran_rca_service.nodes.classify.httpx.AsyncClient") as client,
    ):
        result = await classify_node(make_state(ml_class="stale", ml_steer_used=True))
    assert result == {
        "ml_class": "",
        "ml_class_index": None,
        "ml_confidence": 0.0,
        "ml_status": "disabled",
        "ml_steer_used": False,
    }
    client.assert_not_called()


@pytest.mark.parametrize("raw", ["", "nan", "inf", "-inf", "-0.01", "1.01", "bad"])
def test_invalid_guidance_threshold_fails_fast(raw):
    with pytest.raises(ValueError, match="CLASSIFY_CONFIDENCE_THRESHOLD"):
        parse_classify_confidence_threshold(raw)


@pytest.mark.parametrize("raw, expected", [("0", 0.0), ("0.6", 0.6), ("1", 1.0)])
def test_valid_guidance_threshold(raw, expected):
    assert parse_classify_confidence_threshold(raw) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold, expected_status", [(0.5, "used"), (0.8, "low_confidence"), (0.73, "used")])
async def test_same_prediction_changes_mode_only_with_threshold(threshold, expected_status):
    response = MagicMock()
    response.json.return_value = {"class": RCA_CLASSES[0], "class_index": 0, "confidence": 0.73}
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client
    with (
        patch("ran_rca_service.config.CLASSIFY_INFERENCE_URL", "https://example/v1/classify"),
        patch("ran_rca_service.config.CLASSIFY_CONFIDENCE_THRESHOLD", threshold),
        patch("ran_rca_service.nodes.classify.httpx.AsyncClient", return_value=client),
    ):
        result = await classify_node(make_state())
    assert result["ml_status"] == expected_status
    assert result["ml_class"] == RCA_CLASSES[0]
    assert result["ml_confidence"] == 0.73


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prediction",
    [
        {"class": RCA_CLASSES[0], "class_index": "0", "confidence": 0.9},
        {"class": RCA_CLASSES[0], "class_index": 0.0, "confidence": 0.9},
        {"class": RCA_CLASSES[0], "class_index": -1, "confidence": 0.9},
        {"class": RCA_CLASSES[0], "class_index": 10, "confidence": 0.9},
        {"class": RCA_CLASSES[0], "class_index": 0, "confidence": True},
        {"class": RCA_CLASSES[0], "class_index": 0, "confidence": float("inf")},
        {"class": RCA_CLASSES[0], "class_index": 0},
    ],
)
async def test_invalid_classifier_response_is_explicit_failure(prediction):
    response = MagicMock()
    response.json.return_value = prediction
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client
    with (
        patch("ran_rca_service.config.CLASSIFY_INFERENCE_URL", "https://example/v1/classify"),
        patch("ran_rca_service.nodes.classify.httpx.AsyncClient", return_value=client),
    ):
        assert await classify_node(make_state()) == {
            "ml_class": "",
            "ml_class_index": None,
            "ml_confidence": 0.0,
            "ml_status": "failed",
            "ml_steer_used": False,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("connection refused"),
        httpx.HTTPStatusError(
            "503", request=httpx.Request("POST", "https://example/v1/classify"), response=httpx.Response(503)
        ),
    ],
)
async def test_classifier_transport_failure_uses_llm_only(failure):
    response = MagicMock()
    response.raise_for_status.side_effect = failure
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client
    with (
        patch("ran_rca_service.config.CLASSIFY_INFERENCE_URL", "https://example/v1/classify"),
        patch("ran_rca_service.nodes.classify.httpx.AsyncClient", return_value=client) as factory,
    ):
        result = await classify_node(make_state())
    assert result["ml_status"] == "failed"
    assert result["ml_steer_used"] is False
    assert result["ml_confidence"] == 0.0
    factory.assert_called_once_with(timeout=5.0)
