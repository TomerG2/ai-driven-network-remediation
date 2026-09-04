"""Unit tests for chat.py: prompt building must tolerate the null-heavy SLO shape
that compute_slo_metrics legitimately returns when there's no incident history yet.
"""

from chatbot_service.chat import build_chat_context, format_chat_reply
from chatbot_service.slo import compute_slo_metrics


def _integrations_data(slo: dict, business_impact: dict | None = None) -> dict:
    return {
        "up": 5,
        "total": 5,
        "integrations": [],
        "slo": slo,
        "incident_movie": [],
        "business_impact": business_impact or {},
    }


class TestBuildChatContextWithNoIncidentHistory:
    """Regression test for a real production crash: a quiet cluster with zero
    incident-audit records in the lookback window produces an SLO dict where several
    fields are explicitly `None` (not absent) — see compute_slo_metrics(records=[], ...).
    `dict.get(key, default)` does NOT fall back to `default` when `key` is present with
    value `None`, so any code formatting these fields as `{value:.0f}` would crash with
    `TypeError: unsupported format string passed to NoneType.__format__`.
    """

    def test_does_not_raise_with_zero_incident_records(self):
        slo = compute_slo_metrics(records=[], up_count=5, total_count=5)
        assert slo["auto_remediation_pct"] is None  # sanity check on the real producer

        integrations_data = _integrations_data(slo)

        prompt = build_chat_context("Any incidents?", {"site": "edge-site-01"}, integrations_data, [])

        assert "n/a" in prompt

    def test_format_chat_reply_does_not_raise_with_zero_incident_records(self):
        slo = compute_slo_metrics(records=[], up_count=5, total_count=5)
        integrations_data = _integrations_data(slo)

        reply = format_chat_reply("Any incidents?", "All quiet.", {"site": "edge-site-01"}, integrations_data)

        assert "No recent remediation events." in reply


class TestBuildChatContextWithIncidentHistory:
    def test_includes_slo_percentages(self):
        records = [
            {
                "remediation_success": True,
                "servicenow_ticket": "",
                "remediation_action": "restart",
                "aap_job_id": "1",
                "ai_confidence": 0.9,
                "total_duration_ms": 10000,
            }
        ]
        slo = compute_slo_metrics(records, up_count=5, total_count=5)
        integrations_data = _integrations_data(slo)

        prompt = build_chat_context("Status?", {"site": "edge-site-01"}, integrations_data, [])

        assert "Auto-remediation rate: 100%" in prompt
