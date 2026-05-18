from langgraph.graph import END, START, StateGraph

from agent_service.models import GraphConfig, RemediationState
from agent_service.nodes import (
    analyze_node,
    context_node,
    decide_node,
    ingest_node,
    notify_node,
)


def build_graph(config: GraphConfig | None = None):
    graph = StateGraph(RemediationState)

    graph.add_node("ingest", ingest_node)
    graph.add_node("context", context_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("decide", decide_node)
    graph.add_node("notify", notify_node)

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "context")
    graph.add_edge("context", "analyze")
    graph.add_edge("analyze", "decide")
    graph.add_edge("decide", "notify")
    graph.add_edge("notify", END)

    return graph.compile()
