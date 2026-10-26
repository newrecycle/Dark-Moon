"""Deterministic report exports from the existing campaign/finding store."""
import io
import json
import re
from html import escape

from api import json_storage as data
from api.live_push import _generate_report_from_db


def markdown(campaign):
    # Keep report behavior in the feature package: current upstream's generator
    # assumes evidence arrays and ignores some legacy fields. Do not change its
    # runtime merely to make the dashboard's exports complete.
    def literal(value):
        return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\n", " ")
    def block(value):
        if isinstance(value, (dict, list)):
            value = "\n".join(str(v) for v in value) if isinstance(value, list) else json.dumps(value, ensure_ascii=False, indent=2)
        value = str(value or "")
        fence = "`" * max(3, 1+max([len(m.group()) for m in re.finditer(r"`+", value)] or [0]))
        return fence+"text\n"+value+"\n"+fence+"\n"
    target = data.load_target(campaign.get("target_id", "")) or {}
    findings = data.load_vulnerabilities(campaign["id"])
    order = {s: i for i, s in enumerate(("critical", "high", "medium", "low", "info"))}
    findings = sorted(findings, key=lambda f: order.get(str(f.get("severity", "info")).lower(), 5))
    lines = ["# "+literal(campaign.get("name") or "Security assessment"), "", "**Campaign:** "+literal(campaign["id"]),
             "**Target:** "+literal(target.get("host") or target.get("ip") or campaign.get("target_id")),
             "**Status:** "+literal(campaign.get("status")), "**Date:** "+literal(campaign.get("date")),
             "", "## Executive summary", "", literal(campaign.get("executive_summary") or "No executive summary recorded."),
             "", "## Findings summary", "", "| Severity | Count |", "|---|---:|"]
    lines += [f"| {severity.upper()} | {sum(str(f.get('severity', 'info')).lower() == severity for f in findings)} |" for severity in order]
    lines += ["", "Confirmation labels are agent observations; validated remediation probes are recorded separately.", ""]
    for index, finding in enumerate(findings, 1):
        lines += [f"## {index}. {literal(finding.get('title') or finding.get('id'))}", "", "| Field | Value |", "|---|---|"]
        for key, label in (("id", "Finding"), ("severity", "Severity"), ("cvss_score", "CVSS score"), ("cvss_vector", "CVSS vector"),
                           ("status", "Status"), ("category", "Category"), ("cve", "CVE"), ("endpoint", "Endpoint"),
                           ("mitre_attack_id", "MITRE ATT&CK"), ("mitre_attack_name", "Technique"), ("iso27001_control", "ISO 27001"),
                           ("discovered_by_agent", "Agent")):
            if finding.get(key) is not None:
                lines.append(f"| {label} | {literal(finding[key])} |")
        lines += ["", "### Description", "", literal(finding.get("description")), "", "### Evidence", ""]
        evidence = finding.get("evidence") or {}
        if isinstance(evidence, dict):
            for key, value in evidence.items():
                if value:
                    lines += ["#### "+literal(key.replace("_", " ").title()), "", block(value)]
        elif evidence:
            lines.append(block(evidence))
        for key in ("evidence_commands", "evidence_logs", "evidence_output", "reproduction_steps"):
            if finding.get(key):
                lines += ["#### "+literal(key.replace("_", " ").title()), "", block(finding[key])]
        lines += ["### Remediation", "", literal(finding.get("remediation") or "No remediation guidance recorded."), ""]
    content = "\n".join(lines)
    report_format = campaign.get("report_format", "standard")
    if report_format in {"h1", "hackerone", "bugcrowd"}:
        platform = "HackerOne" if report_format in {"h1", "hackerone"} else "Bugcrowd"
        submissions = ["# "+platform+" submission dossier", "", "Each issue below uses recorded evidence. Review platform-specific program rules before submission.", ""]
        for finding in findings:
            submissions += ["## "+literal(finding.get("title") or finding.get("id")), "", "### Summary", literal(finding.get("description")),
                            "", "### Asset", literal(finding.get("endpoint")), "", "### Category", literal(finding.get("category")),
                            "", "### Steps to reproduce", block(finding.get("evidence") or finding.get("reproduction_steps") or "No reproduction evidence recorded"),
                            "", "### Impact", literal(finding.get("impact") or "Impact was not recorded separately; refer to the assessment evidence."),
                            "", "### Suggested remediation", literal(finding.get("remediation")), ""]
        content = "\n".join(submissions)+"\n---\n\n"+content
    if report_format == "custom":
        import os
        from pathlib import Path
        from string import Template
        path = os.environ.get("DARKMOON_REPORT_TEMPLATE")
        if not path:
            raise ValueError("Custom report format requires DARKMOON_REPORT_TEMPLATE on the server")
        template = Path(path).read_text(encoding="utf-8")
        if len(template) > 256*1024:
            raise ValueError("Custom report template exceeds 256 KiB")
        content = Template(template).safe_substitute(report=content, campaign_id=literal(campaign["id"]), campaign_name=literal(campaign.get("name")),
                                                      target=literal(target.get("host") or target.get("ip")))
    return content


def pdf(campaign):
    from reportlab.lib import colors
    import reportlab
    from pathlib import Path
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether

    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    # Embed ReportLab's bundled Vera fonts. This keeps spacing predictable on
    # hosts without Helvetica substitutes and supports more Unicode evidence.
    font_dir = Path(reportlab.__file__).parent / "fonts"
    for name, file in (("DMText", "Vera.ttf"), ("DMBold", "VeraBd.ttf"), ("DMItalic", "VeraIt.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_dir / file)))
    for style in styles.byName.values():
        style.fontName = "DMBold" if "Heading" in style.name or style.name == "Title" else "DMText"
    styles.add(ParagraphStyle("Evidence", fontName="Courier", fontSize=8, leading=11,
                              spaceAfter=8, wordWrap="CJK", textColor=colors.HexColor("#34405a")))
    styles["BodyText"].leading = 15
    styles["BodyText"].spaceAfter = 8
    styles["Title"].textColor = colors.HexColor("#17223b")
    styles["Heading1"].textColor = colors.HexColor("#17223b")
    story = []

    def text(value, style="BodyText"):
        # Model/target content is always literal. ReportLab supports an HTML
        # subset, so unescaped evidence would be both unsafe and misleading.
        if isinstance(value, list):
            value = "\n".join(str(item) for item in value)
        elif isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False, indent=2)
        value = str(value or "")
        value = value.replace("\u2011", "-")
        if style == "Evidence":
            story.append(Paragraph(escape(value).replace("\n", "<br/>") or "&#160;", styles[style]))
        else:
            for paragraph in value.splitlines() or [""]:
                story.append(Paragraph(escape(paragraph) or "&#160;", styles[style]))

    text("DARKMOON / COMMUNITY", "Heading2")
    text(campaign.get("name") or "Security assessment", "Title")
    target = data.load_target(campaign.get("target_id", "")) or {}
    text(target.get("host") or target.get("ip") or campaign.get("target_id", ""), "Heading2")
    text(f"Campaign: {campaign['id']}\nStatus: {campaign.get('status', 'unknown')}\nDate: {campaign.get('date', '')}")
    text("Executive summary", "Heading1")
    text(campaign.get("executive_summary") or "No executive summary recorded.")
    findings = data.load_vulnerabilities(campaign["id"])
    order = {s: i for i, s in enumerate(("critical", "high", "medium", "low", "info"))}
    findings.sort(key=lambda f: order.get(str(f.get("severity", "info")).lower(), 5))
    counts = {s: sum(str(f.get("severity", "info")).lower() == s for f in findings) for s in order}
    text("Findings", "Heading1")
    text(" | ".join(f"{s.upper()}: {n}" for s, n in counts.items()))
    text("Confirmation labels reflect agent observations. Remediation validation is recorded separately.")
    for index, finding in enumerate(findings, 1):
        text(f"{index}. {finding.get('title', 'Untitled finding')}", "Heading2")
        text(f"{str(finding.get('severity', 'info')).upper()} | {finding.get('status', 'unconfirmed')} | CVSS {finding.get('cvss_score', 'N/A')}")
        for key, label in (("id", "Finding"), ("category", "Category"), ("endpoint", "Endpoint"),
                           ("mitre_attack_id", "MITRE ATT&CK"), ("mitre_attack_name", "Technique"),
                           ("iso27001_control", "ISO 27001"), ("discovered_by_agent", "Agent")):
            if finding.get(key):
                text(f"{label}: {finding[key]}")
        text(finding.get("description", ""))
        evidence = finding.get("evidence", {})
        if isinstance(evidence, dict):
            for key, value in evidence.items():
                if value:
                    text(str(key).replace("_", " ").title(), "Heading3")
                    text(value, "Evidence")
        elif evidence:
            text(evidence, "Evidence")
        for key in ("evidence_commands", "evidence_output", "reproduction_steps"):
            if finding.get(key):
                text(finding[key], "Evidence")
        text("Remediation", "Heading3")
        text(finding.get("remediation") or "No remediation guidance recorded.")
        story.append(Spacer(1, 5 * mm))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("DMText", 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(18 * mm, 12 * mm, "DarkMoon Community | Assessment evidence")
        canvas.drawRightString(192 * mm, 12 * mm, str(document.page))
        canvas.restoreState()

    document = SimpleDocTemplate(stream, pagesize=(210 * mm, 297 * mm), rightMargin=18 * mm,
                                 leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
                                 title=str(campaign.get("name", "Assessment")), author="DarkMoon Community")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
