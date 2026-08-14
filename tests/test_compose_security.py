#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
SOCKET = "/var/run/docker.sock"


def _env_get(service: dict, key: str):
    """Read an environment value from a compose service, accepting either a
    mapping or a list of ``KEY=VALUE`` strings."""
    env = service.get("environment") or {}
    if isinstance(env, dict):
        return env.get(key)
    if isinstance(env, list):
        for item in env:
            if isinstance(item, str) and item.startswith(f"{key}="):
                return item.split("=", 1)[1]
    return None


def _services(compose_path: Path) -> dict:
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    return compose.get("services", {}) or {}


def _assert_no_socket(services: dict) -> None:
    for name, service in services.items():
        for volume in service.get("volumes", []) or []:
            assert SOCKET not in str(volume), f"{name} mounts {SOCKET}"


class ComposeSecurityTests(unittest.TestCase):
    def test_production_is_single_darkmoon_container(self) -> None:
        services = _services(REPO / "docker-compose.yml")
        self.assertEqual(set(services), {"darkmoon"})
        darkmoon = services["darkmoon"]
        _assert_no_socket(services)
        self.assertEqual(darkmoon.get("network_mode"), "host")
        self.assertEqual(_env_get(darkmoon, "DARKMOON_MCP_HOST"), "127.0.0.1")
        self.assertEqual(_env_get(darkmoon, "DARKMOON_EXEC_MODE"), "local")
        healthcheck = darkmoon.get("healthcheck", {})
        self.assertIn("src.healthcheck", str(healthcheck))

    def test_protocol_fixture_uses_single_container(self) -> None:
        services = _services(REPO / "tests" / "docker-compose.mcp.yml")
        self.assertIn("darkmoon", services)
        self.assertNotIn("opencode", services)
        self.assertNotIn("darkmoon-mcp", services)
        self.assertNotIn("docker-proxy", services)
        darkmoon = services["darkmoon"]
        self.assertNotIn("build", darkmoon)
        _assert_no_socket(services)
        self.assertEqual(_env_get(darkmoon, "DARKMOON_MCP_HOST"), "127.0.0.1")
        self.assertEqual(_env_get(darkmoon, "DARKMOON_EXEC_MODE"), "local")
        healthcheck = darkmoon.get("healthcheck", {})
        self.assertIn("src.healthcheck", str(healthcheck))

    def test_production_fixture_has_no_opencode(self) -> None:
        services = _services(REPO / "tests" / "docker-compose.production.yml")
        self.assertNotIn("opencode", services)
        self.assertNotIn("darkmoon-mcp", services)
        self.assertNotIn("docker-proxy", services)
        _assert_no_socket(services)


if __name__ == "__main__":
    unittest.main(verbosity=2)
