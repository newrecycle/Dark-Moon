#!/usr/bin/env python3
from __future__ import annotations

import json
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
        bootstrap = services["opencode-bootstrap"]
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

        # Bootstrap starts as root only to initialize Docker-created bind mounts.
        # conf/bootstrap.py must receive a target identity, use neutral writable
        # paths, and drop privileges before provider secrets are rendered.
        self.assertNotIn("user", bootstrap)
        self.assertEqual(bootstrap["network_mode"], "none")
        self.assertEqual(bootstrap["environment"]["DARKMOON_UID"], "${DARKMOON_UID:-0}")
        self.assertEqual(bootstrap["environment"]["DARKMOON_GID"], "${DARKMOON_GID:-0}")
        self.assertEqual(bootstrap["environment"]["OPENCODE_CONFIG_DIR"], "/config")
        self.assertEqual(bootstrap["environment"]["OPENCODE_DATA_DIR"], "/data")
        self.assertEqual(bootstrap["environment"]["OPENCODE_AGENTS_DIR"], "/config/agents")
        self.assertEqual(bootstrap["environment"]["DARKMOON_WORKFLOWS_DIR"], "/workflows")
        self.assertTrue(any(str(volume).endswith(":/config:rw") for volume in bootstrap["volumes"]))
        self.assertTrue(any(str(volume).endswith(":/data:rw") for volume in bootstrap["volumes"]))
        self.assertTrue(any(str(volume).endswith(":/workflows:rw") for volume in bootstrap["volumes"]))

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

    def test_production_fixture_uses_one_model_contract(self) -> None:
        compose = yaml.safe_load(
            (REPO / "tests" / "docker-compose.production.yml").read_text(encoding="utf-8")
        )
        services = compose["services"]
        mock_env = services["mock-provider"]["environment"]
        overlay = json.loads(services["opencode"]["environment"]["OPENCODE_CONFIG_CONTENT"])

        model_id = mock_env["MOCK_EXPECT_MODEL"]
        self.assertEqual(model_id, "darkmoon-test-model")
        self.assertEqual(mock_env["MOCK_EXPECT_TEMPERATURE"], "0.2")
        self.assertEqual(mock_env["MOCK_EXPECT_TOP_P"], "0.9")
        self.assertEqual(mock_env["MOCK_EXPECT_REASONING_EFFORT"], "medium")

        self.assertEqual(set(overlay["provider"]), {"mock"})
        model = overlay["provider"]["mock"]["models"][model_id]
        self.assertIs(model["temperature"], True)
        self.assertIs(model["reasoning"], True)
        self.assertIs(model["tool_call"], True)
        self.assertEqual(model["variants"]["medium"]["reasoning_effort"], "medium")

        agent = overlay["agent"]["pentest"]
        self.assertEqual(agent["temperature"], 0.2)
        self.assertEqual(agent["top_p"], 0.9)
        self.assertEqual(agent["variant"], "medium")
        self.assertEqual(agent["options"]["reasoning_effort"], "medium")


if __name__ == "__main__":
    unittest.main(verbosity=2)
