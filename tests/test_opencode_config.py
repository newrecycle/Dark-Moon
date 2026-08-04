#!/usr/bin/env python3
"""Keyless regression tests for Dark-Moon/OpenCode agent compatibility."""

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


REPO = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO / "conf" / "opencode-config.py"
SPEC = importlib.util.spec_from_file_location("darkmoon_opencode_config", TOOL_PATH)
assert SPEC and SPEC.loader
CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIG)


class OpenCodeConfigTests(unittest.TestCase):
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
        schema = json.loads((REPO / "conf" / "opencode-schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(CONFIG.SUPPORTED_AGENT_FIELDS), set(schema["darkmoon_markdown_fields"]))
        self.assertEqual(
            set(schema["schema_declared_agent_fields"]),
            set(schema["supported_agent_fields"]) | set(schema["deprecated_agent_fields"]),
        )
        agents = CONFIG.validate_agents(self.agents)
        supported = set(schema["supported_agent_fields"])
        for name, data in agents.items():
            with self.subTest(agent=name):
                self.assertLessEqual(set(data), supported)
                self.assertTrue((self.agents / f"{name}.md").is_file())
                _, prompt = CONFIG.read_agent(self.agents / f"{name}.md", allow_legacy=False)
                self.assertTrue(prompt.strip())

    def test_pentest_is_primary_and_specialists_are_subagents(self) -> None:
        agents = CONFIG.validate_agents(self.agents)
        self.assertEqual(agents["pentest"]["mode"], "primary")
        self.assertGreater(len(agents), 1)
        self.assertTrue(all(data["mode"] == "subagent" for name, data in agents.items() if name != "pentest"))

    def test_global_mcp_and_narrow_pentest_tool_access(self) -> None:
        generated = self.apply()
        self.assertTrue(generated["mcp"]["darkmoon"]["enabled"])
        self.assertEqual(generated["mcp"]["darkmoon"]["command"], ["/usr/local/bin/darkmoon-mcp"])
        self.assertNotIn("permission", generated)
        pentest = CONFIG.validate_agents(self.agents)["pentest"]
        self.assertEqual(list(pentest["permission"])[:3], ["*", "darkmoon_*", "task"])
        self.assertEqual(pentest["permission"]["*"], "deny")
        self.assertEqual(pentest["permission"]["darkmoon_*"], "allow")
        self.assertEqual(pentest["permission"]["task"], "allow")

    def test_generated_json_contains_no_legacy_agent_metadata(self) -> None:
        generated = self.apply(
            {
                "OPENROUTER_PROVIDER": "nvidia",
                "OPENROUTER_API_KEY": "not-a-real-key",
                "OPENCODE_MODEL": "deepseek-ai/deepseek-v4-pro",
            }
        )
        self.assertEqual(generated["model"], "nvidia/deepseek-ai/deepseek-v4-pro")
        self.assertEqual(CONFIG._walk_forbidden(generated), [])
        serialized = json.dumps(generated)
        for key in ("primary", "secondary", "prompt_file", '"id"'):
            self.assertNotIn(key, serialized)
        self.assertNotIn("agent", generated)
        self.assertEqual(set(json.loads(self.auth_file.read_text(encoding="utf-8"))), {"nvidia"})

    def test_issue_36_legacy_metadata_never_enters_provider_options(self) -> None:
        issue_agents = self.root / "issue-36-agents"
        issue_agents.mkdir()
        prompt = issue_agents / "prompt.md"
        prompt.write_text("Legacy prompt body\n", encoding="utf-8")
        (issue_agents / "pentest.md").write_text(
            """---
id: pentest
name: pentest
description: Issue 36 regression agent
primary: true
prompt_file: prompt.md
mcp:
  - darkmoon
---
Perform the requested diagnostic.
""",
            encoding="utf-8",
        )
        # prompt.md is a referenced legacy prompt, not a configured agent.
        prompt.rename(issue_agents / "prompt.txt")
        text = (issue_agents / "pentest.md").read_text(encoding="utf-8").replace("prompt.md", "prompt.txt")
        (issue_agents / "pentest.md").write_text(text, encoding="utf-8")
        CONFIG.migrate_agents(issue_agents)
        data, _ = CONFIG.read_agent(issue_agents / "pentest.md", allow_legacy=False)
        self.assertEqual(data["mode"], "primary")
        self.assertFalse(set(data) & CONFIG.LEGACY_AGENT_FIELDS)
        self.assertFalse(set(data.get("options", {})) & CONFIG.REQUEST_LEAK_FIELDS)
        self.assertEqual(data["permission"]["darkmoon_*"], "allow")

    def test_unknown_agent_key_is_rejected_not_forwarded(self) -> None:
        path = self.agents / "aws.md"
        text = path.read_text(encoding="utf-8").replace("mode: subagent\n", "mode: subagent\nopaque_metadata: true\n", 1)
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(CONFIG.ConfigError, "unsupported agent field"):
            CONFIG.migrate_agents(self.agents)

    def test_duplicate_frontmatter_key_is_rejected(self) -> None:
        path = self.agents / "aws.md"
        text = path.read_text(encoding="utf-8").replace("mode: subagent\n", "mode: subagent\nmode: primary\n", 1)
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(CONFIG.ConfigError, "(?s)invalid YAML frontmatter.*duplicate key"):
            CONFIG.validate_agents(self.agents)

    def test_invalid_permission_value_is_reported(self) -> None:
        path = self.agents / "aws.md"
        text = path.read_text(encoding="utf-8").replace("  darkmoon_*: allow\n", "  darkmoon_*:\n    '*': [allow]\n", 1)
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(CONFIG.ConfigError, "invalid nested permission action"):
            CONFIG.validate_agents(self.agents)

    def test_explicit_provider_options_are_preserved_but_metadata_is_rejected(self) -> None:
        path = self.agents / "aws.md"
        original = path.read_text(encoding="utf-8")
        path.write_text(
            original.replace("mode: subagent\n", "mode: subagent\noptions:\n  reasoning_effort: low\n", 1),
            encoding="utf-8",
        )
        CONFIG.migrate_agents(self.agents)
        data, _ = CONFIG.read_agent(path, allow_legacy=False)
        self.assertEqual(data["options"], {"reasoning_effort": "low"})

        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "options:\n  reasoning_effort: low\n", "options:\n  reasoning_effort: low\n  primary: true\n", 1
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CONFIG.ConfigError, "options contains legacy agent metadata"):
            CONFIG.migrate_agents(self.agents)

    def test_missing_legacy_prompt_file_is_reported(self) -> None:
        agents = self.root / "missing-prompt"
        agents.mkdir()
        (agents / "pentest.md").write_text(
            """---
id: pentest
description: Missing prompt test
primary: true
prompt_file: absent.md
---
Body remains present.
""",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CONFIG.ConfigError, "prompt_file does not exist"):
            CONFIG.migrate_agents(agents)

    def test_duplicate_filename_identifier_is_rejected(self) -> None:
        duplicate = self.agents / "ad.md"
        duplicate.write_text(
            """---
id: active-directory
name: active-directory
description: Duplicate Active Directory agent
---
Duplicate prompt.
""",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CONFIG.ConfigError, "duplicate agent identifier"):
            CONFIG.migrate_agents(self.agents)

    def test_provider_modes_are_preserved(self) -> None:
        cases = [
            ({}, "opencode/big-pickle", None),
            (
                {"ANTHROPIC_BASE_URL": "http://anthropic.test", "ANTHROPIC_MODEL": "private-claude"},
                "anthropic/private-claude",
                "anthropic",
            ),
            (
                {
                    "OPENCODE_LOCAL_MODE": "true",
                    "OPENCODE_LOCAL_PROVIDER_ID": "local",
                    "OPENCODE_LOCAL_PROVIDER_NAME": "Local test",
                    "OPENCODE_LOCAL_BASE_URL": "http://local.test/v1",
                    "OPENCODE_LOCAL_MODEL": "test-model",
                    "OPENCODE_LOCAL_API_KEY": "local-test-key",
                },
                "local/test-model",
                "local",
            ),
            (
                {
                    "OPENROUTER_PROVIDER": "openrouter",
                    "OPENROUTER_API_KEY": "cloud-test-key",
                    "OPENCODE_MODEL": "z-ai/glm-5.2",
                },
                "openrouter/z-ai/glm-5.2",
                None,
            ),
        ]
        for env, expected_model, custom_provider in cases:
            with self.subTest(model=expected_model):
                generated = self.apply(env)
                self.assertEqual(generated["model"], expected_model)
                self.assertEqual(generated["small_model"], expected_model)
                if custom_provider:
                    self.assertIn(custom_provider, generated["provider"])

    def test_darkmoon_mcp_tool_names_match_verified_wildcard(self) -> None:
        source = (REPO / "mcp" / "src" / "server.py").read_text(encoding="utf-8")
        functions = re.findall(r"@mcp\.tool\(\)\s*\ndef\s+([a-zA-Z0-9_]+)\(", source)
        self.assertGreaterEqual(len(functions), 10)
        generated = {f"darkmoon_{name}" for name in functions}
        self.assertIn("darkmoon_get_session", generated)
        self.assertIn("darkmoon_execute_command", generated)
        self.assertTrue(all(fnmatch.fnmatchcase(name, "darkmoon_*") for name in generated))

    def test_clean_restart_is_idempotent(self) -> None:
        first = self.apply({"OPENROUTER_PROVIDER": "nvidia", "OPENROUTER_API_KEY": "test", "OPENCODE_MODEL": "z-ai/glm-5.2"})
        first_agents = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.agents.glob("*.md")}
        second = self.apply({"OPENROUTER_PROVIDER": "nvidia", "OPENROUTER_API_KEY": "test", "OPENCODE_MODEL": "z-ai/glm-5.2"})
        second_agents = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.agents.glob("*.md")}
        self.assertEqual(first, second)
        self.assertEqual(first_agents, second_agents)

    def test_existing_volume_gets_targeted_orchestrator_prompt_migration(self) -> None:
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
        new_body = f"""CUSTOM CANONICAL PREFIX
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
PHASE 6 — SUBAGENT SPAWN PROTOCOL — OPENCODE 1.17.13
{fence}
description, prompt, and subagent_type are required.
{fence}
PHASE 7 — TERMINATION & REPORT GENERATION
{fence}
CUSTOM CANONICAL SUFFIX
"""
        (current / "pentest.md").write_text(frontmatter + old_body, encoding="utf-8")
        (canonical / "pentest.md").write_text(frontmatter + new_body, encoding="utf-8")
        CONFIG.migrate_required_prompt_sections(current, canonical)
        _, migrated = CONFIG.read_agent(current / "pentest.md", allow_legacy=False)
        self.assertIn("CUSTOM USER PREFIX", migrated)
        self.assertIn("CUSTOM USER SUFFIX", migrated)
        self.assertIn("filename-derived agent identifiers", migrated)
        self.assertIn("description, prompt, and subagent_type are required", migrated)
        self.assertIn("WordPress -> wordpress", migrated)
        self.assertNotIn("RAW AGENT FILE", migrated)
        self.assertNotIn("cms/lms sub agent", migrated)
        CONFIG.migrate_required_prompt_sections(current, canonical)
        _, restarted = CONFIG.read_agent(current / "pentest.md", allow_legacy=False)
        self.assertEqual(migrated, restarted)
        self.assertNotIn("python-python-flask", restarted)

    def test_dockerfile_pins_the_audited_newer_opencode(self) -> None:
        schema = json.loads((REPO / "conf" / "opencode-schema.json").read_text(encoding="utf-8"))
        dockerfile = (REPO / "Dockerfile.opencode").read_text(encoding="utf-8")
        self.assertIn(f"ARG OPENCODE_COMMIT={schema['commit']}", dockerfile)
        self.assertIn(f"ARG OPENCODE_VERSION={schema['version']}", dockerfile)
        self.assertIn("bun install --frozen-lockfile", dockerfile)
        self.assertNotIn("OPENCODE_VERSION=opencode-darkmoon", dockerfile)

    def test_repository_examples_do_not_reintroduce_legacy_fields(self) -> None:
        CONFIG.validate_config(REPO / "conf" / "opencode.json", REPO / "conf" / "agents")
        mcp_config = json.loads((REPO / "mcp" / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(CONFIG._walk_forbidden(mcp_config), [])
        self.assertTrue(mcp_config["mcp"]["darkmoon"]["enabled"])
        example, prompt = CONFIG.read_agent(REPO / "mcp" / ".opencode" / "agents" / "pentest-web.md", allow_legacy=False)
        self.assertEqual(example["mode"], "primary")
        self.assertEqual(example["permission"], {"*": "deny", "darkmoon_*": "allow"})
        self.assertFalse(set(example) & CONFIG.LEGACY_AGENT_FIELDS)
        self.assertTrue(prompt)

    def test_compose_uses_official_opencode_and_mcp_sidecar(self) -> None:
        import yaml

        production = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
        services = production["services"]
        opencode = services["opencode"]
        mcp = services["darkmoon-mcp"]

        self.assertEqual(opencode["image"], "ghcr.io/anomalyco/opencode:1.18.12")
        self.assertNotIn("build", opencode)
        self.assertEqual(opencode["working_dir"], "/workspace")
        self.assertTrue(any(str(volume).endswith(":/workspace:rw") for volume in opencode["volumes"]))
        self.assertFalse(any(str(volume).startswith("/var/run/docker.sock:") for volume in opencode["volumes"]))
        self.assertIn("DARKMOON_MCP_URL=http://darkmoon-mcp:8000/mcp", opencode["environment"])
        self.assertEqual(opencode["depends_on"]["darkmoon-mcp"]["condition"], "service_healthy")

        self.assertEqual(mcp["build"]["dockerfile"], "Dockerfile.mcp")
        self.assertTrue(any(str(volume).startswith("/var/run/docker.sock:") for volume in mcp["volumes"]))
        self.assertEqual(mcp["environment"]["DOCKER_CONTAINER_NAME"], "darkmoon")

        development = yaml.safe_load((REPO / "docker-compose-dev.yml").read_text(encoding="utf-8"))
        dev_opencode = development["services"]["opencode"]
        self.assertEqual(dev_opencode["build"]["dockerfile"], "Dockerfile.opencode")
        self.assertEqual(dev_opencode["working_dir"], "/workspace")
        self.assertTrue(any(str(volume).endswith(":/workspace:rw") for volume in dev_opencode["volumes"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
