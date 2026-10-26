"""Regression cases for endpoint credentials, retest verdicts and schedule races."""

import json
import os
from unittest.mock import patch

import test_community as fixtures
from community import configuration, opencode
from community.jobs import Scheduler


class ReviewRegressions(fixtures.Fixture):
    def custom_profile(self, **extra):
        return configuration.profile(
            self.service,
            {
                "name": "Custom endpoint",
                "provider": "custom",
                "mode": "local",
                "model": "one",
                "base_url": "https://endpoint-a.invalid/v1",
                **extra,
            },
        )

    def test_keyless_endpoint_switch_preserves_old_state_and_withholds_key(self):
        key = self.service.vault.save({"name": "A", "secret": "ENDPOINT-A-SECRET"})
        first = self.custom_profile(credential_id=key["id"])
        second = self.custom_profile(base_url="https://endpoint-b.invalid/v1")
        configuration.apply(self.service, first["id"])
        paths = opencode.paths(self.service)
        before = [p.read_bytes() for p in paths]
        with self.assertRaisesRegex(ValueError, "distinct provider id"):
            configuration.apply(self.service, second["id"])
        self.assertEqual(before, [p.read_bytes() for p in paths])
        # A distinct keyless provider remains usable without erasing A's login.
        isolated = self.custom_profile(
            provider="keyless-b", base_url=second["base_url"]
        )
        configuration.apply(self.service, isolated["id"])
        auth = json.loads(paths[1].read_text())
        self.assertEqual(auth["custom"]["key"], "ENDPOINT-A-SECRET")
        self.assertNotIn("keyless-b", auth)

    def test_explicit_key_switch_uses_selected_credential(self):
        for title in ("A", "B"):
            key = self.service.vault.save({"name": title, "secret": "KEY-" + title})
            profile = self.custom_profile(
                credential_id=key["id"],
                base_url="https://" + title.lower() + ".invalid/v1",
            )
            configuration.apply(self.service, profile["id"])
        config, auth, _ = opencode.paths(self.service)
        self.assertEqual(json.loads(auth.read_text())["custom"]["key"], "KEY-B")
        self.assertEqual(
            json.loads(config.read_text())["provider"]["custom"]["options"]["baseURL"],
            "https://b.invalid/v1",
        )

    def test_remote_only_login_prevents_keyless_activation(self):
        profile = self.custom_profile()
        with (
            patch.dict(os.environ, {"DARKMOON_OPENCODE_URL": "http://127.0.0.1:4096"}),
            patch.object(
                opencode, "native", side_effect=[{"connected": ["custom"]}, {}]
            ) as native,
        ):
            with self.assertRaisesRegex(ValueError, "explicit saved API key"):
                configuration.apply(self.service, profile["id"])
        self.assertEqual(native.call_count, 2)
        self.assertFalse(any(p.exists() for p in opencode.paths(self.service)))

    def test_live_keyless_provider_can_be_reapplied_to_same_endpoint(self):
        profile = self.custom_profile()
        current = {
            "provider": {"custom": {"options": {"baseURL": profile["base_url"]}}}
        }

        def native(method, path, body=None):
            if path == "/provider":
                return {"connected": ["custom"]}
            if method == "PATCH":
                current.update(body)
            return current

        with (
            patch.dict(os.environ, {"DARKMOON_OPENCODE_URL": "http://127.0.0.1:4096"}),
            patch.object(opencode, "native", side_effect=native),
        ):
            result = configuration.apply(self.service, profile["id"])
        self.assertFalse(result["restart_required"])

    def test_inline_login_also_prevents_keyless_activation(self):
        profile = self.custom_profile()
        config = opencode.paths(self.service)[0]
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            json.dumps(
                {"provider": {"custom": {"options": {"apiKey": "INLINE-SECRET"}}}}
            )
        )
        before = config.read_bytes()
        with self.assertRaisesRegex(ValueError, "already has authentication"):
            configuration.apply(self.service, profile["id"])
        self.assertEqual(config.read_bytes(), before)

    def test_local_proposals_never_upgrade_absence_to_fixed(self):
        cid = self.campaign()
        finding = self.service.campaign(cid)["findings"][0]
        for proposal_campaign in (cid, "camp_unrelated"):
            with self.subTest(proposal_campaign=proposal_campaign):
                self.service.store.save(
                    "retests",
                    {
                        "id": "retest_demo",
                        "status": "running",
                        "base_campaign_id": cid,
                        "campaign_id": "camp_new",
                        "before_ids": [finding["id"]],
                    },
                )
                snapshot = {
                    "campaigns": [],
                    "findings": [],
                    "remediations": [
                        {
                            "id": "rem_demo",
                            "finding_id": finding["id"],
                            "campaign_id": proposal_campaign,
                            "status": "validated",
                        }
                    ],
                }
                with (
                    patch.object(self.service, "snapshot", return_value=snapshot),
                    patch(
                        "community.operations.data.load_campaign",
                        return_value={"status": "completed"},
                    ),
                    patch(
                        "community.operations.data.load_vulnerabilities",
                        side_effect=lambda c: [finding] if c == cid else [],
                    ),
                ):
                    self.service.operations.tick()
                result = self.service.store.get("retests", "retest_demo")
                self.assertEqual(result["verdicts"][0]["verdict"], "not_observed")
                self.assertNotIn("fixed", result["verdicts_summary"])

    def test_schedule_delete_during_launch_cannot_resurrect_record(self):
        def launch(spec, **kw):
            self.service.store.update(lambda s: s["schedules"].pop(item["id"]))
            return {"id": "fake-job"}

        scheduler = Scheduler(self.service.store, launch)
        item = scheduler.create(
            {"target": "example.invalid", "next_run": "2020-01-01T00:00:00Z"}
        )
        scheduler.tick()
        self.assertIsNone(self.service.store.get("schedules", item["id"]))

    def test_schedule_pause_during_launch_survives_success_and_failure(self):
        for fails in (False, True):
            with self.subTest(launch_fails=fails):

                def launch(spec, **kw):
                    scheduler.set_enabled(item["id"], False)
                    if fails:
                        raise ValueError("Launcher unavailable")
                    return {"id": "fake-job"}

                scheduler = Scheduler(self.service.store, launch)
                item = scheduler.create(
                    {"target": "example.invalid", "next_run": "2020-01-01T00:00:00Z"}
                )
                scheduler.tick()
                current = self.service.store.get("schedules", item["id"])
                self.assertFalse(current["enabled"])
                self.assertEqual(
                    current["last_disposition"], "failed" if fails else "queued"
                )

    def test_pause_after_snapshot_prevents_claim_and_launch(self):
        scheduler = self.service.scheduler
        item = scheduler.create(
            {"target": "example.invalid", "next_run": "2020-01-01T00:00:00Z"}
        )
        read_items = self.service.store.items

        def items(collection):
            snapshot = read_items(collection)
            if collection == "schedules":
                scheduler.set_enabled(item["id"], False)
            return snapshot

        with (
            patch.object(self.service.store, "items", side_effect=items),
            patch.object(scheduler, "launch") as launch,
        ):
            scheduler.tick()
        launch.assert_not_called()
        self.assertFalse(self.service.store.get("schedules", item["id"])["enabled"])
