#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP = REPO / "conf" / "bootstrap.py"
CONFIG_TOOL = REPO / "conf" / "opencode-config.py"
CANONICAL = REPO / "conf" / "agents"


class ProductionBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "config"
        self.data = self.root / "data"
        self.agents = self.config / "agents"
        self.workflows = self.root / "workflows"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def env(self, **overrides: str) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "DARKMOON_UID": str(os.getuid()),
            "DARKMOON_GID": str(os.getgid()),
            "OPENCODE_CONFIG_TOOL": str(CONFIG_TOOL),
            "OPENCODE_CONFIG_DIR": str(self.config),
            "OPENCODE_DATA_DIR": str(self.data),
            "OPENCODE_AGENTS_DIR": str(self.agents),
            "OPENCODE_DEFAULT_AGENTS_DIR": str(CANONICAL),
            "DARKMOON_WORKFLOWS_DIR": str(self.workflows),
            "DARKMOON_DEFAULT_WORKFLOWS_DIR": str(REPO / "mcp" / "src" / "tools" / "workflows"),
            "OPENCODE_LOCAL_MODE": "true",
            "OPENCODE_LOCAL_PROVIDER_ID": "mock",
            "OPENCODE_LOCAL_PROVIDER_NAME": "Bootstrap mock",
            "OPENCODE_LOCAL_BASE_URL": "http://mock-provider:8000/v1",
            "OPENCODE_LOCAL_MODEL": "darkmoon-test-model",
            "OPENCODE_LOCAL_API_KEY": "not-a-real-key",
            "DARKMOON_MCP_TRANSPORT": "remote",
            "DARKMOON_MCP_URL": "http://darkmoon-mcp:8000/mcp",
        }
        env.update(overrides)
        return env

    def run_bootstrap(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BOOTSTRAP)],
            env=self.env(**overrides),
            text=True,
            capture_output=True,
            check=True,
        )

    def test_clean_bootstrap_seeds_agents_provider_remote_mcp_and_workflows(self) -> None:
        self.run_bootstrap()
        config_path = self.config / "opencode.json"
        state_path = self.config / ".darkmoon-bootstrap.json"
        config = json.loads(config_path.read_text())
        state = json.loads(state_path.read_text())
        self.assertEqual(config["model"], "mock/darkmoon-test-model")
        self.assertEqual(config["default_agent"], "pentest")
        self.assertEqual(config["subagent_depth"], 1)
        self.assertEqual(config["mcp"]["darkmoon"]["type"], "remote")
        self.assertEqual(config["mcp"]["darkmoon"]["url"], "http://darkmoon-mcp:8000/mcp")
        self.assertTrue((self.agents / "pentest.md").is_file())
        self.assertGreaterEqual(state["agents"], 50)
        self.assertGreater(state["workflows"], 0)
        self.assertEqual(state["uid"], os.getuid())
        self.assertEqual(state["gid"], os.getgid())
        self.assertTrue(any(self.workflows.glob("*.py")))
        self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(config_path.stat().st_uid, os.getuid())
        self.assertEqual(config_path.stat().st_gid, os.getgid())

    def test_bootstrap_is_idempotent_and_preserves_existing_prompt_customization(self) -> None:
        self.run_bootstrap()
        pentest = self.agents / "pentest.md"
        pentest.write_text(pentest.read_text() + "\nCUSTOM-PERSISTED-INSTRUCTION\n", encoding="utf-8")
        before = hashlib.sha256(pentest.read_bytes()).hexdigest()
        self.run_bootstrap()
        after = hashlib.sha256(pentest.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertIn("CUSTOM-PERSISTED-INSTRUCTION", pentest.read_text())

    def test_local_transport_remains_available_for_source_fallback(self) -> None:
        self.run_bootstrap(
            DARKMOON_MCP_TRANSPORT="local",
            DARKMOON_MCP_COMMAND='["/usr/local/bin/darkmoon-mcp"]',
        )
        config = json.loads((self.config / "opencode.json").read_text())
        self.assertEqual(config["mcp"]["darkmoon"]["type"], "local")
        self.assertEqual(config["mcp"]["darkmoon"]["command"], ["/usr/local/bin/darkmoon-mcp"])

    def test_invalid_remote_url_fails_closed(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_bootstrap(DARKMOON_MCP_URL="file:///tmp/not-http")

    def test_nonroot_identity_mismatch_fails_closed(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root can intentionally switch to another target identity")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_bootstrap(DARKMOON_UID=str(os.getuid() + 1))

    def test_invalid_identity_fails_closed(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_bootstrap(DARKMOON_UID="not-an-integer")


if __name__ == "__main__":
    unittest.main()
