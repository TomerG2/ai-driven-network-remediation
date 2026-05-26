"""Slack tool implementations."""

from datetime import datetime, timezone
from typing import Any

import httpx

from .config import SLACK_BASE_URL, SLACK_BOT_TOKEN, SLACK_NOC_CHANNEL, mcp

_SEVERITY_COLORS = {
    "critical": "#FF0000",
    "high": "#FF6600",
    "medium": "#FFAA00",
    "low": "#00AA00",
    "info": "#0066CC",
}


def _slack_post(endpoint: str, payload: dict) -> dict:
    """Post to Slack API with bot token auth."""
    with httpx.Client(timeout=10) as client:
        resp = client.post(
            f"{SLACK_BASE_URL}/{endpoint}",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    if not data.get("ok"):
        raise ValueError(f"Slack API error: {data.get('error', 'unknown')}")

    return data


@mcp.tool()
def send_alert(
    title: str,
    message: str,
    severity: str = "medium",
    edge_site: str = "edge-01",
    channel: str = SLACK_NOC_CHANNEL,
) -> dict:
    """
    Send a formatted NOC alert to Slack with color-coded severity.

    Args:
        title:     Alert title (e.g., "nginx OOMKilled on edge-01")
        message:   Alert body with details
        severity:  One of: critical, high, medium, low, info
        edge_site: Edge site identifier for context
        channel:   Slack channel (default: from SLACK_NOC_CHANNEL env)

    Returns:
        Dict with ts (message timestamp) for thread follow-ups
    """
    color = _SEVERITY_COLORS.get(severity.lower(), "#CCCCCC")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    payload = {
        "channel": channel,
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"NOC Alert: {title}"},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Severity:* {severity.upper()}"},
                            {"type": "mrkdwn", "text": f"*Site:* {edge_site}"},
                            {"type": "mrkdwn", "text": f"*Time:* {timestamp}"},
                            {"type": "mrkdwn", "text": "*Status:* AI Analyzing..."},
                        ],
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": message},
                    },
                ],
            }
        ],
    }

    try:
        data = _slack_post("chat.postMessage", payload)
        return {"success": True, "ts": data.get("ts"), "channel": data.get("channel")}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"Slack HTTP error: {e.response.status_code} – {e.response.text[:200]}"}
    except (httpx.HTTPError, ValueError) as e:
        return {"success": False, "error": f"Slack error: {e}"}


@mcp.tool()
def send_remediation(
    alert_title: str,
    action_taken: str,
    result: str,
    job_id: str = "",
    duration_seconds: float = 0,
    thread_ts: str = "",
    channel: str = SLACK_NOC_CHANNEL,
) -> dict:
    """
    Send a remediation summary to Slack (replies to alert thread if ts provided).

    Args:
        alert_title:      Original alert title for context
        action_taken:     What was done (e.g., "Restarted nginx deployment")
        result:           Outcome: "success", "failed", or "escalated"
        job_id:           AAP job ID if Ansible was used
        duration_seconds: How long remediation took
        thread_ts:        Slack timestamp to reply in thread (optional)
        channel:          Slack channel

    Returns:
        Dict with message timestamp
    """
    result_emoji = {"success": "OK", "failed": "FAIL", "escalated": "ESCALATED"}.get(result, "INFO")
    color = {"success": "#00AA00", "failed": "#FF0000", "escalated": "#FF6600"}.get(result, "#CCCCCC")

    fields = [
        {"type": "mrkdwn", "text": f"*Action:* {action_taken}"},
        {"type": "mrkdwn", "text": f"*Result:* {result_emoji}"},
    ]
    if job_id:
        fields.append({"type": "mrkdwn", "text": f"*AAP Job:* #{job_id}"})
    if duration_seconds > 0:
        fields.append({"type": "mrkdwn", "text": f"*Duration:* {duration_seconds:.1f}s"})

    payload: dict[str, Any] = {
        "channel": channel,
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"Remediation: {alert_title}"},
                    },
                    {"type": "section", "fields": fields},
                ],
            }
        ],
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts

    try:
        data = _slack_post("chat.postMessage", payload)
        return {"success": True, "ts": data.get("ts")}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"Slack HTTP error: {e.response.status_code} – {e.response.text[:200]}"}
    except (httpx.HTTPError, ValueError) as e:
        return {"success": False, "error": f"Slack error: {e}"}


@mcp.tool()
def send_message(
    text: str,
    channel: str = SLACK_NOC_CHANNEL,
) -> dict:
    """
    Send a plain text message to Slack.

    Args:
        text:    Message text (Slack mrkdwn formatting supported)
        channel: Target channel (default: from SLACK_NOC_CHANNEL env)

    Returns:
        Dict with message timestamp
    """
    try:
        data = _slack_post("chat.postMessage", {"channel": channel, "text": text})
        return {"success": True, "ts": data.get("ts")}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"Slack HTTP error: {e.response.status_code} – {e.response.text[:200]}"}
    except (httpx.HTTPError, ValueError) as e:
        return {"success": False, "error": f"Slack error: {e}"}


@mcp.tool()
def send_incident_ticket(
    ticket_number: str,
    title: str,
    description: str,
    priority: str,
    assigned_group: str = "NOC-Team",
    channel: str = SLACK_NOC_CHANNEL,
) -> dict:
    """
    Send a ServiceNow incident ticket notification to Slack.

    Args:
        ticket_number:  ServiceNow ticket number (e.g., INC0001234)
        title:          Incident short description
        description:    Full incident details
        priority:       1-Critical, 2-High, 3-Medium, 4-Low
        assigned_group: Assignment group
        channel:        Target channel

    Returns:
        Dict with message timestamp
    """
    priority_label = {
        "1": "Critical",
        "2": "High",
        "3": "Medium",
        "4": "Low",
    }.get(str(priority), "Unknown")

    payload = {
        "channel": channel,
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"ServiceNow Ticket: {ticket_number}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Title:* {title}"},
                    {"type": "mrkdwn", "text": f"*Priority:* {priority_label}"},
                    {"type": "mrkdwn", "text": f"*Assigned To:* {assigned_group}"},
                    {"type": "mrkdwn", "text": "*Status:* New — Pending Engineer Review"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Description:*\n{description[:500]}"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_This incident was created automatically by the NOC AI agent. A NOC engineer has been assigned._",
                },
            },
        ],
    }

    try:
        data = _slack_post("chat.postMessage", payload)
        return {"success": True, "ts": data.get("ts"), "ticket": ticket_number}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"Slack HTTP error: {e.response.status_code} – {e.response.text[:200]}"}
    except (httpx.HTTPError, ValueError) as e:
        return {"success": False, "error": f"Slack error: {e}"}
