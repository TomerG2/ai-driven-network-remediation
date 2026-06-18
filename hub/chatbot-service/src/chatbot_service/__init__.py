"""
NOC Dashboard Backend-for-Frontend (BFF)
========================================
Aggregates operational state from MCP servers, Kafka incident-audit,
ServiceNow, and vLLM to power the React dashboard.

Endpoints:
  GET  /health             - Liveness probe
  GET  /api/summary        - Agent status, site, open incidents
  GET  /api/integrations   - MCP/platform probes, SLO metrics, incident timeline
  POST /api/chat           - NOC chat backed by vLLM with operational context
  POST /api/demo/trigger   - Publish failure scenario to Kafka
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from .chat import build_chat_context, call_model, format_chat_reply
from .config import (
    APP_VERSION,
    CORS_ORIGINS,
    DEMO_TOPIC,
    INTEGRATIONS_CACHE_TTL,
    INTEGRATION_TARGETS,
    MODEL_NAME,
)
from .kafka import build_demo_event, fetch_recent_audits, publish_demo_event
from .probes import fetch_servicenow_incident_count, probe_http
from .slo import build_incident_movie, compute_slo_metrics, normalize_incident_record
from .utils import normalize_session_id, utc_now

# ── App State ─────────────────────────────────────────────────────
MAX_CHAT_SESSIONS = 100
chat_sessions: dict[str, list[dict[str, str]]] = {}
_integrations_cache: dict[str, Any] = {"ts": 0.0, "payload": None}

app = FastAPI(
    title="NOC Dashboard BFF",
    version=APP_VERSION,
    description="Backend-for-Frontend powering the AI-Driven Network Remediation dashboard",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ───────────────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(max_length=1000)
    session_id: str | None = None


class DemoTriggerRequest(BaseModel):
    scenario: str = "crashloop"
    site: str = "edge-01"


# ── Integrations Builder ──────────────────────────────────────────


async def _build_integrations() -> dict[str, Any]:
    """Probe all services and compute SLO/incident data."""
    probes = await asyncio.gather(*(probe_http(t["probe_url"]) for t in INTEGRATION_TARGETS))

    integrations: list[dict[str, Any]] = []
    up_count = 0
    for target, probe in zip(INTEGRATION_TARGETS, probes):
        if probe["status"] == "up":
            up_count += 1
        integrations.append({
            "id": target["id"],
            "name": target["name"],
            "group": target["group"],
            "status": probe["status"],
            "http_code": probe["http_code"],
        })

    audits = await asyncio.to_thread(fetch_recent_audits)
    slo = compute_slo_metrics(audits, up_count, len(integrations))
    movie, impact = build_incident_movie(audits, slo)

    return {
        "timestamp": utc_now(),
        "total": len(integrations),
        "up": up_count,
        "down": len(integrations) - up_count,
        "slo": slo,
        "incident_movie": movie,
        "business_impact": impact,
        "integrations": integrations,
    }


async def get_integrations(force_refresh: bool = False) -> dict[str, Any]:
    """Return cached integrations payload (TTL-based)."""
    now = time.time()
    cached = _integrations_cache.get("payload")
    cached_ts = float(_integrations_cache.get("ts", 0.0) or 0.0)
    if not force_refresh and cached is not None and (now - cached_ts) <= INTEGRATIONS_CACHE_TTL:
        return cached
    payload = await _build_integrations()
    _integrations_cache["payload"] = payload
    _integrations_cache["ts"] = now
    return payload


# ── Endpoints ─────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "noc-chatbot-bff", "version": APP_VERSION}


@app.get("/ready")
async def ready():
    """Readiness probe — verifies Kafka and ServiceNow are reachable."""
    from .config import KAFKA_BOOTSTRAP, SERVICENOW_URL

    checks: dict[str, bool] = {}

    kafka_probe = await probe_http(f"http://{KAFKA_BOOTSTRAP.split(',')[0]}", timeout=2.0)
    checks["kafka"] = kafka_probe["reachable"] or kafka_probe["http_code"] is not None

    sn_probe = await probe_http(SERVICENOW_URL, timeout=2.0)
    checks["servicenow"] = sn_probe["reachable"]

    all_ready = all(checks.values())
    content = {"status": "ready" if all_ready else "unavailable", "checks": checks}
    if not all_ready:
        return JSONResponse(status_code=503, content=content)
    return content


@app.get("/api/summary")
async def summary() -> dict:
    tickets, servicenow_state = await fetch_servicenow_incident_count()
    return {
        "timestamp": utc_now(),
        "agent_status": "running",
        "cluster": "hub",
        "site": "edge-01",
        "open_incidents": tickets,
        "servicenow": servicenow_state,
    }


@app.get("/api/integrations")
async def integrations_endpoint(force_refresh: bool = False) -> dict:
    return await get_integrations(force_refresh=force_refresh)


@app.post("/api/demo/trigger")
async def trigger_demo(req: DemoTriggerRequest) -> dict:
    event = build_demo_event(req.scenario, req.site)
    try:
        offset = await asyncio.to_thread(publish_demo_event, event)
    except Exception as exc:
        logger.exception("Failed to publish demo event for scenario=%s", req.scenario)
        return JSONResponse(status_code=502, content={
            "timestamp": utc_now(),
            "status": "error",
            "error": str(exc),
            "scenario": req.scenario,
            "site": req.site,
        })

    scenario = event["labels"]["dark_noc_scenario"]
    return {
        "timestamp": utc_now(),
        "status": "queued",
        "scenario": scenario,
        "site": req.site,
        "topic": DEMO_TOPIC,
        "kafka_offset": offset,
        "event_message": event["message"],
    }


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict:
    msg = req.message.strip()
    if not msg:
        return {"reply": "Please enter a question.", "session_id": normalize_session_id(req.session_id)}

    session_id = normalize_session_id(req.session_id)
    if session_id not in chat_sessions and len(chat_sessions) >= MAX_CHAT_SESSIONS:
        oldest = next(iter(chat_sessions))
        del chat_sessions[oldest]
    history = chat_sessions.setdefault(session_id, [])

    summary_data = await summary()
    integrations_data = await get_integrations()

    prompt = build_chat_context(msg, summary_data, integrations_data, history)
    raw_reply, model_source = await call_model(prompt)
    reply = format_chat_reply(msg, raw_reply, summary_data, integrations_data)

    history.append({"role": "user", "content": msg})
    history.append({"role": "assistant", "content": reply})
    if len(history) > 20:
        del history[:-20]

    mcp_items = [i for i in integrations_data.get("integrations", []) if i.get("group") == "mcp"]

    return {
        "timestamp": utc_now(),
        "session_id": session_id,
        "reply": reply,
        "model_name": MODEL_NAME,
        "model_source": model_source,
        "open_incidents": summary_data.get("open_incidents"),
        "site": summary_data.get("site"),
        "integrations_up": integrations_data.get("up"),
        "integrations_total": integrations_data.get("total"),
        "mcp_status": mcp_items,
    }


# ── Entrypoint ────────────────────────────────────────────────────


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
