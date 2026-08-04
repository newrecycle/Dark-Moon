#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
SOCKET = "/var/run/docker.sock"
PROXY_IMAGE = "tecnativa/docker-socket-proxy:v0.4.2@sha256:1f3a6f303320723d199d2316a3e82b2e2685d86c275d5e3deeaf182573b47476"


class ComposeSecurityTests(unittest.TestCase):
    def check_topology(self, filename: str) -> None:
        compose = yaml.safe_load((REPO / filename).read_text(encoding="utf-8"))
        services = compose["services"]
        proxy = services["docker-proxy"]
        mcp = services["darkmoon-mcp"]
        opencode = services["opencode"]

        self.assertEqual(proxy["image"], PROXY_IMAGE)
        self.assertEqual(proxy["networks"], ["control"])
        self.assertNotIn("ports", proxy)
        self.assertEqual(
            proxy["environment"],
            {"CONTAINERS": "1", "EXEC": "1", "POST": "1", "LOG_LEVEL": "warning"},
        )
        self.assertEqual(proxy["volumes"], [f"{SOCKET}:{SOCKET}:ro"])

        self.assertEqual(mcp["environment"]["DOCKER_HOST"], "tcp://docker-proxy:2375")
        self.assertEqual(mcp["depends_on"]["docker-proxy"]["condition"], "service_started")
        self.assertFalse(any(SOCKET in volume for volume in mcp.get("volumes", [])))
        self.assertFalse(any(SOCKET in volume for volume in opencode.get("volumes", [])))

        socket_consumers = {
            name
            for name, service in services.items()
            if any(SOCKET in volume for volume in service.get("volumes", []))
        }
        self.assertEqual(socket_consumers, {"darkmoon", "docker-proxy"})

    def test_production_socket_boundary(self) -> None:
        self.check_topology("docker-compose.yml")

    def test_development_socket_boundary(self) -> None:
        self.check_topology("docker-compose-dev.yml")

    def test_protocol_fixture_uses_the_same_proxy_controls(self) -> None:
        compose = yaml.safe_load((REPO / "tests" / "docker-compose.mcp.yml").read_text(encoding="utf-8"))
        services = compose["services"]
        self.assertEqual(services["docker-proxy"]["image"], PROXY_IMAGE)
        self.assertEqual(services["darkmoon-mcp"]["environment"]["DOCKER_HOST"], "tcp://docker-proxy:2375")
        self.assertFalse(any(SOCKET in volume for volume in services["darkmoon-mcp"].get("volumes", [])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
