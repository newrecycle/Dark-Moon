"""Non-Docker browser-runtime health checks."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.common import ExecutionResult, ExecutionStatus  # noqa: E402
from src.tools.core.health import BROWSER_RUNTIME_NAME, HealthChecker  # noqa: E402


class FakeHealthClient:
    def __init__(self, browser_available=True):
        self.browser_available = browser_available
        self.commands = []

    def execute_command(self, command, **kwargs):
        self.commands.append((command, kwargs))
        payload = {
            "available": self.browser_available,
            "engine": BROWSER_RUNTIME_NAME,
            "version": "1.62.1",
        }
        return ExecutionResult(
            status=(
                ExecutionStatus.SUCCESS
                if self.browser_available
                else ExecutionStatus.FAILED
            ),
            stdout=json.dumps(payload),
            exit_code=0 if self.browser_available else 1,
        )

    def health_check(self):
        return {"container_running": True, "message": "ok", "disk_usage": None}

    def check_tool_available(self, _tool):
        return True


def test_browser_runtime_probe_is_available():
    client = FakeHealthClient(browser_available=True)
    status = HealthChecker(client).check_browser_runtime()
    assert status == {
        "tool_name": BROWSER_RUNTIME_NAME,
        "available": True,
        "version": "1.62.1",
    }
    assert client.commands[0][0] == ["node", "/opt/darkmoon/verify-runtime.cjs"]


def test_missing_browser_runtime_makes_health_unhealthy():
    status = HealthChecker(FakeHealthClient(browser_available=False)).check()
    assert status.healthy is False
    assert status.tools_available[BROWSER_RUNTIME_NAME] is False
    assert BROWSER_RUNTIME_NAME in status.message


def test_diagnostics_include_browser_runtime_details():
    checker = HealthChecker(FakeHealthClient(browser_available=True))
    checker.check_network_connectivity = lambda: {}
    checker.get_resource_usage = lambda: {}
    details = checker.diagnose()
    assert details["essential_tools"][BROWSER_RUNTIME_NAME]["available"] is True
