"""
Tests for the local-subprocess executor (LocalCommandClient).

Proves the local executor mirrors DarkmoonDockerClient's public surface and
semantics when DARKMOON_EXEC_MODE=local is selected: commands run as local
subprocesses, timeouts kill the process, and tool availability is probed via
`which`. No Docker required.
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import local_client as local_client_module  # noqa: E402
from src.local_client import LocalCommandClient  # noqa: E402
from src.models.common import ExecutionStatus  # noqa: E402


def _run_with_watchdog(fn, budget: float):
    """Run `fn` in a thread; raise AssertionError if it exceeds `budget` seconds.

    This proves the executor returns instead of blocking forever on a pipe
    held open by a backgrounded grandchild.
    """
    result = {}
    exc = {}

    def _target():
        try:
            result["value"] = fn()
        except BaseException as e:  # noqa: BLE001
            exc["error"] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(budget)
    if t.is_alive():
        raise AssertionError(
            f"execute_command did not return within {budget}s "
            f"(orphan-held-stdout hang)"
        )
    if "error" in exc:
        raise exc["error"]
    return result["value"]


def test_echo():
    result = LocalCommandClient(timeout=5).execute_command("echo hi", timeout=5)
    assert result.status == ExecutionStatus.SUCCESS
    assert result.exit_code == 0
    assert "hi" in result.stdout


def test_timeout():
    result = LocalCommandClient().execute_command("sleep 5", timeout=1)
    assert result.status == ExecutionStatus.TIMEOUT


def test_check_tool():
    client = LocalCommandClient()
    assert client.check_tool_available("bash") is True
    assert client.check_tool_available("definitely-not-a-real-binary-xyz") is False


def test_orphan_pipe_does_not_hang():
    """A backgrounded grandchild that keeps stdout open must not hang the read.

    `sleep 100 &` backgrounds a process that inherits the stdout pipe and keeps
    it open for 100s. The direct `bash` child exits quickly (exec sleep 0.2),
    but a naive read loop would block on the pipe until the orphan dies. The
    executor must enforce a wall-clock deadline and return TIMEOUT promptly.
    """
    client = LocalCommandClient()

    result = _run_with_watchdog(
        lambda: client.execute_command(
            "sleep 100 & echo started; exec sleep 0.2", timeout=2
        ),
        budget=8.0,
    )

    assert result.status == ExecutionStatus.TIMEOUT


def test_browser_request_payload_is_not_broadcast_or_recorded():
    client = LocalCommandClient(timeout=5)
    broadcasts = []
    client._broadcast = lambda payload, _session_id=None: broadcasts.append(payload)

    result = client.execute_command(
        ["true", "/fixed/headless_runner.mjs", "reversible-encoded-target"],
        timeout=5,
    )

    assert result.status == ExecutionStatus.SUCCESS
    assert broadcasts == []
    assert "reversible-encoded-target" not in str(result.metadata)
    assert "REDACTED_BROWSER_REQUEST" in str(result.metadata)


def test_browser_request_payload_is_hidden_on_executor_exception(monkeypatch):
    def fail_to_start(*_args, **_kwargs):
        raise RuntimeError("failure mentions reversible-encoded-target")

    monkeypatch.setattr(local_client_module.subprocess, "Popen", fail_to_start)
    result = LocalCommandClient(timeout=5).execute_command(
        ["node", "/fixed/headless_runner.mjs", "reversible-encoded-target"],
        timeout=5,
    )

    serialized = f"{result.stderr} {result.metadata}"
    assert result.status == ExecutionStatus.FAILED
    assert "reversible-encoded-target" not in serialized
    assert "REDACTED_BROWSER_REQUEST" in serialized
