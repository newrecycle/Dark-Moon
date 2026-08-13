#!/usr/bin/env python3
"""Security-invariant tests for the single-container Dark-Moon stack.

The stack is now ONE container (`darkmoon`): the toolbox image with the MCP
server baked in, executing tools locally (DARKMOON_EXEC_MODE=local). There is
no OpenCode brain container and no docker-proxy sidecar, and the Docker socket
is never mounted.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SOCKET = "/var/run/docker.sock"


def load_services(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("services", {})


class ComposeSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compose = load_services(REPO / "docker-compose.yml")
        self.dev_compose = load_services(REPO / "docker-compose-dev.yml")

    def _assert_single_service(self, services: dict, label: str) -> dict:
        self.assertEqual(
            set(services.keys()),
            {"darkmoon"},
            f"{label}: expected exactly one service 'darkmoon', got {sorted(services)}",
        )
        return services["darkmoon"]

    def _assert_no_socket_mount(self, services: dict, label: str) -> None:
        for name, svc in services.items():
            for volume in svc.get("volumes", []):
                self.assertNotIn(
                    SOCKET,
                    str(volume),
                    f"{label}: service '{name}' mounts the Docker socket ({volume})",
                )

    def test_production_is_single_container_no_socket(self) -> None:
        svc = self._assert_single_service(self.compose, "production compose")
        self._assert_no_socket_mount(self.compose, "production compose")
        # Host networking: the MCP is reachable on localhost with no port publish.
        self.assertEqual(svc.get("network_mode"), "host")
        env = svc.get("environment", {})
        self.assertEqual(env.get("DARKMOON_EXEC_MODE"), "local")
        self.assertEqual(env.get("DARKMOON_MCP_HOST"), "127.0.0.1")
        self.assertEqual(str(env.get("DARKMOON_MCP_PORT")), "8000")
        self.assertEqual(env.get("DARKMOON_MCP_PATH"), "/mcp")
        # Healthcheck resolves the baked-in server module.
        healthcheck = " ".join(str(p) for p in svc.get("healthcheck", {}).get("test", []))
        self.assertIn("src.healthcheck", healthcheck)

    def test_development_is_single_container_no_socket(self) -> None:
        svc = self._assert_single_service(self.dev_compose, "dev compose")
        self._assert_no_socket_mount(self.dev_compose, "dev compose")
        self.assertEqual(svc.get("network_mode"), "host")
        env = svc.get("environment", {})
        self.assertEqual(env.get("DARKMOON_EXEC_MODE"), "local")
        self.assertEqual(env.get("DARKMOON_MCP_HOST"), "127.0.0.1")
        # Dev bind-mounts the live mcp/ source tree.
        mounts = " ".join(str(v) for v in svc.get("volumes", []))
        self.assertIn("/opt/darkmoon/mcp/server", mounts)

    def test_no_legacy_services(self) -> None:
        for services, label in (
            (self.compose, "production compose"),
            (self.dev_compose, "dev compose"),
        ):
            for legacy in ("opencode", "opencode-bootstrap", "docker-proxy", "darkmoon-mcp"):
                self.assertNotIn(
                    legacy,
                    services,
                    f"{label}: legacy service '{legacy}' must be removed",
                )


if __name__ == "__main__":
    unittest.main()
