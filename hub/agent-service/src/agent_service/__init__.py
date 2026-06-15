from pathlib import Path

import click

from agent_service.graph import build_graph, draw_graph


def _format_result(result: dict) -> str:
    rca = result.get("root_cause_analysis")
    remediation = result.get("remediation_result")

    lines = [
        f"incident_id: {result.get('incident_id', '')}",
        f"next_action: {result.get('decision', '')}",
    ]

    if rca:
        lines.append(f"rca: {rca.failure_type} (confidence={rca.confidence}, severity={rca.estimated_severity})")
        lines.append(f"  summary: {rca.summary}")

    if remediation:
        lines.append(f"remediation: {remediation.action_taken} (success={remediation.success})")
        if remediation.generated_playbook_name:
            lines.append(f"  playbook: {remediation.generated_playbook_name}")

    return "\n".join(lines)


@click.command()
@click.option("--confidence", type=float, default=0.85, help="Override confidence for smoke testing.")
@click.option("--failure-type", type=str, default=None, help="Override failure_type for smoke testing.")
@click.option(
    "--draw", "draw_path", type=click.Path(path_type=Path), default=None, help="Draw the graph to a PNG file and exit."
)
def main(confidence: float, failure_type: str | None, draw_path: Path | None) -> None:
    if draw_path is not None:
        draw_graph(draw_path)
        click.echo(f"Graph saved to {draw_path}")
        return
    graph = build_graph()
    invoke_input: dict = {"raw_event": "nginx CrashLoopBackOff in namespace prod", "confidence_override": confidence}
    if failure_type is not None:
        invoke_input["failure_type_override"] = failure_type
    result = graph.invoke(invoke_input)
    click.echo(_format_result(result))
