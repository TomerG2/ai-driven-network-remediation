from agent_service.graph import build_graph


def main() -> None:
    graph = build_graph()
    result = graph.invoke({"raw_event": "nginx CrashLoopBackOff in namespace prod"})
    print(result)
