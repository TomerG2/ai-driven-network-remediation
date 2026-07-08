# Tracer: `mcp_call` foundation + escalate node migration -- end-to-end

**Parent:** [#94](https://github.com/rh-ai-quickstart/ai-driven-network-remediation/issues/94)
**Type:** AFK
**Blocked by:** None - can start immediately

## What to build

Introduce a new `mcp_call(service, tool_name, args)` function in `utils.py` that calls MCP servers directly via JSON-RPC (`tools/call` on the `/mcp` endpoint), bypassing the LlamaStack `/v1/tool-runtime/invoke` hop. The pattern is already validated in the integration test helper (`hub/integration-tests/tests/mcp_servers/conftest.py`).

Add two new env vars to `config.py`:
- `MCP_AAP_URL` (default `http://mcp-noc-aap:8000`)
- `MCP_SERVICENOW_URL` (default `http://mcp-noc-servicenow:8000`)

Migrate the escalate node to use `mcp_call` instead of `invoke_tool`. Escalate is the simplest node (single `create_incident` call targeting `mcp-noc-servicenow`), making it ideal for proving the pattern end-to-end.

## Acceptance criteria

- [ ] `MCP_AAP_URL` and `MCP_SERVICENOW_URL` env vars added to `config.py` with documented defaults
- [ ] `mcp_call(service, tool_name, args)` implemented in `utils.py` — JSON-RPC POST to `/mcp`, SSE/JSON response parsing, content block extraction
- [ ] Escalate node calls `mcp_call("servicenow", "create_incident", ...)` instead of `invoke_tool("create_incident", ...)`
- [ ] Existing escalate tests updated and passing
- [ ] Unit tests for `mcp_call` covering success, error, and unparseable-response paths
