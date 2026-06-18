from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_service.models import IncidentState, LogEvent


def _make_log_event(**overrides):
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


def _make_state(**overrides):
    defaults = dict(raw_event="some raw event", log_event=_make_log_event())
    defaults.update(overrides)
    return IncidentState(**defaults)


class TestRagQueryConstruction:
    @pytest.mark.asyncio
    async def test_query_built_from_log_event_fields(self):
        mock_client = MagicMock()
        mock_client.vector_stores.list = AsyncMock(return_value=MagicMock(data=[]))
        mock_client.vector_stores.search = AsyncMock(
            return_value=MagicMock(data=[])
        )

        with patch("agent_service.nodes.rag_retrieval._client", mock_client), \
             patch("agent_service.nodes.rag_retrieval._vector_store_id", "vs-123"):
            from agent_service.nodes.rag_retrieval import rag_retrieval_node

            state = _make_state()
            result = await rag_retrieval_node(state)

        assert "CrashLoopBackOff" in result["rag_query_used"]
        assert "namespace=prod" in result["rag_query_used"]
        assert "pod=nginx-abc123" in result["rag_query_used"]


class TestRagSuccessfulSearch:
    @pytest.mark.asyncio
    async def test_returns_snippets_from_search_results(self):
        mock_content_1 = MagicMock(text="Runbook: restart the pod")
        mock_content_2 = MagicMock(text="Runbook: check memory limits")
        mock_item_1 = MagicMock(content=[mock_content_1])
        mock_item_2 = MagicMock(content=[mock_content_2])
        mock_response = MagicMock(data=[mock_item_1, mock_item_2])

        mock_client = MagicMock()
        mock_client.vector_stores.search = AsyncMock(return_value=mock_response)

        with patch("agent_service.nodes.rag_retrieval._client", mock_client), \
             patch("agent_service.nodes.rag_retrieval._vector_store_id", "vs-123"):
            from agent_service.nodes.rag_retrieval import rag_retrieval_node

            result = await rag_retrieval_node(_make_state())

        assert result["context_snippets"] == [
            "Runbook: restart the pod",
            "Runbook: check memory limits",
        ]
        assert result["rag_query_used"] != ""


class TestRagEmptyResults:
    @pytest.mark.asyncio
    async def test_empty_search_returns_empty_snippets(self):
        mock_client = MagicMock()
        mock_client.vector_stores.search = AsyncMock(
            return_value=MagicMock(data=[])
        )

        with patch("agent_service.nodes.rag_retrieval._client", mock_client), \
             patch("agent_service.nodes.rag_retrieval._vector_store_id", "vs-123"):
            from agent_service.nodes.rag_retrieval import rag_retrieval_node

            result = await rag_retrieval_node(_make_state())

        assert result["context_snippets"] == []
        assert result["rag_query_used"] != ""


class TestRagVectorStoreLookup:
    @pytest.mark.asyncio
    async def test_looks_up_vector_store_by_name_on_first_call(self):
        mock_vs = MagicMock()
        mock_vs.id = "vs-found"
        mock_vs.name = "noc_runbooks"
        mock_client = MagicMock()
        mock_client.vector_stores.list = AsyncMock(
            return_value=MagicMock(data=[mock_vs])
        )
        mock_client.vector_stores.search = AsyncMock(
            return_value=MagicMock(data=[])
        )

        with patch("agent_service.nodes.rag_retrieval._client", mock_client), \
             patch("agent_service.nodes.rag_retrieval._vector_store_id", None):
            from agent_service.nodes.rag_retrieval import rag_retrieval_node

            await rag_retrieval_node(_make_state())

        mock_client.vector_stores.list.assert_awaited_once()
        mock_client.vector_stores.search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_vector_store_not_found_returns_empty(self):
        mock_client = MagicMock()
        mock_client.vector_stores.list = AsyncMock(
            return_value=MagicMock(data=[])
        )

        with patch("agent_service.nodes.rag_retrieval._client", mock_client), \
             patch("agent_service.nodes.rag_retrieval._vector_store_id", None):
            from agent_service.nodes.rag_retrieval import rag_retrieval_node

            result = await rag_retrieval_node(_make_state())

        assert result["context_snippets"] == []
        assert result["rag_query_used"] != ""


class TestRagErrorHandling:
    @pytest.mark.asyncio
    async def test_client_error_returns_empty_context_no_raise(self):
        mock_client = MagicMock()
        mock_client.vector_stores.search = AsyncMock(
            side_effect=ConnectionError("LlamaStack unreachable")
        )

        with patch("agent_service.nodes.rag_retrieval._client", mock_client), \
             patch("agent_service.nodes.rag_retrieval._vector_store_id", "vs-123"):
            from agent_service.nodes.rag_retrieval import rag_retrieval_node

            result = await rag_retrieval_node(_make_state())

        assert result["context_snippets"] == []
        assert result["rag_query_used"] != ""

    @pytest.mark.asyncio
    async def test_vector_store_lookup_error_returns_empty_context(self):
        mock_client = MagicMock()
        mock_client.vector_stores.list = AsyncMock(
            side_effect=ConnectionError("LlamaStack unreachable")
        )

        with patch("agent_service.nodes.rag_retrieval._client", mock_client), \
             patch("agent_service.nodes.rag_retrieval._vector_store_id", None):
            from agent_service.nodes.rag_retrieval import rag_retrieval_node

            result = await rag_retrieval_node(_make_state())

        assert result["context_snippets"] == []
        assert result["rag_query_used"] != ""
