"""FastAPI app: health/readiness probes + Kafka-driven RAN RCA enrichment."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections import deque
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from kafka import KafkaProducer
from loguru import logger
from pydantic import ValidationError
from ran_rca_service import config
from ran_rca_service.config import (
    KAFKA_ANOMALIES_TOPIC,
    KAFKA_BOOTSTRAP,
    KAFKA_CONSUMER_ENABLED,
    KAFKA_ENRICHED_TOPIC,
    KAFKA_GROUP_ID,
    RECENT_ANOMALIES_LIMIT,
)
from ran_rca_service.graph import build_graph
from ran_rca_service.models import AnomalyInput
from shared.kafka import TopicConsumer

EnrichedBuffer = deque[dict[str, Any]]


_consumer_loop: asyncio.AbstractEventLoop | None = None


def _get_consumer_loop() -> asyncio.AbstractEventLoop:
    global _consumer_loop
    if _consumer_loop is None or _consumer_loop.is_closed():
        _consumer_loop = asyncio.new_event_loop()
    return _consumer_loop


def _handle_anomaly_message(
    raw_value: bytes,
    graph,
    producer: KafkaProducer | None,
    enriched_topic: str,
    recent_enriched: EnrichedBuffer,
) -> None:
    try:
        anomaly = json.loads(raw_value)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning(
            "Skipping malformed RAN anomaly message sha256={}: {}",
            hashlib.sha256(raw_value).hexdigest()[:12],
            exc,
        )
        return

    try:
        AnomalyInput.model_validate(anomaly)
    except ValidationError as exc:
        incident_id = anomaly.get("incident_id", "") if isinstance(anomaly, dict) else ""
        logger.warning("Skipping invalid RAN anomaly message incident_id={}: {}", incident_id, exc)
        return

    result: dict[str, Any] = {}

    async def collect_updates() -> None:
        async for update in graph.astream(anomaly, stream_mode="updates"):
            for stage_result in update.values():
                if isinstance(stage_result, dict):
                    result.update(stage_result)

    try:
        loop = _get_consumer_loop()
        loop.run_until_complete(collect_updates())
    except Exception:  # noqa: BLE001 - Kafka consumption must survive graph failures.
        logger.exception("Graph invocation failed, forwarding anomaly with available classification")
        result.update(root_cause_category="unknown", root_cause="", recommended_fix="")

    enriched = {
        "incident_id": anomaly["incident_id"],
        "zone": anomaly["zone"],
        "application": anomaly["application"],
        "kpi_window": anomaly["kpi_window"],
        "ad_label": anomaly["ad_label"],
        "ad_confidence": anomaly["ad_confidence"],
        "root_cause_category": result.get("root_cause_category", "unknown"),
        "root_cause": result.get("root_cause", ""),
        "recommended_fix": result.get("recommended_fix", ""),
        "ml_class": result.get("ml_class", ""),
        "ml_class_index": result.get("ml_class_index"),
        "ml_confidence": result.get("ml_confidence", 0.0),
        "ml_status": result.get("ml_status", "failed" if config.CLASSIFY_INFERENCE_URL else "disabled"),
        "ml_steer_used": result.get("ml_steer_used", False),
    }

    logger.info("RAN anomaly enriched: incident_id={} zone={}", enriched["incident_id"], enriched["zone"])
    recent_enriched.append(enriched)

    if producer is not None:
        producer.send(enriched_topic, json.dumps(enriched).encode("utf-8"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    graph = build_graph()
    recent_enriched: EnrichedBuffer = deque(maxlen=RECENT_ANOMALIES_LIMIT)

    app.state.recent_enriched = recent_enriched

    producer: KafkaProducer | None = None
    consumer: TopicConsumer | None = None

    if KAFKA_CONSUMER_ENABLED:
        producer = KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)

        consumer = TopicConsumer(
            lambda raw_value: _handle_anomaly_message(
                raw_value, graph, producer, KAFKA_ENRICHED_TOPIC, recent_enriched
            ),
            name="ran-anomaly",
            bootstrap_servers=KAFKA_BOOTSTRAP,
            topic=KAFKA_ANOMALIES_TOPIC,
            group_id=KAFKA_GROUP_ID,
        )
        consumer.start()
        logger.info("RAN RCA service Kafka consumer enabled")
    else:
        logger.info("RAN RCA service Kafka consumer disabled")

    app.state.kafka_consumer = consumer
    app.state.kafka_producer = producer

    yield

    if consumer is not None:
        consumer.stop()
    if producer is not None:
        producer.close()


app = FastAPI(title=os.environ.get("APP_TITLE", "ran-rca-service"), lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(req: Request):
    not_ready = []

    if KAFKA_CONSUMER_ENABLED:
        consumer: TopicConsumer | None = getattr(req.app.state, "kafka_consumer", None)
        if consumer is None or not consumer.is_connected:
            not_ready.append("kafka-consumer")

        if req.app.state.kafka_producer is None:
            not_ready.append("kafka-producer")

    if not_ready:
        return JSONResponse({"ready": False, "reason": ", ".join(not_ready)}, status_code=503)
    return {"ready": True}


@app.get("/anomalies")
def anomalies(req: Request, limit: int = Query(default=50, ge=0)):
    recent: EnrichedBuffer = req.app.state.recent_enriched
    items = list(recent)[-limit:] if limit else []
    return {"count": len(items), "anomalies": items}


def start():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8003")))
