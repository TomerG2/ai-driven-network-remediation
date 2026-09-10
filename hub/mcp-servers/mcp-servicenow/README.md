# MCP ServiceNow

MCP server wrapping the ServiceNow REST API for incident management in the AI-driven network remediation agent.

## Tools

| Tool | Description |
|---|---|
| `create_incident` | Open a new ServiceNow incident ticket |
| `update_incident` | Add work notes or change state on an existing incident |
| `get_incident` | Get incident details by ticket number |
| `resolve_incident` | Close an incident with resolution notes (tries PDI-specific `close_code` fallbacks when none is specified) |

## Environment Variables

| Variable | Required | Default |
|---|---|---|
| `SERVICENOW_URL` | No | `http://servicenow-mock...svc:8080` |
| `SERVICENOW_USERNAME` | No | `admin` |
| `SERVICENOW_PASSWORD` | No | `admin` |
| `SERVICENOW_CALLER_NAME` | No | `NOC Agent` |
| `MCP_TRANSPORT` | No | `sse` |
| `MCP_PORT` | No | `8000` |

The mock and real ServiceNow instances use the same API contract (flat JSON, `sysparm_query` lookups). Set `SERVICENOW_URL` to a real PDI or the local mock.

Authentication: prefer `SERVICENOW_API_KEY` (sends `x-sn-apikey` header for `noc_agent` machine users). When unset, falls back to Basic Auth via `SERVICENOW_USERNAME` / `SERVICENOW_PASSWORD` (mock and admin bootstrap).

## Running Locally

```bash
export SERVICENOW_URL=http://localhost:8080  # point at a servicenow-mock or real PDI
export SERVICENOW_USERNAME=admin
export SERVICENOW_PASSWORD=admin
export MCP_TRANSPORT=streamable-http
uv run uvicorn mcp_servicenow:app --host 0.0.0.0 --port 8000
```

## Tests

```bash
# Unit tests (mocks all HTTP calls)
uv sync --group dev && uv run pytest

# Integration tests run via: make integration-tests
```
