import json

import httpx

from agent_service.config import HTTP_TIMEOUT_SECONDS, MCP_URLS, get_http_client

_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}

_mcp_clients: dict[str, httpx.AsyncClient] = {}


def _get_mcp_client(service: str) -> httpx.AsyncClient:
    if service not in MCP_URLS:
        raise ValueError(f"unknown MCP service: {service!r}")
    if service not in _mcp_clients:
        _mcp_clients[service] = httpx.AsyncClient(
            base_url=MCP_URLS[service],
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    return _mcp_clients[service]


def _parse_sse_json(response: httpx.Response) -> dict:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        for line in response.text.splitlines():
            if line.startswith("data:"):
                data = line.removeprefix("data:").strip()
                if data:
                    return json.loads(data)
        raise ValueError(f"no data line in SSE response: {response.text[:200]}")
    return response.json()


async def mcp_call(service: str, tool_name: str, args: dict | None = None) -> dict:
    """Call an MCP tool directly via JSON-RPC, bypassing LlamaStack."""
    client = _get_mcp_client(service)
    resp = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args or {},
            },
        },
        headers=_MCP_HEADERS,
    )
    resp.raise_for_status()
    data = _parse_sse_json(resp)

    if "result" not in data:
        return {"success": False, "error": "no result in MCP response"}

    result = data["result"]
    content = result.get("content", [])
    if not content:
        return {"success": False, "error": "empty content in MCP response"}

    text = content[0].get("text", "")
    if result.get("isError"):
        return {"success": False, "error": text}

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"success": False, "error": f"unparseable response: {text[:200]}"}


async def invoke_tool(tool_name: str, kwargs: dict) -> dict:
    """Call an MCP tool via LlamaStack's /v1/tool-runtime/invoke endpoint."""
    resp = await get_http_client().post(
        "/v1/tool-runtime/invoke",
        json={"tool_name": tool_name, "kwargs": kwargs},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error_message"):
        return {"success": False, "error": data["error_message"]}
    content = data.get("content", "")
    try:
        if isinstance(content, str):
            return json.loads(content) if content else {}
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return json.loads(item["text"])
    except json.JSONDecodeError:
        return {"success": False, "error": f"unparseable response: {str(content)[:200]}"}
    return {}
