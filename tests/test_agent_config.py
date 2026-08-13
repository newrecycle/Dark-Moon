#!/usr/bin/env python3
"""Keyless regression tests for Dark-Moon agent configuration."""

from __future__ import annotations

import fnmatch
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest import mock

import yaml

REPO = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO / "conf" / "opencode-config.py"
SPEC = importlib.util.spec_from_file_location("darkmoon_opencode_config", TOOL_PATH)
assert SPEC and SPEC.loader
CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIG)


class AgentConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.agents = self.root / "agents"
        shutil.copytree(REPO / "conf" / "agents", self.agents)
        self.config_file = self.root / "config" / "opencode.json"
        self.auth_file = self.root / "share" / "auth.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def apply(self, env: dict[str, str] | None = None) -> dict:
        with mock.patch.dict(os.environ, env or {}, clear=True):
            CONFIG.apply_configuration(self.config_file, self.auth_file, self.agents, REPO / "conf" / "agents")
        return json.loads(self.config_file.read_text(encoding="utf-8"))

    def test_every_agent_uses_the_pinned_supported_schema(self) -> None:
        schema = json.loads((REPO / "conf" / "opencode-schema.json").read_text())
        self.assertEqual(set(CONFIG.SUPPORTED_AGENT_FIELDS), set(schema["darkmoon_markdown_fields"]))
        agents = CONFIG.validate_agents(self.agents)
        self.assertGreaterEqual(len(agents), 50)
        for name, data in agents.items():
            with self.subTest(agent=name):
                self.assertFalse(set(data) & CONFIG.LEGACY_AGENT_FIELDS)
                self.assertTrue((self.agents / f"{name}.md").is_file())
                _, prompt = CONFIG.read_agent(self.agents / f"{name}.md", allow_legacy=False)
                self.assertTrue(prompt.strip())

    def test_pentest_is_only_primary_and_specialists_cannot_delegate(self) -> None:
        agents = CONFIG.validate_agents(self.agents)
        self.assertEqual(agents["pentest"]["mode"], "primary")
        self.assertEqual(agents["pentest"]["permission"]["task"], "allow")
        for name, data in agents.items():
            if name == "pentest":
                continue
            self.assertEqual(data["mode"], "subagent")
            self.assertNotEqual(data["permission"].get("task"), "allow")

    def test_source_fallback_keeps_local_mcp_and_narrow_permissions(self) -> None:
        generated = self.apply()
        self.assertEqual(generated["mcp"]["darkmoon"]["command"], ["/usr/local/bin/darkmoon-mcp"])
        pentest = CONFIG.validate_agents(self.agents)["pentest"]
        self.assertEqual(list(pentest["permission"])[:3], ["*", "darkmoon_*", "task"])

    def test_generated_cloud_config_has_no_legacy_metadata(self) -> None:
        generated = self.apply(
            {
                "OPENROUTER_PROVIDER": "nvidia",
                "OPENROUTER_API_KEY": "not-a-real-key",
                "OPENCODE_MODEL": "deepseek-ai/deepseek-v4-pro",
            }
        )
        self.assertEqual(generated["model"], "nvidia/deepseek-ai/deepseek-v4-pro")
        self.assertEqual(CONFIG._walk_forbidden(generated), [])
        self.assertEqual(set(json.loads(self.auth_file.read_text())), {"nvidia"})

    def test_issue36_legacy_metadata_migrates_without_provider_options(self) -> None:
        issue_agents = self.root / "issue36"
        issue_agents.mkdir()
        (issue_agents / "prompt.txt").write_text("Legacy prompt\n")
        (issue_agents / "pentest.md").write_text(
            """---
id: pentest
name: pentest
description: Issue 36
primary: true
prompt_file: prompt.txt
mcp: [darkmoon]
---
Body.
"""
        )
        CONFIG.migrate_agents(issue_agents)
        data, prompt = CONFIG.read_agent(issue_agents / "pentest.md", allow_legacy=False)
        self.assertFalse(set(data) & CONFIG.LEGACY_AGENT_FIELDS)
        self.assertFalse(set(data.get("options", {})) & CONFIG.REQUEST_LEAK_FIELDS)
        self.assertEqual(data["mode"], "primary")
        self.assertTrue(prompt)

    def test_stale_primary_mode_on_non_pentest_agent_is_auto_corrected(self) -> None:
        """A stale agent with mode: primary (not pentest) must be migrated to subagent."""
        stale = self.agents / "pentest-web.md"
        stale.write_text(
            "---\n"
            "description: Stale web pentest agent\n"
            "mode: primary\n"
            "permission:\n"
            "  '*': deny\n"
            "  darkmoon_*: allow\n"
            "---\n"
            "Prompt body.\n"
        )
        CONFIG.migrate_agents(self.agents)
        data, _ = CONFIG.read_agent(stale, allow_legacy=False)
        self.assertEqual(data["mode"], "subagent")
        CONFIG.validate_agents(self.agents)

    def test_unknown_and_duplicate_frontmatter_are_rejected(self) -> None:
        path = self.agents / "aws.md"
        original = path.read_text()
        path.write_text(original.replace("mode: subagent\n", "mode: subagent\nopaque_metadata: true\n", 1))
        with self.assertRaisesRegex(CONFIG.ConfigError, "unsupported agent field"):
            CONFIG.migrate_agents(self.agents)
        path.write_text(original.replace("mode: subagent\n", "mode: subagent\nmode: primary\n", 1))
        with self.assertRaisesRegex(CONFIG.ConfigError, "duplicate key"):
            CONFIG.validate_agents(self.agents)

    def test_invalid_permission_and_provider_metadata_are_rejected(self) -> None:
        path = self.agents / "aws.md"
        original = path.read_text()
        path.write_text(original.replace("  darkmoon_*: allow\n", "  darkmoon_*:\n    '*': [allow]\n", 1))
        with self.assertRaisesRegex(CONFIG.ConfigError, "invalid nested permission action"):
            CONFIG.validate_agents(self.agents)
        path.write_text(original.replace("mode: subagent\n", "mode: subagent\noptions:\n  reasoning_effort: low\n  primary: true\n", 1))
        with self.assertRaisesRegex(CONFIG.ConfigError, "options contains legacy agent metadata"):
            CONFIG.migrate_agents(self.agents)

    def test_valid_provider_options_survive_migration(self) -> None:
        path = self.agents / "aws.md"
        path.write_text(path.read_text().replace("mode: subagent\n", "mode: subagent\noptions:\n  reasoning_effort: low\n", 1))
        CONFIG.migrate_agents(self.agents)
        data, _ = CONFIG.read_agent(path, allow_legacy=False)
        self.assertEqual(data["options"], {"reasoning_effort": "low"})

    def test_missing_prompt_and_duplicate_identifier_are_rejected(self) -> None:
        agents = self.root / "bad"
        agents.mkdir()
        (agents / "pentest.md").write_text("---\nid: pentest\ndescription: Missing\nprimary: true\nprompt_file: absent.md\n---\nBody\n")
        with self.assertRaisesRegex(CONFIG.ConfigError, "prompt_file does not exist"):
            CONFIG.migrate_agents(agents)
        duplicate = self.agents / "ad.md"
        duplicate.write_text("---\nid: active-directory\nname: active-directory\ndescription: Duplicate\n---\nPrompt\n")
        with self.assertRaisesRegex(CONFIG.ConfigError, "duplicate agent identifier"):
            CONFIG.migrate_agents(self.agents)

    def test_provider_modes_are_rendered(self) -> None:
        cases = [
            ({}, "opencode/big-pickle"),
            ({"ANTHROPIC_BASE_URL": "http://anthropic.test", "ANTHROPIC_MODEL": "private"}, "anthropic/private"),
            ({
                "OPENCODE_LOCAL_MODE": "true",
                "OPENCODE_LOCAL_PROVIDER_ID": "local",
                "OPENCODE_LOCAL_PROVIDER_NAME": "Local",
                "OPENCODE_LOCAL_BASE_URL": "http://local.test/v1",
                "OPENCODE_LOCAL_MODEL": "model",
            }, "local/model"),
            ({"OPENROUTER_PROVIDER": "openrouter", "OPENROUTER_API_KEY": "x", "OPENCODE_MODEL": "z-ai/glm-5.2"}, "openrouter/z-ai/glm-5.2"),
            ({"OPENROUTER_PROVIDER": "nvidia", "OPENROUTER_API_KEY": "x", "OPENCODE_MODEL": "nvidia/minimaxai/minimax-m3"}, "nvidia/minimaxai/minimax-m3"),
        ]
        for env, expected in cases:
            with self.subTest(expected=expected):
                generated = self.apply(env)
                self.assertEqual(generated["model"], expected)
                self.assertEqual(generated["small_model"], expected)

    def test_mcp_tool_names_match_permission_wildcard(self) -> None:
        source = (REPO / "mcp" / "src" / "server.py").read_text()
        functions = re.findall(r"@mcp\.tool\(\)\s*\ndef\s+([a-zA-Z0-9_]+)\(", source)
        generated = {f"darkmoon_{name}" for name in functions}
        self.assertIn("darkmoon_get_session", generated)
        self.assertIn("darkmoon_execute_command", generated)
        self.assertTrue(all(fnmatch.fnmatchcase(name, "darkmoon_*") for name in generated))

    def test_configuration_restart_is_idempotent(self) -> None:
        env = {"OPENROUTER_PROVIDER": "nvidia", "OPENROUTER_API_KEY": "x", "OPENCODE_MODEL": "z-ai/glm-5.2"}
        first = self.apply(env)
        first_agents = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.agents.glob("*.md")}
        second = self.apply(env)
        second_agents = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.agents.glob("*.md")}
        self.assertEqual(first, second)
        self.assertEqual(first_agents, second_agents)

    def test_targeted_orchestrator_migration_preserves_custom_text(self) -> None:
        current = self.root / "persisted"
        canonical = self.root / "canonical"
        current.mkdir()
        canonical.mkdir()
        frontmatter = """---
description: Test orchestrator
mode: primary
permission:
  '*': deny
  darkmoon_*: allow
  task: allow
---
"""
        fence = "=" * 80
        old_body = f"""CUSTOM USER PREFIX
{fence}
PHASE 1 — INITIAL CLASSIFICATION & MULTI-DISPATCH
{fence}
Instead, you must dynamically discover available agents within the OpenCode
agents directory.
{fence}
PHASE 2 — SIGNAL DETECTION MATRIX
{fence}
DISPATCH: cms/lms sub agent
CONTEXT PASS: old
{fence}
PHASE 6 — SUBAGENT SPAWN PROTOCOL — UNIVERSAL COMPATIBILITY VERSION
{fence}
SUBAGENT PROMPT = RAW AGENT FILE
Any additional fields (e.g., description) are forbidden.
{fence}
PHASE 7 — TERMINATION & REPORT GENERATION
{fence}
CUSTOM USER SUFFIX
"""
        new_body = f"""CANONICAL PREFIX
{fence}
PHASE 1 — INITIAL CLASSIFICATION & MULTI-DISPATCH
{fence}
Use filename-derived agent identifiers from the task tool.
{fence}
PHASE 2 — SIGNAL DETECTION MATRIX
{fence}
DISPATCH MAPPING (use the exact matching subagent_type):
    - WordPress -> wordpress
CONTEXT PASS: canonical
{fence}
PHASE 6 — SUBAGENT SPAWN PROTOCOL — OPENCODE 1.18.12
{fence}
description, prompt, and subagent_type are required.
{fence}
PHASE 7 — TERMINATION & REPORT GENERATION
{fence}
CANONICAL SUFFIX
"""
        (current / "pentest.md").write_text(frontmatter + old_body)
        (canonical / "pentest.md").write_text(frontmatter + new_body)
        CONFIG.migrate_required_prompt_sections(current, canonical)
        _, migrated = CONFIG.read_agent(current / "pentest.md", allow_legacy=False)
        self.assertIn("CUSTOM USER PREFIX", migrated)
        self.assertIn("CUSTOM USER SUFFIX", migrated)
        self.assertIn("filename-derived agent identifiers", migrated)
        self.assertIn("description, prompt, and subagent_type are required", migrated)
        self.assertIn("WordPress -> wordpress", migrated)
        self.assertNotIn("RAW AGENT FILE", migrated)
        self.assertNotIn("cms/lms sub agent", migrated)

    def test_source_dockerfile_pins_audited_opencode(self) -> None:
        schema = json.loads((REPO / "conf" / "opencode-schema.json").read_text())
        dockerfile = (REPO / "Dockerfile.opencode").read_text()
        self.assertIn(f"ARG OPENCODE_COMMIT={schema['commit']}", dockerfile)
        self.assertIn(f"ARG OPENCODE_VERSION={schema['version']}", dockerfile)
        self.assertIn("bun install --frozen-lockfile", dockerfile)

    def test_reference_configs_make_transport_scope_explicit(self) -> None:
        source = json.loads((REPO / "conf" / "opencode.json").read_text())
        production = json.loads((REPO / "conf" / "opencode.production.json").read_text())
        standalone = json.loads((REPO / "mcp" / "opencode.json").read_text())
        self.assertEqual(source["mcp"]["darkmoon"]["type"], "local")
        self.assertEqual(standalone["mcp"]["darkmoon"]["type"], "local")
        self.assertEqual(production["mcp"]["darkmoon"]["type"], "remote")
        self.assertEqual(production["subagent_depth"], 1)
        self.assertEqual(CONFIG._walk_forbidden(production), [])

    def test_production_and_arm_compose_are_single_darkmoon_container(self) -> None:
        production = yaml.safe_load((REPO / "docker-compose.yml").read_text())
        development = yaml.safe_load((REPO / "docker-compose-dev.yml").read_text())
        for name, compose in (("production", production), ("development", development)):
            services = compose["services"]
            self.assertEqual(
                set(services),
                {"darkmoon"},
                f"{name}: expected exactly one service 'darkmoon'",
            )
            svc = services["darkmoon"]
            self.assertEqual(svc.get("network_mode"), "host")
            env = svc.get("environment", {})
            self.assertEqual(env.get("DARKMOON_EXEC_MODE"), "local")
            self.assertEqual(env.get("DARKMOON_MCP_HOST"), "127.0.0.1")
            # No legacy services survive the merge.
            for legacy in ("opencode", "opencode-bootstrap", "docker-proxy", "darkmoon-mcp"):
                self.assertNotIn(legacy, services, f"{name}: legacy service '{legacy}' remains")
            # Prod uses the prebuilt image; dev builds locally.
            if name == "production":
                self.assertNotIn("build", svc)
            else:
                self.assertEqual(svc["build"]["dockerfile"], "Dockerfile")

    def test_installer_and_wrapper_are_repository_safe_and_stock_image_compatible(self) -> None:
        installer = (REPO / "install.sh").read_text()
        wrapper = (REPO / "darkmoon.sh").read_text()
        self.assertIn('${BASH_SOURCE[0]}', installer)
        self.assertIn("--keep", installer)
        generated_match = re.search(
            r"(?ms)^GENERATED_BIND_PATHS=\(\n(?P<body>.*?)^\)\n",
            installer,
        )
        self.assertIsNotNone(generated_match)
        assert generated_match is not None
        generated_paths = re.findall(
            r'(?m)^\s+"\./([^"]+)"\s*$',
            generated_match.group("body"),
        )
        self.assertEqual(
            generated_paths,
            ["data", "darkmoon-settings", "workflows", "reports", "sessions", "workspace"],
        )
        self.assertNotIn('SCRIPT_DIR="$(pwd)"', installer)
        self.assertNotIn("bash -lc", wrapper)
        self.assertIn("darkmoon", wrapper)
        self.assertIn("src.mcp_monitoring", wrapper)


if __name__ == "__main__":
    unittest.main(verbosity=2)
