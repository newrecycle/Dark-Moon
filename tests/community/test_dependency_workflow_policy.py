"""Static safeguards for the Dependabot staging and security merge workflows.

These do not replace a real Dependabot PR acceptance test.
"""
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
    def test_actions_yaml_is_valid_and_shell_is_parseable(self):
        for name in (
            "dependency-staging-validation.yml",
            "dependency-staging-automerge.yml",
            "sync-pro-to-deps.yml",
        ):
            with self.subTest(name=name):
                _text, workflow = read_workflow(name)
                self.assertIsInstance(workflow, dict)
                self.assertIn("on", workflow)
                self.assertIn("jobs", workflow)
                for job_name, job in workflow["jobs"].items():
                    for idx, step in enumerate(job.get("steps", [])):
                        if "run" in step:
                            result = subprocess.run(
                                ["bash", "-n"],
                                input=step["run"],
                                text=True,
                                capture_output=True,
                                check=False,
                            )
                            self.assertEqual(
                                result.returncode, 0,
                                f"{name} job {job_name} step {idx}: {result.stderr}",
                            )

    def test_routine_prs_target_deps_and_security_remains_on_default(self):
        config = yaml.load(
            (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        for update in config["updates"]:
            groups = update.get("groups", {})
            if "routine" in groups:
                self.assertEqual(update.get("target-branch"), "deps")
            if "security" in groups:
                self.assertNotIn("target-branch", update)
                self.assertEqual(
                    groups["security"].get("applies-to"), "security-updates"
                )

    def test_validation_is_read_only_for_pro_and_deps(self):
        text, workflow = read_workflow("dependency-staging-validation.yml")
        self.assertEqual(
            workflow["on"]["pull_request"]["branches"], ["deps", "pro"]
        )
        self.assertEqual(workflow["permissions"]["contents"], "read")
        self.assertEqual(workflow["permissions"]["pull-requests"], "read")
        for required in (
            "dependabot[bot]",
            "github.event.pull_request.head.repo.full_name == github.repository",
            "tests/test_live_push_fixes.py",
            "TEST_JENKINS",
            "Validate Grafana frontend",
        ):
            self.assertIn(required, text)

    def test_privileged_merger_is_exact_and_test_gated(self):
        text, workflow = read_workflow("dependency-staging-automerge.yml")
        self.assertEqual(
            workflow["on"]["workflow_run"]["workflows"],
            ["Dependency staging validation"],
        )
        self.assertEqual(workflow["permissions"]["contents"], "write")
        self.assertEqual(workflow["permissions"]["pull-requests"], "write")
        for required in (
            "dependabot[bot]",
            ".workflow_run.head_sha",
            ".workflow_run.head_repository.full_name",
            '.base.ref == \\"deps\\" or .base.ref == \\"pro\\"',
            "You can disable automated security fix PRs for this repo",
            "gh pr checks",
            "--watch --fail-fast",
            '-f sha="$sha"',
            '-f base=deps -f head=pro',
            "if [[ \"$base\" == 'pro' ]]; then",
        ):
            self.assertIn(required, text)
        self.assertNotIn("actions/checkout", text)
        # All non-security promotions are PRs only; only the security case
        # uses the merge API with pro as the PR's base.
        self.assertNotIn("-f base=pro -f head=deps", text)


if __name__ == "__main__":
    unittest.main()
