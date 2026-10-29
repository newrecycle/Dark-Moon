"""Reports distinguish recorded impact/disposition from remediation proof."""
import io

from pypdf import PdfReader
import test_community as fixtures
from api import json_storage as data
from community.reports import markdown, pdf, plan


class ReportRoadmap(fixtures.Fixture):
    def test_markdown_and_pdf_keep_dispositions_out_of_active_roadmap(self):
        cid = self.campaign()
        rows = [{"id": "active_low", "campaign_id": cid, "severity": "low", "status": "confirmed", "impact": "Recorded limited impact"},
                {"id": "active_critical", "campaign_id": cid, "severity": "critical", "status": "unconfirmed", "remediation": "Parameterize | validate"}]
        rows += [{"id": "excluded_" + status, "campaign_id": cid, "severity": "critical", "status": status}
                 for status in ("false_positive", "accepted_risk", "remediated", "resolved")]
        data.save_vulnerabilities(cid, rows)
        active, counts = plan(rows)
        self.assertEqual([f["id"] for f in active], ["active_critical", "active_low"])
        self.assertEqual(counts["accepted_risk"], 1)
        campaign = data.load_campaign(cid)
        content = markdown(campaign)
        roadmap = content.split("## Remediation roadmap", 1)[1].split("## 1.", 1)[0]
        self.assertNotIn("excluded_", roadmap)
        self.assertIn("Parameterize \\| validate", roadmap)
        self.assertIn("Recorded limited impact", content)
        text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf(campaign))).pages)
        for report in (content, text):
            self.assertIn("Disposition and coverage", report)
            self.assertIn("Remediation roadmap", report)
            self.assertIn("Recorded impact", report)
            self.assertIn("not proof of deployment", report)
            self.assertIn("Recorded limited impact", report)
        pdf_roadmap = text.split("Remediation roadmap", 1)[1].split("1. Untitled finding", 1)[0]
        self.assertIn("active_critical", pdf_roadmap)
        self.assertNotIn("excluded_accepted_risk", pdf_roadmap)

    def test_empty_report_does_not_claim_validated_fix_or_invent_impact(self):
        cid = self.campaign()
        data.save_vulnerabilities(cid, [])
        campaign = data.load_campaign(cid)
        for report in (markdown(campaign), "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf(campaign))).pages)):
            self.assertIn("No active findings are recorded.", report)
            self.assertIn("not a clean bill of health", report)
