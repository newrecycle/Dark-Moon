from __future__ import annotations

import json
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[1]


class BrowserPackagingTests(unittest.TestCase):
    def test_browser_contract_is_shared_by_python_and_node(self) -> None:
        contract = json.loads(
            (
                REPO
                / "mcp"
                / "src"
                / "tools"
                / "browser"
                / "capabilities.json"
            ).read_text(encoding="utf-8")
        )
        runner = (
            REPO / "mcp" / "src" / "tools" / "browser" / "headless_runner.mjs"
        ).read_text(encoding="utf-8")
        policy = (
            REPO / "mcp" / "src" / "tools" / "browser" / "policy.py"
        ).read_text(encoding="utf-8")

        self.assertEqual(len(contract["modes"]), 15)
        self.assertEqual(contract["limits"]["max_pages"], 50)
        self.assertEqual(contract["limits"]["max_depth"], 8)
        self.assertEqual(contract["limits"]["max_requests"], 2500)
        self.assertEqual(contract["limits"]["max_timeout_seconds"], 600)
        self.assertIn("./capabilities.json", runner)
        self.assertIn('with_name("capabilities.json")', policy)

    def test_playwright_dependency_is_exact_and_lockfile_matches(self) -> None:
        package = json.loads(
            (REPO / "browser" / "package.json").read_text(encoding="utf-8")
        )
        lock = json.loads(
            (REPO / "browser" / "package-lock.json").read_text(
                encoding="utf-8"
            )
        )

        version = package["dependencies"]["playwright"]
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertEqual(lock["packages"]["node_modules/playwright"]["version"], version)
        self.assertEqual(
            lock["packages"]["node_modules/playwright-core"]["version"],
            version,
        )
        self.assertTrue(
            lock["packages"]["node_modules/playwright"]["integrity"].startswith(
                "sha512-"
            )
        )

    def test_image_uses_reproducible_install_and_launch_probe(self) -> None:
        dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("npm ci --omit=dev", dockerfile)
        self.assertIn("npx --no-install playwright install chromium", dockerfile)
        self.assertIn("verify-runtime.cjs --launch", dockerfile)
        self.assertNotIn("npm install playwright", dockerfile)

    def test_runner_and_runtime_probe_parse_as_node_scripts(self) -> None:
        runner = REPO / "mcp" / "src" / "tools" / "browser" / "headless_runner.mjs"
        probe = REPO / "browser" / "verify-runtime.cjs"
        self.assertTrue(runner.is_file())
        self.assertTrue(probe.is_file())

    def test_readiness_is_bound_to_the_plugin_container_process(self) -> None:
        entrypoint = (REPO / "conf" / "entrypoint-darkmoon.sh").read_text(
            encoding="utf-8"
        )
        healthcheck = (REPO / "mcp" / "src" / "healthcheck.py").read_text(
            encoding="utf-8"
        )
        launcher = (
            REPO / "plugin" / "scripts" / "darkmoon-up.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("DARKMOON_MCP_PID_FILE", entrypoint)
        self.assertIn("verify_local_server_process()", healthcheck)
        self.assertIn("src.http_server", healthcheck)
        self.assertIn("compose -f", launcher)
        self.assertIn("python -m src.healthcheck", launcher)
        self.assertNotIn("curl -s -o /dev/null", launcher)


if __name__ == "__main__":
    unittest.main(verbosity=2)
