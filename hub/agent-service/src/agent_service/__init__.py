import click

from agent_service.graph import build_graph


@click.command()
@click.option("--confidence", type=float, default=0.85, help="Override confidence for smoke testing.")
def main(confidence: float) -> None:
    graph = build_graph()
    result = graph.invoke({"raw_event": "nginx CrashLoopBackOff in namespace prod", "confidence_override": confidence})
    print(result)
