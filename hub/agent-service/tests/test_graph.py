from agent_service.graph import build_graph
from agent_service.models import RootCauseAnalysis


class TestGraphCompilation:
    def test_graph_compiles(self):
        graph = build_graph()
        assert graph is not None


class TestLinearFlow:
    def test_end_to_end_produces_expected_state(self):
        graph = build_graph()
        result = graph.invoke({"raw_event": "nginx CrashLoopBackOff in namespace prod"})

        assert result["raw_event"] == "nginx CrashLoopBackOff in namespace prod"
        assert len(result["context_snippets"]) > 0
        assert result["root_cause_analysis"] is not None
        assert isinstance(result["root_cause_analysis"], RootCauseAnalysis)
        assert isinstance(result["root_cause_analysis"].confidence, float)
        assert result["decision"] != ""
        assert len(result["notifications_sent"]) > 0
