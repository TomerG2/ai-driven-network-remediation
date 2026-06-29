from agent_service.models import IncidentState, LogEvent


def make_log_event(**overrides):
    defaults = dict(
        timestamp="2024-01-01T00:00:00Z",
        message="CrashLoopBackOff",
        level="error",
        namespace="prod",
        pod_name="nginx-abc123",
        container="nginx",
        edge_site_id="edge-1",
        kafka_offset=42,
        raw="raw log line",
    )
    defaults.update(overrides)
    return LogEvent(**defaults)


def make_state(**overrides):
    defaults = dict(raw_event="some raw event", log_event=make_log_event())
    defaults.update(overrides)
    return IncidentState(**defaults)
