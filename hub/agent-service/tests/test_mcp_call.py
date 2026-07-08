import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from agent_service.utils import mcp_call


def _sse_response(data: dict, status=200) -> httpx.Response:
    """Build an SSE-formatted httpx.Response wrapping a JSON-RPC result."""
    body = f"data: {json.dumps(data)}\n\n"
    return httpx.Response(
        status,
        content=body.encode(),
        headers={"content-type": "text/event-stream"},
        request=httpx.Request("POST", "http://test/mcp"),
    )


def _json_response(data: dict, status=200) -> httpx.Response:
    return httpx.Response(
        status,
        json=data,
        request=httpx.Request("POST", "http://test/mcp"),
    )


def _ok_result(payload: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": json.dumps(payload)}],
        },
    }


def _error_result(message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": message}],
            "isError": True,
        },
    }


class TestMcpCallSuccess:
    async def test_returns_parsed_json_from_sse(self):
        mock_client = AsyncMock()
        mock_client.post.return_value = _sse_response(_ok_result({"number": "INC001"}))

        with patch("agent_service.utils._get_mcp_client", return_value=mock_client):
            result = await mcp_call("servicenow", "create_incident", {"desc": "test"})

        assert result == {"number": "INC001"}

    async def test_returns_parsed_json_from_plain_json(self):
        mock_client = AsyncMock()
        mock_client.post.return_value = _json_response(_ok_result({"job_id": 42}))

        with patch("agent_service.utils._get_mcp_client", return_value=mock_client):
            result = await mcp_call("aap", "launch_job", {"template": "x"})

        assert result == {"job_id": 42}

    async def test_posts_correct_jsonrpc_payload(self):
        mock_client = AsyncMock()
        mock_client.post.return_value = _json_response(_ok_result({"ok": True}))

        with patch("agent_service.utils._get_mcp_client", return_value=mock_client):
            await mcp_call("aap", "launch_job", {"template": "restart"})

        mock_client.post.assert_awaited_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[0][0] == "/mcp"
        body = call_kwargs[1]["json"]
        assert body["jsonrpc"] == "2.0"
        assert body["method"] == "tools/call"
        assert body["params"]["name"] == "launch_job"
        assert body["params"]["arguments"] == {"template": "restart"}

    async def test_defaults_args_to_empty_dict(self):
        mock_client = AsyncMock()
        mock_client.post.return_value = _json_response(_ok_result({"ok": True}))

        with patch("agent_service.utils._get_mcp_client", return_value=mock_client):
            await mcp_call("aap", "list_templates")

        body = mock_client.post.call_args[1]["json"]
        assert body["params"]["arguments"] == {}


class TestMcpCallError:
    async def test_mcp_error_flag_returns_error_dict(self):
        mock_client = AsyncMock()
        mock_client.post.return_value = _json_response(_error_result("incident creation failed"))

        with patch("agent_service.utils._get_mcp_client", return_value=mock_client):
            result = await mcp_call("servicenow", "create_incident", {})

        assert result == {"success": False, "error": "incident creation failed"}

    async def test_http_error_propagates(self):
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        with patch("agent_service.utils._get_mcp_client", return_value=mock_client):
            with pytest.raises(httpx.ConnectError):
                await mcp_call("servicenow", "create_incident", {})

    async def test_unknown_service_raises_value_error(self):
        with pytest.raises(ValueError, match="unknown MCP service"):
            await mcp_call("nonexistent", "some_tool", {})


class TestMcpCallUnparseable:
    async def test_no_result_key_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post.return_value = _json_response({"jsonrpc": "2.0", "id": 1})

        with patch("agent_service.utils._get_mcp_client", return_value=mock_client):
            result = await mcp_call("aap", "launch_job", {})

        assert result["success"] is False
        assert "no result" in result["error"].lower()

    async def test_empty_content_returns_error(self):
        resp_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": []},
        }
        mock_client = AsyncMock()
        mock_client.post.return_value = _json_response(resp_data)

        with patch("agent_service.utils._get_mcp_client", return_value=mock_client):
            result = await mcp_call("aap", "launch_job", {})

        assert result["success"] is False
        assert "empty" in result["error"].lower()

    async def test_non_json_text_returns_error(self):
        resp_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "not valid json {"}],
            },
        }
        mock_client = AsyncMock()
        mock_client.post.return_value = _json_response(resp_data)

        with patch("agent_service.utils._get_mcp_client", return_value=mock_client):
            result = await mcp_call("aap", "launch_job", {})

        assert result["success"] is False
        assert "unparseable" in result["error"].lower()
