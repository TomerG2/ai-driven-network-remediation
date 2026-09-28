"""Analyze node — LLM-powered root cause analysis for ML-detected RAN anomalies."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from ran_rca_service.config import get_llm
from ran_rca_service.models import RCAState

_SYSTEM_PROMPT = """\
You are a senior telco radio engineer specialising in RAN (Radio Access Network) root cause analysis.
You have deep expertise in 5G KPIs including RSRP, BLER, MCS, SNR, PRB utilization, throughput, and protocol behavior.

An ML-based anomaly detection model (Mantis AD on TelecomTS) has flagged a KPI window as anomalous.
Analyze the anomaly context and any vendor documentation, then produce a structured JSON diagnosis.

When recommending fixes, reference specific vendor documentation sections from the provided context where available.

Classify the root cause as exactly one category:
- antenna_misalignment: antenna tilt, azimuth, or alignment is degrading coverage.
- interference: noise, SINR degradation, or RF interference is the primary cause.
- scheduler_degradation: radio scheduling or resource-allocation behavior is degrading service.
- congestion: excess active-user demand is causing a transient load imbalance.
- capacity_exhaustion: sustained PRB or resource capacity is exhausted and must be expanded.
- cell_failure: a cell, radio, or supporting component has failed or is unavailable.
- unknown: the evidence does not support one of the other categories.

Respond ONLY with valid JSON matching the provided schema:
{
  "root_cause_category": "<one of the defined categories>",
  "root_cause": "<concise root cause explanation referencing 5G KPIs>",
  "recommended_fix": "<specific remediation steps referencing vendor doc sections>"
}"""

_MAX_CONTEXT_CHARS = 5000

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause_category": {
            "type": "string",
            "enum": [
                "antenna_misalignment",
                "interference",
                "scheduler_degradation",
                "congestion",
                "capacity_exhaustion",
                "cell_failure",
                "unknown",
            ],
        },
        "root_cause": {"type": "string"},
        "recommended_fix": {"type": "string"},
    },
    "required": ["root_cause_category", "root_cause", "recommended_fix"],
}


async def analyze_node(state: RCAState) -> dict:
    context = "\n---\n".join(state.context_snippets or [])[:_MAX_CONTEXT_CHARS]

    kpi_summary = state.kpi_summary()
    user_content = (
        f"Incident: {state.incident_id}\n"
        f"Zone: {state.zone}, Application: {state.application}\n"
        f"AD Label: {state.ad_label}, Confidence: {state.ad_confidence:.3f}\n"
        f"KPI Window: {len(state.kpi_window)} timesteps x 18 channels (TelecomTS 5G lab trace)"
    )
    if kpi_summary:
        user_content += f"\n\nPer-channel KPI summary (sorted by variability):\n{kpi_summary}"
    if context:
        user_content += f"\n\nVendor documentation context:\n{context}"

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    try:
        response = await get_llm().ainvoke(
            messages,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "RCAAnalysis", "schema": _RESPONSE_SCHEMA},
            },
        )
        if not isinstance(response.content, str):
            raise TypeError("LLM response content must be a JSON string")
        parsed = json.loads(response.content)
        return {
            "root_cause_category": parsed.get("root_cause_category", "unknown"),
            "root_cause": parsed.get("root_cause", ""),
            "recommended_fix": parsed.get("recommended_fix", ""),
        }
    except Exception:  # noqa: BLE001 - graceful degradation must handle provider and parsing errors.
        logger.exception("LLM analysis failed — anomaly will flow through unenriched")
        return {"root_cause_category": "unknown", "root_cause": "", "recommended_fix": ""}
