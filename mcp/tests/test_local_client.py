"""
Tests for the local-subprocess executor (LocalCommandClient).

Proves the local executor mirrors DarkmoonDockerClient's public surface and
semantics when DARKMOON_EXEC_MODE=local is selected: commands run as local
subprocesses, timeouts kill the process, and tool availability is probed via
`which`. No Docker required.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.local_client import LocalCommandClient  # noqa: E402
from src.models.common import ExecutionStatus  # noqa: E402


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
