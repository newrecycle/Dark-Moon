"""Packaged dashboard contracts; these checks do not execute Splunk's SPL."""
import configparser
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "darkmoon/default"


class DashboardPackageContracts(unittest.TestCase):
    def config(self, name):
        result = configparser.ConfigParser(interpolation=None, strict=True)
        result.read(DEFAULT / name)
        return result

    def test_finding_views_and_drilldown_preserve_campaign_identity(self):
        views = {p.name: ET.parse(p) for p in (DEFAULT / "data/ui/views").glob("*.xml")}
        for name, tree in views.items():
            for query in tree.findall(".//query"):
                text = query.text or ""
                self.assertNotIn("dedup finding_id", text, name)
                self.assertNotIn("dc(finding_id)", text, name)
                # Every query-valued UI token must apply Splunk's string filter.
                for token in re.findall(r"\$([^$]+)\$", text):
                    self.assertTrue(token.endswith("|s"), (name, token))
        finding = views["darkmoon_findings.xml"]
        self.assertTrue(finding.findall(".//set[@token='sel_finding_key']"))
        queries = [q.text for q in finding.findall(".//query")]
        self.assertTrue(any("finding_key=$sel_finding_key|s$" in q for q in queries))
        for query in queries:
            if "severity=$sev|s$" in query:
                self.assertLess(query.index("dedup finding_key"), query.index("severity=$sev|s$"))

    def test_retest_and_proposal_views_do_not_require_optional_titles(self):
        tree = ET.parse(DEFAULT / "data/ui/views/darkmoon_remediation.xml")
        queries = [q.text for q in tree.findall(".//query")]
        self.assertTrue(any("sourcetype=darkmoon:remediation" in q and "proposal_id" in q for q in queries))
        self.assertTrue(any("record_type=lifecycle" in q and "run_id" in q for q in queries))
        self.assertTrue(any("dedup retest_id finding_key" in q and "current_finding_id" in q for q in queries))
        self.assertFalse(any(re.search(r"\bby\s+finding_id\s+title", q) for q in queries))
        props = self.config("props.conf")
        self.assertIn("campaign_id", props["darkmoon:finding"]["eval-finding_key"])
        self.assertIn("new_campaign_id", props["darkmoon:retest"]["eval-finding_key"])
        self.assertIn("not_observed", props["darkmoon:retest"]["description"])

    def test_zero_denominator_and_observation_counts_are_explicit(self):
        source = (DEFAULT / "data/ui/views/darkmoon_soc_overview.xml").read_text()
        self.assertIn("null()", source)
        self.assertIn("Accepted and unknown states remain open", source)
        self.assertIn('NOT status IN ("false_positive","remediated","resolved","closed","fixed")', source)
        self.assertIn("dedup retest_id finding_key", source)
        campaigns = (DEFAULT / "data/ui/views/darkmoon_campaigns.xml").read_text()
        self.assertIn("timechart dc(campaign_id)", campaigns)
        self.assertNotIn("timechart count as campaigns", campaigns)
        searches = self.config("savedsearches.conf")
        for section in searches.values():
            if "action.darkmoon_campaign" in section:
                self.assertEqual(section["disabled"], "1")
                self.assertEqual(section["action.darkmoon_campaign.param.dry_run"], "1")

    def test_finding_scope_controls_and_examples_are_wired_without_changing_default(self):
        settings = self.config("alert_actions.conf")["darkmoon_campaign"]
        self.assertEqual(settings["param.retest_scope"], "target")
        form = ET.parse(DEFAULT / "data/ui/alerts/darkmoon_campaign.html")
        names = {element.attrib.get("name") for element in form.iter()}
        for key in ("retest_scope", "campaign_id", "finding_id"):
            self.assertIn("action.darkmoon_campaign.param." + key, names)
        searches = self.config("savedsearches.conf")
        for name in ("Darkmoon - Exploited finding -> auto retest", "Darkmoon - Regression verdict -> retest"):
            self.assertEqual(searches[name]["action.darkmoon_campaign.param.retest_scope"], "finding")
            self.assertEqual(searches[name]["disabled"], "1")
            self.assertEqual(searches[name]["action.darkmoon_campaign.param.dry_run"], "1")
        self.assertIn("finding_campaign_id", searches["Darkmoon - Regression verdict -> retest"]["search"])

    @unittest.skipIf(os.name == "nt", "GNU tar package recipe is verified on Linux")
    def test_actual_package_contains_views_and_guards_without_local_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "splunk"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns("dist", "__pycache__"))
            private = root / "darkmoon/local"
            private.mkdir()
            (private / "passwords.conf").write_text("PRIVATE-PACKAGE-SECRET")
            cache = root / "darkmoon/bin/__pycache__"
            cache.mkdir(exist_ok=True)
            (cache / "private.pyc").write_text("PRIVATE-PACKAGE-SECRET")
            result = subprocess.run(["bash", str(root / "scripts/package.sh")], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            archives = list((root / "dist").glob("*.tar.gz"))
            self.assertEqual(len(archives), 1)
            with tarfile.open(archives[0]) as archive:
                names = set(archive.getnames())
                for required in ("default/data/ui/views/darkmoon_remediation.xml", "default/data/ui/views/darkmoon_setup.xml",
                                 "appserver/static/setup.js", "bin/darkmoon_campaign.py", "README/darkmoon.conf.spec"):
                    self.assertIn("darkmoon/" + required, names)
                for item in archive:
                    self.assertNotIn("local", Path(item.name).parts)
                    self.assertNotIn("__pycache__", Path(item.name).parts)
                    if item.isfile():
                        self.assertNotIn(b"PRIVATE-PACKAGE-SECRET", archive.extractfile(item).read())


if __name__ == "__main__":
    unittest.main()
