"""Documented launch semantics and scope serialization regressions."""

import os
from unittest.mock import patch
import test_community as fixtures
from community.assessment_catalog import catalog
from community.jobs import launch_spec, prompt_for
from community.reports import markdown


class DocumentedLaunchTests(fixtures.Fixture):
    def test_catalog_has_documented_options_and_presets(self):
        options = catalog()
        self.assertEqual(options["noise"], ["stealth", "low", "moderate"])
        self.assertNotIn("info", options["severity_caps"])
        self.assertIn("H1", [v["value"] for v in options["exclude"]])
        self.assertIn("auth-bypass", [v["value"] for v in options["focus"]])
        for preset in options["presets"]:
            launch_spec({"target": "example.invalid", **preset})
        # The removed IDE integration is no longer counted among supported hosts.
        self.assertEqual(len(options["integrations"]), 8)

    def test_scope_serializes_native_flags_without_secret_values(self):
        spec = launch_spec(
            {
                "target": "example.invalid",
                "name": "Review program",
                "targets": ["API:https://api.example.invalid/v2"],
                "out_of_scope": ["payments.example.invalid"],
                "rules": "POC only;no real user data",
                "safe_harbor_applies": "yes",
                "assessment_token_id": "cred_token",
                "severity": "high",
                "noise": "stealth",
            }
        )
        prompt = prompt_for(spec, "camp_preview")
        for text in [
            'PROGRAM="Review program"',
            "TARGETS=API:https://api.example.invalid/v2",
            "OUT=payments.example.invalid",
            'RULES="POC only;no real user data"',
            "SAFE_HARBOR=yes",
            "SEVERITY=high",
            "NOISE=stealth",
        ]:
            self.assertIn(text, prompt)
        self.assertNotIn("cred_token", prompt)
        self.assertNotIn("REMEDIATE=1", prompt)

    def test_invalid_noise_and_multi_severity_are_rejected(self):
        for params in [
            {"noise": "high"},
            {"severity": "high,critical"},
            {"severity": ["high", "critical"]},
            {"severity": "info"},
            {"safe_harbor_applies": "maybe"},
        ]:
            with self.subTest(params=params), self.assertRaises(ValueError):
                launch_spec({"target": "example.invalid", **params})
        self.assertEqual(
            launch_spec({"target": "example.invalid", "format": "hackerone"})["format"],
            "h1",
        )

    def test_api_prefixed_target_obeys_allowlist(self):
        with patch.dict(
            os.environ,
            {"DARKMOON_TARGET_ALLOWLIST": "example.invalid,api.example.invalid"},
        ):
            self.service.launch(
                {
                    "target": "example.invalid",
                    "targets": ["API:https://api.example.invalid/v2"],
                }
            )
            with self.assertRaises(PermissionError):
                self.service.launch(
                    {
                        "target": "example.invalid",
                        "targets": ["API:https://outside.invalid/v2"],
                    }
                )

    def test_lab_origin_is_explicit_in_report(self):
        cid = self.campaign()
        report = markdown(
            self.service.campaign(cid)
            | {"analysis_origin": {"kind": "owned-loopback-lab"}}
        )
        self.assertIn("no LLM-driven assessment", report)
