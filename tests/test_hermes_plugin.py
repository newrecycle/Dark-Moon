from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
import yaml

import hermes_registration


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugin"


class HermesPluginTests(unittest.TestCase):
    def test_manifest_and_skills_expose_headless_browser(self) -> None:
        manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.3.0")

        skill_names = {
            path.parent.name for path in (PLUGIN / "skills").glob("*/SKILL.md")
        }
        self.assertEqual(
            skill_names,
            {"darkmoon-pentest", "darkmoon-headless-browser"},
        )

    def test_headless_skill_loads_persona_through_mcp(self) -> None:
        self.assertTrue(
            (REPO / "conf" / "agents" / "headless-browser.md").is_file()
        )
        skill = (
            PLUGIN / "skills" / "darkmoon-headless-browser" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("headless_browser", skill)
        self.assertIn("darkmoon_run_workflow", skill)
        self.assertIn('darkmoon_read_agent("headless-browser")', skill)

    def test_headless_guidance_tracks_the_runtime_browser_contract(self) -> None:
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
        guidance_files = (
            REPO / "conf" / "agents" / "headless-browser.md",
            PLUGIN / "skills" / "darkmoon-headless-browser" / "SKILL.md",
        )
        for path in guidance_files:
            guidance = path.read_text(encoding="utf-8")
            self.assertEqual(
                guidance.count("<!-- DARKMOON_BROWSER_CAPABILITIES_START -->"),
                1,
            )
            self.assertEqual(
                guidance.count("<!-- DARKMOON_BROWSER_CAPABILITIES_END -->"),
                1,
            )
            for mode in contract["modes"]:
                self.assertIn(f"`{mode}`", guidance)
            for wait_until in contract["wait_until"]:
                self.assertIn(f"`{wait_until}`", guidance)
            self.assertIn(
                str(contract["limits"]["max_pages"]), guidance
            )
            self.assertIn(
                str(contract["limits"]["max_requests"]), guidance
            )

    def test_pentest_skill_creates_an_explicit_isolated_session(self) -> None:
        skill = (
            PLUGIN / "skills" / "darkmoon-pentest" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("explicit session boundary", skill)
        self.assertIn("start_pentest_session", skill)
        self.assertIn("resume_pentest_session", skill)
        self.assertIn("exactly `/darkmoon-pentest`", skill)
        self.assertIn("Never turn the invoking Hermes agent", skill)
        self.assertIn("`darkmoon-plugin`", skill)

    def test_plugin_exposes_the_host_side_session_launcher(self) -> None:
        mcp = json.loads((PLUGIN / "mcp.json").read_text(encoding="utf-8"))
        launcher = mcp["mcpServers"]["darkmoon-session"]
        self.assertEqual(launcher["type"], "stdio")
        self.assertEqual(launcher["command"], "bash")
        self.assertIn("darkmoon-session-mcp.sh", launcher["args"][0])
        self.assertTrue((PLUGIN / "session_launcher.py").is_file())
        self.assertTrue((PLUGIN / "session_server.py").is_file())

    def test_registration_cleans_stale_darkmoon_paths_but_keeps_unrelated(self) -> None:
        home = Path(tempfile.mkdtemp())
        try:
            unrelated = "/opt/other-plugin/skills"
            stale = "/home/justin/.hermes/plugins/darkmoon-OLD/skills"
            (home / "config.yaml").write_text(
                yaml.safe_dump(
                    {
                        "skills": {
                            "external_dirs": [unrelated, stale],
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            result = hermes_registration.register_skill_directory(
                PLUGIN, hermes_root=home
            )
            config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
            dirs = config["skills"]["external_dirs"]
            self.assertIn(str((PLUGIN / "skills").resolve()), dirs)
            self.assertIn(unrelated, dirs)
            self.assertNotIn(stale, dirs)
            self.assertTrue(result["changed"])
        finally:
            import shutil

            shutil.rmtree(home, ignore_errors=True)

    def test_unregister_removes_only_darkmoon_entries(self) -> None:
        home = Path(tempfile.mkdtemp())
        try:
            unrelated = "/opt/other-plugin/skills"
            # Simulate an installed darkmoon plugin layout (darkmoon-<hash>).
            installed = Path(tempfile.mkdtemp(prefix="darkmoon-"))
            current = str((installed / "skills").resolve())
            (home / "config.yaml").write_text(
                yaml.safe_dump(
                    {
                        "skills": {
                            "external_dirs": [unrelated, current],
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            result = hermes_registration.unregister_skill_directory(hermes_root=home)
            config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
            dirs = config["skills"]["external_dirs"]
            self.assertIn(unrelated, dirs)
            self.assertNotIn(current, dirs)
            self.assertEqual(result["removed"], [current])
        finally:
            import shutil

            shutil.rmtree(home, ignore_errors=True)

    def test_registration_is_idempotent_on_repeat_runs(self) -> None:
        home = Path(tempfile.mkdtemp())
        try:
            first = hermes_registration.register_skill_directory(PLUGIN, hermes_root=home)
            second = hermes_registration.register_skill_directory(PLUGIN, hermes_root=home)
            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
        finally:
            import shutil

            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
