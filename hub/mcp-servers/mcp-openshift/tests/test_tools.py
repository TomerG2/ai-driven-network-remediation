"""Unit tests for mcp_openshift tools (subprocess is always mocked)."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from mcp_openshift.tools import (
    _run_kubectl,
    get_events,
    get_namespaces,
    get_pod_logs,
    get_pods,
    patch_deployment_memory,
    rollout_restart,
)

SAMPLE_PODS_JSON = json.dumps(
    {
        "items": [
            {
                "metadata": {"name": "edge-worker-abc12"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {"restartCount": 0, "ready": True},
                    ],
                },
                "spec": {"nodeName": "edge-node-1"},
            },
            {
                "metadata": {"name": "edge-worker-def34"},
                "status": {
                    "phase": "CrashLoopBackOff",
                    "containerStatuses": [
                        {"restartCount": 5, "ready": False},
                    ],
                },
                "spec": {"nodeName": "edge-node-2"},
            },
        ]
    }
)

SAMPLE_EVENTS_JSON = json.dumps(
    {
        "items": [
            {
                "type": "Warning",
                "reason": "BackOff",
                "message": "Back-off restarting failed container",
                "involvedObject": {"kind": "Pod", "name": "edge-worker-def34"},
                "lastTimestamp": "2026-05-26T10:00:00Z",
                "count": 3,
            },
            {
                "type": "Normal",
                "reason": "Scheduled",
                "message": "Successfully assigned pod",
                "involvedObject": {"kind": "Pod", "name": "edge-worker-abc12"},
                "lastTimestamp": "2026-05-26T09:00:00Z",
                "count": 1,
            },
        ]
    }
)


class TestRunKubectl:
    """Tests for the _run_kubectl helper."""

    @patch("mcp_openshift.tools.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="ok", stderr="", returncode=0
        )
        result = _run_kubectl(["get", "pods"], kubeconfig="/fake/config")
        assert result["success"] is True
        assert result["stdout"] == "ok"
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "kubectl"
        assert "--kubeconfig=/fake/config" in cmd

    @patch("mcp_openshift.tools.subprocess.run")
    def test_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="", stderr="not found", returncode=1
        )
        result = _run_kubectl(["get", "pods"])
        assert result["success"] is False
        assert result["stderr"] == "not found"

    @patch("mcp_openshift.tools.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=30)
        result = _run_kubectl(["get", "pods"], timeout=30)
        assert result["success"] is False
        assert "timed out" in result["stderr"]

    @patch("mcp_openshift.tools.subprocess.run")
    def test_unexpected_error(self, mock_run):
        mock_run.side_effect = OSError("No such file or directory")
        result = _run_kubectl(["get", "pods"])
        assert result["success"] is False
        assert "No such file" in result["stderr"]

    @patch("mcp_openshift.tools.subprocess.run")
    def test_custom_timeout(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        _run_kubectl(["rollout", "status"], timeout=120)
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["timeout"] == 120


SAMPLE_NAMESPACES_JSON = json.dumps(
    {
        "items": [
            {
                "metadata": {"name": "dark-noc-edge"},
                "status": {"phase": "Active"},
            },
            {
                "metadata": {"name": "default"},
                "status": {"phase": "Active"},
            },
            {
                "metadata": {"name": "kube-system"},
                "status": {"phase": "Active"},
            },
        ]
    }
)


class TestGetNamespaces:
    """Tests for the get_namespaces tool."""

    @patch("mcp_openshift.tools._run_kubectl")
    def test_success(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": SAMPLE_NAMESPACES_JSON,
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = get_namespaces()
        assert result["count"] == 3
        names = [ns["name"] for ns in result["namespaces"]]
        assert "dark-noc-edge" in names
        assert all(ns["status"] == "Active" for ns in result["namespaces"])

    @patch("mcp_openshift.tools._run_kubectl")
    def test_kubectl_failure(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "",
            "stderr": "forbidden",
            "returncode": 1,
            "success": False,
        }
        result = get_namespaces()
        assert result["error"] == "forbidden"
        assert result["namespaces"] == []

    @patch("mcp_openshift.tools._run_kubectl")
    def test_malformed_json(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "not json",
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = get_namespaces()
        assert "Failed to parse" in result["error"]

    @patch("mcp_openshift.tools._run_kubectl")
    def test_empty(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": json.dumps({"items": []}),
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = get_namespaces()
        assert result["count"] == 0
        assert result["namespaces"] == []


class TestGetPods:
    """Tests for the get_pods tool."""

    @patch("mcp_openshift.tools._run_kubectl")
    def test_success(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": SAMPLE_PODS_JSON,
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = get_pods(namespace="dark-noc-edge")
        assert result["count"] == 2
        assert result["pods"][0]["name"] == "edge-worker-abc12"
        assert result["pods"][0]["ready"] is True
        assert result["pods"][1]["restart_count"] == 5
        assert result["pods"][1]["ready"] is False

    @patch("mcp_openshift.tools._run_kubectl")
    def test_kubectl_failure(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "",
            "stderr": "connection refused",
            "returncode": 1,
            "success": False,
        }
        result = get_pods()
        assert result["error"] == "connection refused"
        assert result["pods"] == []

    @patch("mcp_openshift.tools._run_kubectl")
    def test_malformed_json(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "not json",
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = get_pods()
        assert "Failed to parse" in result["error"]

    @patch("mcp_openshift.tools._run_kubectl")
    def test_empty_items(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": json.dumps({"items": []}),
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = get_pods()
        assert result["count"] == 0
        assert result["pods"] == []


class TestGetEvents:
    """Tests for the get_events tool."""

    @patch("mcp_openshift.tools._run_kubectl")
    def test_success(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": SAMPLE_EVENTS_JSON,
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = get_events(namespace="dark-noc-edge")
        assert len(result["events"]) == 2
        assert result["events"][0]["type"] == "Warning"

    @patch("mcp_openshift.tools._run_kubectl")
    def test_kubectl_failure(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "",
            "stderr": "forbidden",
            "returncode": 1,
            "success": False,
        }
        result = get_events()
        assert result["error"] == "forbidden"
        assert result["events"] == []

    @patch("mcp_openshift.tools._run_kubectl")
    def test_limit(self, mock_kubectl):
        items = [
            {
                "type": "Normal",
                "reason": f"Event{i}",
                "message": f"msg {i}",
                "involvedObject": {"kind": "Pod", "name": f"pod-{i}"},
                "lastTimestamp": f"2026-05-26T10:{i:02d}:00Z",
                "count": 1,
            }
            for i in range(10)
        ]
        mock_kubectl.return_value = {
            "stdout": json.dumps({"items": items}),
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = get_events(limit=3)
        assert len(result["events"]) == 3

    @patch("mcp_openshift.tools._run_kubectl")
    def test_null_timestamps(self, mock_kubectl):
        items = [
            {
                "type": "Warning",
                "reason": "BackOff",
                "message": "Back-off restarting",
                "involvedObject": {"kind": "Pod", "name": "pod-1"},
                "lastTimestamp": None,
                "eventTime": "2026-05-28T10:00:00Z",
                "count": 2,
            },
            {
                "type": "Normal",
                "reason": "Scheduled",
                "message": "Assigned pod",
                "involvedObject": {"kind": "Pod", "name": "pod-2"},
                "lastTimestamp": None,
                "count": 1,
            },
        ]
        mock_kubectl.return_value = {
            "stdout": json.dumps({"items": items}),
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = get_events()
        assert len(result["events"]) == 2
        assert result["events"][0]["type"] == "Warning"
        assert result["events"][0]["time"] == "2026-05-28T10:00:00Z"
        assert result["events"][1]["time"] == ""


class TestRolloutRestart:
    """Tests for the rollout_restart tool."""

    @patch("mcp_openshift.tools._run_kubectl")
    def test_success(self, mock_kubectl):
        mock_kubectl.side_effect = [
            {"stdout": "deployment.apps/edge-worker restarted", "stderr": "", "returncode": 0, "success": True},
            {"stdout": "deployment edge-worker successfully rolled out", "stderr": "", "returncode": 0, "success": True},
        ]
        result = rollout_restart(deployment="edge-worker", namespace="dark-noc-edge")
        assert result["success"] is True
        assert result["deployment"] == "edge-worker"
        assert mock_kubectl.call_count == 2
        wait_call_kwargs = mock_kubectl.call_args_list[1]
        assert wait_call_kwargs.kwargs["timeout"] == 120

    @patch("mcp_openshift.tools._run_kubectl")
    def test_restart_fails(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "",
            "stderr": "deployment not found",
            "returncode": 1,
            "success": False,
        }
        result = rollout_restart(deployment="nonexistent")
        assert result["success"] is False
        assert result["error"] == "deployment not found"
        assert mock_kubectl.call_count == 1

    @patch("mcp_openshift.tools._run_kubectl")
    def test_wait_times_out(self, mock_kubectl):
        mock_kubectl.side_effect = [
            {"stdout": "restarted", "stderr": "", "returncode": 0, "success": True},
            {"stdout": "", "stderr": "timed out waiting", "returncode": 1, "success": False},
        ]
        result = rollout_restart(deployment="slow-deploy")
        assert result["success"] is False
        assert "timed out" in result["message"]


class TestPatchDeploymentMemory:
    """Tests for the patch_deployment_memory tool."""

    @patch("mcp_openshift.tools._run_kubectl")
    def test_success(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "deployment.apps/edge-worker patched",
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = patch_deployment_memory(
            deployment="edge-worker", memory_limit="1Gi"
        )
        assert result["success"] is True
        assert result["new_memory_limit"] == "1Gi"
        cmd = mock_kubectl.call_args[0][0]
        assert "--type=json" in cmd

    @patch("mcp_openshift.tools._run_kubectl")
    def test_failure(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "",
            "stderr": "the path does not exist",
            "returncode": 1,
            "success": False,
        }
        result = patch_deployment_memory(
            deployment="no-limits", memory_limit="512Mi"
        )
        assert result["success"] is False


class TestGetPodLogs:
    """Tests for the get_pod_logs tool."""

    @patch("mcp_openshift.tools._run_kubectl")
    def test_success(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "line1\nline2\nline3",
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        result = get_pod_logs(pod_name="edge-worker-abc12", tail_lines=3)
        assert result["success"] is True
        assert "line1" in result["logs"]
        assert result["error"] is None

    @patch("mcp_openshift.tools._run_kubectl")
    def test_with_container(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "logs",
            "stderr": "",
            "returncode": 0,
            "success": True,
        }
        get_pod_logs(pod_name="multi-pod", container="sidecar")
        cmd = mock_kubectl.call_args[0][0]
        assert "-c" in cmd
        assert "sidecar" in cmd

    @patch("mcp_openshift.tools._run_kubectl")
    def test_pod_not_found(self, mock_kubectl):
        mock_kubectl.return_value = {
            "stdout": "",
            "stderr": "pods \"gone\" not found",
            "returncode": 1,
            "success": False,
        }
        result = get_pod_logs(pod_name="gone")
        assert result["success"] is False
        assert result["error"] is not None
