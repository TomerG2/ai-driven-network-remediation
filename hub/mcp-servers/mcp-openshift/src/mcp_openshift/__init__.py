"""
OpenShift API MCP Server
=========================
MCP server exposing OpenShift operations as tools
for the AI-driven network remediation agent.

Tools:
    get_pods               - List pods in a namespace with status
    get_events             - Get recent OpenShift events (warnings)
    rollout_restart        - Trigger a rolling restart
    patch_deployment_memory - Patch deployment memory limits
    get_pod_logs           - Get recent logs from a specific pod

Transport: Configurable via MCP_TRANSPORT env var (default: sse)
"""

import json
import os
import subprocess
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

MCP_TRANSPORT: Literal["stdio", "sse", "streamable-http"] = os.environ.get(
    "MCP_TRANSPORT", "sse"
)  # type: ignore[assignment]
MCP_PORT = int(os.environ.get("MCP_PORT", "8001"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")

mcp = FastMCP(
    "noc-openshift",
    instructions=(
        "OpenShift cluster management tools for the NOC remediation agent. "
        "Use these tools to inspect pod status, get logs, patch deployments, "
        "and trigger restarts on the edge cluster."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=(MCP_TRANSPORT == "streamable-http"),
)

EDGE_KUBECONFIG = os.getenv("EDGE_KUBECONFIG", "/kubeconfig/edge-kubeconfig")
DEFAULT_NAMESPACE = os.getenv("DEFAULT_NAMESPACE", "dark-noc-edge")


@mcp.custom_route("/health", methods=["GET"])  # type: ignore
async def health(request: Any) -> JSONResponse:
    """Health check endpoint for Kubernetes probes."""
    return JSONResponse({"status": "OK"})


def _run_oc(args: list[str], kubeconfig: str = EDGE_KUBECONFIG) -> dict:
    """Run an oc/kubectl command and return parsed output."""
    cmd = ["kubectl", f"--kubeconfig={kubeconfig}"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Command timed out after 30s", "returncode": -1, "success": False}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1, "success": False}


@mcp.tool()
def get_pods(namespace: str = DEFAULT_NAMESPACE) -> dict:
    """
    List all pods in the specified namespace with their status.

    Args:
        namespace: Kubernetes namespace to query (default: dark-noc-edge)

    Returns:
        Dict with pods list: [{name, status, restart_count, node, ready}]
    """
    result = _run_oc(["get", "pods", "-n", namespace, "-o", "json"])

    if not result["success"]:
        return {"error": result["stderr"], "pods": []}

    try:
        data = json.loads(result["stdout"])
        pods = []
        for pod in data.get("items", []):
            name = pod["metadata"]["name"]
            phase = pod["status"].get("phase", "Unknown")
            containers = pod["status"].get("containerStatuses", [])
            restarts = sum(c.get("restartCount", 0) for c in containers)
            node = pod["spec"].get("nodeName", "unknown")
            pods.append(
                {
                    "name": name,
                    "status": phase,
                    "restart_count": restarts,
                    "node": node,
                    "ready": all(c.get("ready", False) for c in containers),
                }
            )
        return {"namespace": namespace, "pods": pods, "count": len(pods)}
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse pod output: {e}", "pods": []}


@mcp.tool()
def get_events(namespace: str = DEFAULT_NAMESPACE, limit: int = 20) -> dict:
    """
    Get recent Kubernetes events (especially warnings) from a namespace.

    Args:
        namespace: Kubernetes namespace (default: dark-noc-edge)
        limit:     Maximum number of events to return (default: 20)

    Returns:
        Dict with events list: [{type, reason, message, object, time, count}]
    """
    result = _run_oc(["get", "events", "-n", namespace, "--sort-by=lastTimestamp", "-o", "json"])

    if not result["success"]:
        return {"error": result["stderr"], "events": []}

    try:
        data = json.loads(result["stdout"])
        events = []
        for evt in data.get("items", [])[-limit:]:
            events.append(
                {
                    "type": evt.get("type", "Normal"),
                    "reason": evt.get("reason", ""),
                    "message": evt.get("message", ""),
                    "object": f"{evt['involvedObject']['kind']}/{evt['involvedObject']['name']}",
                    "time": evt.get("lastTimestamp", ""),
                    "count": evt.get("count", 1),
                }
            )
        events.sort(key=lambda e: (0 if e["type"] == "Warning" else 1, e["time"]))
        return {"namespace": namespace, "events": events}
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse events: {e}", "events": []}


@mcp.tool()
def rollout_restart(deployment: str, namespace: str = DEFAULT_NAMESPACE) -> dict:
    """
    Trigger a rolling restart of a deployment (safe — no downtime if replicas > 1).

    Args:
        deployment: Name of the Deployment to restart
        namespace:  Namespace of the deployment (default: dark-noc-edge)

    Returns:
        Dict with restart status and message
    """
    result = _run_oc(["rollout", "restart", f"deployment/{deployment}", "-n", namespace])

    if not result["success"]:
        return {"success": False, "error": result["stderr"]}

    wait_result = _run_oc(
        [
            "rollout",
            "status",
            f"deployment/{deployment}",
            "-n",
            namespace,
            "--timeout=90s",
        ]
    )

    return {
        "success": wait_result["success"],
        "deployment": deployment,
        "namespace": namespace,
        "message": wait_result["stdout"].strip() or wait_result["stderr"].strip(),
    }


@mcp.tool()
def patch_deployment_memory(
    deployment: str,
    memory_limit: str,
    namespace: str = DEFAULT_NAMESPACE,
) -> dict:
    """
    Patch a deployment's memory limit (useful for OOMKilled remediation).

    Args:
        deployment:   Deployment name
        memory_limit: New memory limit (e.g., "512Mi", "1Gi")
        namespace:    Namespace (default: dark-noc-edge)

    Returns:
        Dict with patch status
    """
    patch = json.dumps(
        [
            {
                "op": "replace",
                "path": "/spec/template/spec/containers/0/resources/limits/memory",
                "value": memory_limit,
            }
        ]
    )

    result = _run_oc(
        [
            "patch",
            "deployment",
            deployment,
            "-n",
            namespace,
            "--type=json",
            f"-p={patch}",
        ]
    )

    return {
        "success": result["success"],
        "deployment": deployment,
        "new_memory_limit": memory_limit,
        "message": result["stdout"] or result["stderr"],
    }


@mcp.tool()
def get_pod_logs(
    pod_name: str,
    namespace: str = DEFAULT_NAMESPACE,
    container: str = "",
    tail_lines: int = 50,
) -> dict:
    """
    Get recent logs from a specific pod.

    Args:
        pod_name:   Pod name
        namespace:  Namespace (default: dark-noc-edge)
        container:  Container name (optional, for multi-container pods)
        tail_lines: Number of log lines to return (default: 50)

    Returns:
        Dict with logs string
    """
    args = ["logs", pod_name, "-n", namespace, f"--tail={tail_lines}"]
    if container:
        args += ["-c", container]

    result = _run_oc(args)
    return {
        "pod": pod_name,
        "namespace": namespace,
        "logs": result["stdout"],
        "success": result["success"],
        "error": result["stderr"] if not result["success"] else None,
    }


def main() -> None:
    """Run the OpenShift MCP server."""
    mcp.run(transport=MCP_TRANSPORT)


app = mcp.streamable_http_app()
