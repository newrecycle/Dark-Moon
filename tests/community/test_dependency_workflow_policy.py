"""Guard direct-to-pro dependency review against silent automatic promotion."""
from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def read_workflow(name):
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return text, yaml.load(text, Loader=yaml.BaseLoader)


class DependabotWorkflowPolicy(unittest.TestCase):
    def test_dependency_workflows_parse_and_shell_is_valid(self):
        for name in ("dependency-validation.yml", "dependency-automation-regressions.yml"):
            with self.subTest(name=name):
                _text, workflow = read_workflow(name)
                self.assertIsInstance(workflow, dict)
                self.assertIn("on", workflow)
                self.assertIn("jobs", workflow)
                for job in workflow["jobs"].values():
                    for step in job.get("steps", []):
                        if "run" in step:
                            result = subprocess.run(
                                ["bash", "-n"], input=step["run"], text=True,
                                capture_output=True, check=False,
                            )
                            self.assertEqual(result.returncode, 0, result.stderr)

    def test_single_default_branch_entry_per_ecosystem_with_both_groups(self):
        config = yaml.load(
            (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        ecosystems = set()
        for update in config["updates"]:
            ecosystem = update["package-ecosystem"]
            self.assertNotIn(ecosystem, ecosystems, "Overlapping update entries")
            ecosystems.add(ecosystem)
            self.assertNotIn("target-branch", update)
            self.assertEqual(update["open-pull-requests-limit"], "1")
            self.assertEqual(update["groups"]["routine"]["applies-to"], "version-updates")
            self.assertEqual(update["groups"]["security"]["applies-to"], "security-updates")
            for directory in update["directories"]:
                root = ROOT / directory.lstrip("/")
                if ecosystem == "npm":
                    self.assertTrue((root / "package.json").is_file(), directory)
                elif ecosystem == "pip":
                    self.assertTrue((root / "requirements.txt").is_file(), directory)
        self.assertEqual(ecosystems, {"github-actions", "pip", "npm"})
        npm = next(u for u in config["updates"] if u["package-ecosystem"] == "npm")
        self.assertIn("/integrations/upstream/jenkins", npm["directories"])

    def test_validation_is_read_only_and_runs_for_pro(self):
        text, workflow = read_workflow("dependency-validation.yml")
        self.assertEqual(workflow["on"]["pull_request"]["branches"], ["pro"])
        self.assertEqual(workflow["permissions"], {"contents": "read", "pull-requests": "read"})
        for required in (
            "dependabot[bot]",
            "github.event.pull_request.head.repo.full_name == github.repository",
            "github.event.pull_request.base.ref == 'pro'",
            "tests/test_live_push_fixes.py",
            "TEST_JENKINS",
            "Validate Grafana frontend",
        ):
            self.assertIn(required, text)
        self.assertNotIn("secrets.", text)

    def test_staging_and_privileged_dependency_mergers_are_retired(self):
        for name in ("sync-pro-to-deps.yml", "dependency-staging-automerge.yml",
                     "dependency-staging-validation.yml"):
            self.assertFalse((WORKFLOWS / name).exists(), name)
        for path in WORKFLOWS.glob("dependency-*.yml"):
            text, workflow = read_workflow(path.name)
            self.assertNotIn("workflow_run", workflow["on"])
            self.assertNotIn("write", workflow.get("permissions", {}).values())
            for forbidden in ("/merge", "gh pr merge", "refs/heads/deps", "base=deps", "head=deps"):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
