from pathlib import Path
from typing import Optional

from langgraph.graph import END, START, StateGraph

from agent_service.models import GraphConfig, IncidentState
from agent_service.nodes import (
    analyze_node,
    escalate_node,
    normalize_node,
    notify_node,
    rag_retrieval_node,
    remediate_node,
)
from agent_service.nodes.decide import make_decide_node


def _route_after_decide(state: IncidentState) -> str:
    return state.decision


def build_graph(config: Optional[GraphConfig] = None):
    if config is None:
        config = GraphConfig()

    graph = StateGraph(IncidentState)

    graph.add_node("normalize", normalize_node)
    graph.add_node("rag_retrieval", rag_retrieval_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("decide", make_decide_node(config))
    graph.add_node("remediate", remediate_node)
    graph.add_node("escalate", escalate_node)
    graph.add_node("notify", notify_node)

    graph.add_edge(START, "normalize")
    graph.add_edge("normalize", "rag_retrieval")
    graph.add_edge("rag_retrieval", "analyze")
    graph.add_edge("analyze", "decide")
    graph.add_conditional_edges(
        "decide",
        _route_after_decide,
        {"remediate": "remediate", "escalate": "escalate"},
    )
    graph.add_edge("remediate", "notify")
    graph.add_edge("escalate", "notify")
    graph.add_edge("notify", END)

    return graph.compile()


def draw_graph(output: Path, config: Optional[GraphConfig] = None) -> None:
    compiled = build_graph(config)
    png_bytes = compiled.get_graph().draw_mermaid_png()
    output.write_bytes(png_bytes)
