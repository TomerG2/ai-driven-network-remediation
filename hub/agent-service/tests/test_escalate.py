from unittest.mock import patch

from agent_service.models import IncidentState, RootCauseAnalysis
from agent_service.nodes.escalate import escalate_node
from helpers import make_log_event, make_state


def _stub_rca(**overrides):
    defaults = dict(
        failure_type="CrashLoopBackOff",
        confidence=0.5,
        summary="pod is crash-looping",
        evidence=["restart count > 5"],
        recommended_actions=["restart-pod"],
        estimated_severity="high",
        runbook_reference="runbook-001",
    )
    defaults.update(overrides)
    return RootCauseAnalysis(**defaults)


async def _fake_invoke(tool_name, kwargs):
    if tool_name == "create_incident":
        return {"success": True, "number": "INC0012345"}
    return {}


class TestEscalateHappyPath:
    async def test_creates_servicenow_ticket(self):
        state = make_state(root_cause_analysis=_stub_rca())
        with patch("agent_service.nodes.escalate._invoke_tool", _fake_invoke):
            result = await escalate_node(state)

        assert result["servicenow_ticket"] == "INC0012345"

    async def test_does_not_set_decision(self):
        state = make_state(root_cause_analysis=_stub_rca())
        with patch("agent_service.nodes.escalate._invoke_tool", _fake_invoke):
            result = await escalate_node(state)

        assert "decision" not in result

    async def test_calls_create_incident_with_correct_short_description(self):
        state = make_state(root_cause_analysis=_stub_rca())
        captured = {}

        async def _capture_invoke(tool_name, kwargs):
            captured.update({"tool_name": tool_name, "kwargs": kwargs})
            return {"success": True, "number": "INC0012345"}

        with patch("agent_service.nodes.escalate._invoke_tool", _capture_invoke):
            await escalate_node(state)

        assert captured["tool_name"] == "create_incident"
        expected_desc = "[AI-NOC] CrashLoopBackOff – nginx-abc123 in prod (edge-1)"
        assert captured["kwargs"]["short_description"] == expected_desc

    async def test_description_contains_rca_context(self):
        state = make_state(root_cause_analysis=_stub_rca())
        captured = {}

        async def _capture_invoke(tool_name, kwargs):
            captured.update({"tool_name": tool_name, "kwargs": kwargs})
            return {"success": True, "number": "INC0012345"}

        with patch("agent_service.nodes.escalate._invoke_tool", _capture_invoke):
            await escalate_node(state)

        desc = captured["kwargs"]["description"]
        assert "CrashLoopBackOff" in desc
        assert "pod is crash-looping" in desc
        assert "restart count > 5" in desc
        assert "restart-pod" in desc
        assert "CrashLoopBackOff" in desc


class TestPriorityMapping:
    async def _get_priority(self, severity):
        state = make_state(root_cause_analysis=_stub_rca(estimated_severity=severity))
        captured = {}

        async def _capture_invoke(tool_name, kwargs):
            captured.update({"kwargs": kwargs})
            return {"success": True, "number": "INC0099"}

        with patch("agent_service.nodes.escalate._invoke_tool", _capture_invoke):
            await escalate_node(state)

        return captured["kwargs"]["priority"]

    async def test_critical_maps_to_1(self):
        assert await self._get_priority("critical") == 1

    async def test_high_maps_to_2(self):
        assert await self._get_priority("high") == 2

    async def test_medium_maps_to_3(self):
        assert await self._get_priority("medium") == 3

    async def test_low_maps_to_4(self):
        assert await self._get_priority("low") == 4
