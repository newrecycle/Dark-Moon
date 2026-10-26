#!/usr/bin/env python3
"""
Generate the Darkmoon "Security Posture" Grafana dashboards (FREE path, Infinity
datasource). Emits two variants from one spec:

  dashboards/darkmoon-security-posture.json       PRODUCTION — point at your
                                                  Darkmoon Pro/Community REST API
                                                  (real /api/v1/... paths + query
                                                  filters). Import + set the
                                                  `darkmoon_url` variable.

  dashboards/darkmoon-security-posture-demo.json  DEMO — self-contained preview
                                                  wired to the bundled synthetic
                                                  Demo Shop fixtures on GitHub raw
                                                  (static .json files). Renders
                                                  instantly with no backend; used
                                                  for the live Grafana Cloud
                                                  screenshots.

Both mirror the Angular front-app views (dashboard, campaigns, vulnerabilities,
infra, pull-request, report, history) and NEVER render evidence / raw / report
bodies — metadata only. Panel colors match the Angular badge palette.
"""
import copy
import json
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "dashboards")

# raw GitHub base for the demo (static fixtures, query strings ignored)
DEMO_BASE = "https://raw.githubusercontent.com/ASCIT31/darkmoon-grafana/main/fixtures"
DS = {"type": "yesoreyeram-infinity-datasource", "uid": "${darkmoon_ds}"}

# ---- Angular badge palette (see INTEGRATIONS-PHASE2-PLAN §3.B.3) -------------
SEV_COLORS = {"critical": "#ef4444", "high": "#f97316", "medium": "#eab308",
              "low": "#22c55e", "info": "#3b82f6", "none": "#d1d5db"}
STATUS_COLORS = {"exploited": "#f97316", "confirmed": "#ef4444",
                 "unconfirmed": "#14b8a6", "remediated": "#22c55e",
                 "false_positive": "#3b82f6"}
PR_COLORS = {"open": "#22c55e", "merged": "#a855f7", "draft": "#9ca3af",
             "proposed": "#6366f1", "closed": "#9ca3af", "error": "#ef4444"}
VERDICT_COLORS = {"fixed": "#22c55e", "still_present": "#ef4444",
                  "regressed": "#b91c1c", "new": "#f97316"}
CAMP_COLORS = {"completed": "#22c55e", "running": "#eab308",
               "stopped": "#9ca3af", "aborted": "#9ca3af", "failed": "#ef4444"}


def infinity_target(url, root, columns, fmt="table", refid="A", ftype="json"):
    return {
        "refId": refid,
        "datasource": DS,
        "type": ftype,
        "source": "url",
        "parser": "backend",
        "url": url,
        "url_options": {"method": "GET", "data": ""},
        "root_selector": root,
        "columns": columns,
        "filters": [],
        "format": fmt,
    }


def col(sel, text, typ="string"):
    return {"selector": sel, "text": text, "type": typ}


def mappings_from(colormap):
    return [{"type": "value", "options": {
        k: {"color": v, "index": i} for i, (k, v) in enumerate(colormap.items())}}]


PANELS = []
_id = [0]


def nid():
    _id[0] += 1
    return _id[0]


def panel(title, gridpos, ptype, targets, fieldcfg=None, options=None,
          transformations=None, description=""):
    p = {
        "id": nid(),
        "title": title,
        "type": ptype,
        "datasource": DS,
        "gridPos": gridpos,
        "targets": targets,
        "description": description,
        "fieldConfig": fieldcfg or {"defaults": {}, "overrides": []},
        "options": options or {},
    }
    if transformations:
        p["transformations"] = transformations
    return p


def gp(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def row(title, y):
    return {"id": nid(), "type": "row", "title": title, "collapsed": False,
            "gridPos": gp(0, y, 24, 1), "panels": []}


# ---------------------------------------------------------------------------
# Build the panel list against a base url + suffix (production="" / demo=".json")
# ---------------------------------------------------------------------------
def build_panels(sfx):
    B = "${darkmoon_url}/api/v1"
    P = []

    # ============ ROW: OVERVIEW (mirrors DashboardComponent) ============
    P.append(row("Security posture — overview", 0))

    ov_url = f"{B}/dashboard/overview{sfx}"
    # KPI counts
    P.append(panel(
        "Estate", gp(0, 1, 6, 4), "stat",
        [infinity_target(ov_url, "", [
            col("projects_count", "Projects", "number"),
            col("targets_count", "Targets", "number"),
            col("campaigns_count", "Campaigns", "number"),
            col("total_vulnerabilities", "Findings", "number")])],
        fieldcfg={"defaults": {"color": {"mode": "fixed", "fixedColor": "#3b82f6"}},
                  "overrides": []},
        options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                 "orientation": "horizontal", "textMode": "value_and_name",
                 "colorMode": "none", "graphMode": "none"},
        description="Projects / Targets / Campaigns / total Findings across the estate."))

    # Active campaigns (count of running)
    P.append(panel(
        "Active campaigns", gp(6, 1, 3, 4), "stat",
        [infinity_target(f"{B}/campaigns{sfx}", "data",
                         [col("id", "id"), col("status", "status")], refid="A")],
        options={"reduceOptions": {"calcs": ["count"], "fields": "/^id$/"},
                 "colorMode": "value", "graphMode": "none", "textMode": "value"},
        fieldcfg={"defaults": {"color": {"mode": "fixed", "fixedColor": CAMP_COLORS["running"]}},
                  "overrides": []},
        transformations=[{"id": "filterByValue", "options": {"type": "include",
            "match": "all", "filters": [{"fieldName": "status", "config": {
                "id": "equal", "options": {"value": "running"}}}]}}],
        description="Campaigns currently running."))

    # Critical / High / Exploited / Confirmed
    for i, (label, sel, cmap, key) in enumerate([
            ("Critical", "critical", SEV_COLORS, "critical"),
            ("High", "high", SEV_COLORS, "high")]):
        P.append(panel(
            label, gp(9 + i * 3, 1, 3, 4), "stat",
            [infinity_target(ov_url, "severity_distribution",
                             [col(sel, label, "number")])],
            fieldcfg={"defaults": {"color": {"mode": "fixed",
                      "fixedColor": cmap[key]}}, "overrides": []},
            options={"reduceOptions": {"calcs": ["lastNotNull"]},
                     "colorMode": "background", "graphMode": "none", "textMode": "value_and_name"},
            description=f"{label}-severity findings across the estate."))
    P.append(panel(
        "Exploited", gp(15, 1, 3, 4), "stat",
        [infinity_target(ov_url, "status_distribution", [col("exploited", "Exploited", "number")])],
        fieldcfg={"defaults": {"color": {"mode": "fixed", "fixedColor": STATUS_COLORS["exploited"]}},
                  "overrides": []},
        options={"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background",
                 "graphMode": "none", "textMode": "value_and_name"},
        description="Findings Darkmoon actively EXPLOITED (proof-of-impact)."))
    P.append(panel(
        "Confirmed", gp(18, 1, 3, 4), "stat",
        [infinity_target(ov_url, "status_distribution", [col("confirmed", "Confirmed", "number")])],
        fieldcfg={"defaults": {"color": {"mode": "fixed", "fixedColor": STATUS_COLORS["confirmed"]}},
                  "overrides": []},
        options={"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background",
                 "graphMode": "none", "textMode": "value_and_name"},
        description="Findings confirmed present (not yet exploited)."))

    # Remediation rate gauge (remediated / total * 100) — single query, one row
    P.append(panel(
        "Remediation rate", gp(21, 1, 3, 4), "gauge",
        [infinity_target(ov_url, "", [
            col("status_distribution.remediated", "remediated", "number"),
            col("total_vulnerabilities", "total", "number")])],
        fieldcfg={"defaults": {"unit": "percent", "min": 0, "max": 100,
                  "thresholds": {"mode": "absolute", "steps": [
                      {"color": "red", "value": None}, {"color": "orange", "value": 25},
                      {"color": "yellow", "value": 50}, {"color": "green", "value": 75}]}},
                  "overrides": []},
        options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "rate"},
                 "showThresholdLabels": False, "showThresholdMarkers": True},
        transformations=[
            {"id": "calculateField", "options": {"mode": "binary", "alias": "ratio",
                "binary": {"left": "remediated", "operator": "/", "right": "total"},
                "replaceFields": True}},
            {"id": "calculateField", "options": {"mode": "binary", "alias": "rate",
                "binary": {"left": "ratio", "operator": "*", "right": "100"},
                "replaceFields": True}}],
        description="Share of findings marked remediated. (MTTR is intentionally NOT "
                    "shown: the data model carries no per-finding open/close timestamps, "
                    "so it cannot be computed honestly.)"))

    # Findings over time by severity (mirrors VulnEvolutionChart) — from /campaigns
    camp_ts = infinity_target(f"{B}/campaigns{sfx}", "data", [
        col("date", "time", "timestamp"),
        col("stats.critical", "critical", "number"),
        col("stats.high", "high", "number"),
        col("stats.medium", "medium", "number"),
        col("stats.low", "low", "number")], fmt="table")
    P.append(panel(
        "Findings over time (by severity)", gp(0, 5, 16, 9), "timeseries", [camp_ts],
        fieldcfg={"defaults": {"custom": {"drawStyle": "line", "lineWidth": 2,
                  "fillOpacity": 15, "showPoints": "always", "pointSize": 6,
                  "spanNulls": True, "stacking": {"mode": "normal", "group": "A"}}},
                  "overrides": [
            {"matcher": {"id": "byName", "options": "critical"},
             "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": SEV_COLORS["critical"]}}]},
            {"matcher": {"id": "byName", "options": "high"},
             "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": SEV_COLORS["high"]}}]},
            {"matcher": {"id": "byName", "options": "medium"},
             "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": SEV_COLORS["medium"]}}]},
            {"matcher": {"id": "byName", "options": "low"},
             "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": SEV_COLORS["low"]}}]}]},
        options={"legend": {"displayMode": "list", "placement": "bottom"},
                 "tooltip": {"mode": "multi"}},
        description="Per-campaign finding counts by severity over time (mirrors the "
                    "Angular Vulnerability Evolution chart)."))

    # Severity distribution (bar gauge)
    P.append(panel(
        "Severity distribution", gp(16, 5, 4, 9), "bargauge",
        [infinity_target(ov_url, "severity_distribution", [
            col("critical", "Critical", "number"), col("high", "High", "number"),
            col("medium", "Medium", "number"), col("low", "Low", "number"),
            col("info", "Info", "number")])],
        fieldcfg={"defaults": {"color": {"mode": "fixed"}}, "overrides": [
            {"matcher": {"id": "byName", "options": n}, "properties": [
                {"id": "color", "value": {"mode": "fixed", "fixedColor": SEV_COLORS[k]}}]}
            for n, k in [("Critical", "critical"), ("High", "high"), ("Medium", "medium"),
                         ("Low", "low"), ("Info", "info")]]},
        options={"orientation": "horizontal", "displayMode": "gradient",
                 "reduceOptions": {"calcs": ["lastNotNull"]}},
        description="Findings by severity (colors match the app badges)."))

    # Status distribution (pie — Grafana adds what Angular tiles lack)
    P.append(panel(
        "Status distribution", gp(20, 5, 4, 9), "piechart",
        [infinity_target(ov_url, "status_distribution", [
            col("exploited", "Exploited", "number"), col("confirmed", "Confirmed", "number"),
            col("unconfirmed", "Unconfirmed", "number"), col("remediated", "Remediated", "number")])],
        fieldcfg={"defaults": {"color": {"mode": "fixed"}}, "overrides": [
            {"matcher": {"id": "byName", "options": n}, "properties": [
                {"id": "color", "value": {"mode": "fixed", "fixedColor": STATUS_COLORS[k]}}]}
            for n, k in [("Exploited", "exploited"), ("Confirmed", "confirmed"),
                         ("Unconfirmed", "unconfirmed"), ("Remediated", "remediated")]]},
        options={"reduceOptions": {"calcs": ["lastNotNull"]}, "pieType": "donut",
                 "legend": {"displayMode": "list", "placement": "right"}},
        description="Findings by exploitation/remediation status."))

    # ============ ROW: CAMPAIGNS & TARGETS ============
    P.append(row("Campaigns & targets", 14))

    # Last campaigns table (drill -> campaign)
    camp_link = {"title": "Drill into campaign ${__data.fields.id}",
                 "url": "d/darkmoon-posture/?var-campaign_id=${__data.fields.id}&${__url_time_range}"}
    P.append(panel(
        "Last campaigns", gp(0, 15, 12, 9), "table",
        [infinity_target(f"{B}/campaigns{sfx}", "data", [
            col("id", "Campaign"), col("target_id", "Target"),
            col("date", "Date", "timestamp"), col("status", "Status"),
            col("overall_risk", "Risk"), col("stats.total_findings", "Findings", "number"),
            col("stats.critical", "Crit", "number"), col("stats.high", "High", "number")])],
        fieldcfg={"defaults": {}, "overrides": [
            {"matcher": {"id": "byName", "options": "Risk"}, "properties": [
                {"id": "mappings", "value": mappings_from(SEV_COLORS)},
                {"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
            {"matcher": {"id": "byName", "options": "Status"}, "properties": [
                {"id": "mappings", "value": mappings_from(CAMP_COLORS)},
                {"id": "custom.cellOptions", "value": {"type": "color-text"}}]},
            {"matcher": {"id": "byName", "options": "Campaign"}, "properties": [
                {"id": "links", "value": [camp_link]}]}]},
        options={"showHeader": True, "sortBy": [{"displayName": "Date", "desc": True}]},
        description="Recent campaigns. Click a campaign id to drill down."))

    # Targets at risk table (drill -> target)
    tgt_link = {"title": "Drill into target ${__data.fields.id}",
                "url": "d/darkmoon-posture/?var-target_id=${__data.fields.id}&${__url_time_range}"}
    P.append(panel(
        "Targets at risk", gp(12, 15, 12, 9), "table",
        [infinity_target(f"{B}/targets{sfx}", "data", [
            col("id", "id"), col("host", "Host"), col("ip", "IP"),
            col("risk_level", "Risk"), col("status", "Status"),
            col("open_vuln", "Open", "number")])],
        fieldcfg={"defaults": {}, "overrides": [
            {"matcher": {"id": "byName", "options": "Risk"}, "properties": [
                {"id": "mappings", "value": mappings_from(SEV_COLORS)},
                {"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
            {"matcher": {"id": "byName", "options": "Host"}, "properties": [
                {"id": "links", "value": [tgt_link]}]},
            {"matcher": {"id": "byName", "options": "id"},
             "properties": [{"id": "custom.hidden", "value": True}]}]},
        options={"showHeader": True, "sortBy": [{"displayName": "Open", "desc": True}]},
        description="Targets at critical/high/medium risk. Click a host to drill down."))

    # ============ ROW: VULNERABILITIES ============
    P.append(row("Vulnerabilities", 24))

    vuln_url = f"{B}/vulnerabilities{sfx}"
    vuln_link = {"title": "Finding detail ${__data.fields.id}",
                 "url": "d/darkmoon-posture/?var-vuln_id=${__data.fields.id}&${__url_time_range}"}
    P.append(panel(
        "Vulnerabilities", gp(0, 25, 24, 10), "table",
        [infinity_target(vuln_url, "data", [
            col("id", "id"), col("title", "Title"), col("severity", "Severity"),
            col("status", "Status"), col("category", "Category"), col("cve", "CVE"),
            col("cvss_score", "CVSS", "number"), col("mitre_attack_id", "ATT&CK"),
            col("endpoint", "Endpoint")])],
        fieldcfg={"defaults": {"custom": {"filterable": True}}, "overrides": [
            {"matcher": {"id": "byName", "options": "Severity"}, "properties": [
                {"id": "mappings", "value": mappings_from(SEV_COLORS)},
                {"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
            {"matcher": {"id": "byName", "options": "Status"}, "properties": [
                {"id": "mappings", "value": mappings_from(STATUS_COLORS)},
                {"id": "custom.cellOptions", "value": {"type": "color-text"}}]},
            {"matcher": {"id": "byName", "options": "Title"}, "properties": [
                {"id": "links", "value": [vuln_link]}]},
            {"matcher": {"id": "byName", "options": "id"},
             "properties": [{"id": "custom.hidden", "value": True}]}]},
        options={"showHeader": True, "footer": {"show": True, "reducer": ["count"],
                 "fields": "/^Title$/"}},
        description="All findings (safe fields only — NO description, NO evidence). "
                    "Every column is filterable (click the column header funnel to "
                    "filter by severity / status / category / campaign). "
                    "Click a title to drill into the finding."))

    # MITRE ATT&CK breakdown
    P.append(panel(
        "MITRE ATT&CK", gp(0, 35, 8, 8), "barchart",
        [infinity_target(f"{B}/vulnerabilities{sfx}", "data", [
            col("mitre_attack_name", "Technique"), col("id", "id")])],
        transformations=[{"id": "groupBy", "options": {"fields": {
            "Technique": {"operation": "groupby"},
            "id": {"operation": "aggregate", "aggregations": ["count"]}}}}],
        fieldcfg={"defaults": {"color": {"mode": "fixed", "fixedColor": "#6366f1"}}, "overrides": []},
        options={"orientation": "horizontal", "xTickLabelRotation": 0,
                 "legend": {"showLegend": False}},
        description="Findings grouped by MITRE ATT&CK technique."))

    # Category breakdown
    P.append(panel(
        "Category breakdown", gp(8, 35, 8, 8), "barchart",
        [infinity_target(f"{B}/vulnerabilities{sfx}", "data", [
            col("category", "Category"), col("id", "id")])],
        transformations=[{"id": "groupBy", "options": {"fields": {
            "Category": {"operation": "groupby"},
            "id": {"operation": "aggregate", "aggregations": ["count"]}}}}],
        fieldcfg={"defaults": {"color": {"mode": "fixed", "fixedColor": "#0ea5e9"}}, "overrides": []},
        options={"orientation": "horizontal", "legend": {"showLegend": False}},
        description="Findings grouped by vulnerability category."))

    # Technology breakdown (flatten targets.technologies via JSONata)
    P.append(panel(
        "Technologies", gp(16, 35, 8, 8), "table",
        [infinity_target(f"{B}/targets{sfx}", "data.technologies", [
            col("name", "Technology"), col("version", "Version"),
            col("category", "Category")])],
        options={"showHeader": True},
        description="Technology stack discovered across targets."))

    # ============ ROW: REMEDIATION / RETEST (drill-down chain end) ============
    P.append(row("Remediation & retest", 43))

    P.append(panel(
        "Pull requests (remediation)", gp(0, 44, 14, 8), "table",
        [infinity_target(f"{B}/pull-requests{sfx}", "data", [
            col("provider", "Provider"), col("repo", "Repo"),
            col("number", "PR #", "number"), col("state", "State"),
            col("validation.confidence", "Confidence", "number"),
            col("finding_ids", "Findings"), col("url", "URL")])],
        fieldcfg={"defaults": {}, "overrides": [
            {"matcher": {"id": "byName", "options": "State"}, "properties": [
                {"id": "mappings", "value": mappings_from(PR_COLORS)},
                {"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
            {"matcher": {"id": "byName", "options": "Confidence"}, "properties": [
                {"id": "unit", "value": "percentunit"}]},
            {"matcher": {"id": "byName", "options": "URL"}, "properties": [
                {"id": "custom.cellOptions", "value": {"type": "auto"}},
                {"id": "links", "value": [{"title": "Open PR", "url": "${__value.raw}",
                 "targetBlank": True}]}]}]},
        options={"showHeader": True},
        description="Remediation pull requests (Pro). Human-reviewed, never auto-merged."))

    # Retest verdict summary (stat)
    P.append(panel(
        "Retest verdicts", gp(14, 44, 10, 3), "stat",
        [infinity_target(f"{B}/retest/${{retest_id}}{sfx}", "verdicts_summary", [
            col("fixed", "Fixed", "number"), col("still_present", "Still present", "number"),
            col("regressed", "Regressed", "number"), col("new", "New", "number")])],
        fieldcfg={"defaults": {"color": {"mode": "fixed"}}, "overrides": [
            {"matcher": {"id": "byName", "options": n}, "properties": [
                {"id": "color", "value": {"mode": "fixed", "fixedColor": VERDICT_COLORS[k]}}]}
            for n, k in [("Fixed", "fixed"), ("Still present", "still_present"),
                         ("Regressed", "regressed"), ("New", "new")]]},
        options={"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background",
                 "graphMode": "none", "textMode": "value_and_name", "orientation": "horizontal"},
        description="Derived retest verdicts (fixed / still_present / regressed / new). "
                    "Set the retest_id variable to a retest run."))

    P.append(panel(
        "Retest / regression detail", gp(14, 47, 10, 5), "table",
        [infinity_target(f"{B}/retest/${{retest_id}}{sfx}", "findings", [
            col("title", "Finding"), col("severity", "Severity"),
            col("verdict", "Verdict"), col("base_status", "Was"),
            col("new_status", "Now")])],
        fieldcfg={"defaults": {}, "overrides": [
            {"matcher": {"id": "byName", "options": "Verdict"}, "properties": [
                {"id": "mappings", "value": mappings_from(VERDICT_COLORS)},
                {"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
            {"matcher": {"id": "byName", "options": "Severity"}, "properties": [
                {"id": "mappings", "value": mappings_from(SEV_COLORS)},
                {"id": "custom.cellOptions", "value": {"type": "color-text"}}]}]},
        options={"showHeader": True},
        description="Per-finding retest verdict comparing the base vs new campaign."))

    # ============ ROW: DRILL-DOWN DETAIL (campaign / finding / evidence-meta) ============
    P.append(row("Drill-down detail (campaign → finding → evidence metadata)", 52))

    # Campaign detail stats
    P.append(panel(
        "Campaign ${campaign_id} — stats", gp(0, 53, 12, 5), "stat",
        [infinity_target(f"{B}/campaigns/${{campaign_id}}{sfx}", "data.stats", [
            col("critical", "Critical", "number"), col("high", "High", "number"),
            col("medium", "Medium", "number"), col("low", "Low", "number"),
            col("exploited", "Exploited", "number"), col("confirmed", "Confirmed", "number")])],
        fieldcfg={"defaults": {"color": {"mode": "fixed", "fixedColor": "#6366f1"}}, "overrides": [
            {"matcher": {"id": "byName", "options": "Critical"}, "properties": [
                {"id": "color", "value": {"mode": "fixed", "fixedColor": SEV_COLORS["critical"]}}]},
            {"matcher": {"id": "byName", "options": "High"}, "properties": [
                {"id": "color", "value": {"mode": "fixed", "fixedColor": SEV_COLORS["high"]}}]}]},
        options={"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background",
                 "graphMode": "none", "textMode": "value_and_name", "orientation": "horizontal"},
        description="Stats for the campaign selected via drill-down (campaign_id variable)."))

    # Finding detail (safe fields only)
    P.append(panel(
        "Finding ${vuln_id} — detail (safe fields only)", gp(12, 53, 12, 5), "table",
        [infinity_target(f"{B}/vulnerabilities/${{vuln_id}}{sfx}", "data", [
            col("title", "Title"), col("severity", "Severity"), col("status", "Status"),
            col("category", "Category"), col("cve", "CVE"),
            col("cvss_score", "CVSS", "number"), col("cvss_vector", "Vector"),
            col("mitre_attack_id", "ATT&CK"), col("mitre_attack_name", "Technique"),
            col("iso27001_control", "ISO 27001"), col("endpoint", "Endpoint"),
            col("discovered_by_agent", "Agent")])],
        transformations=[{"id": "transpose", "options": {}}],
        options={"showHeader": False},
        description="Finding metadata (NEVER description/evidence/raw). Selected via "
                    "the vuln_id drill-down variable."))

    # Evidence metadata (counts/booleans only)
    P.append(panel(
        "Finding ${vuln_id} — evidence metadata (counts only, never content)", gp(0, 58, 24, 4),
        "stat",
        [infinity_target(f"{B}/vulnerabilities/${{vuln_id}}/evidence-meta{sfx}", "", [
            col("has_evidence", "Has evidence", "string"),
            col("counts.commands", "Commands", "number"),
            col("counts.payloads", "Payloads", "number"),
            col("counts.screenshots", "Screenshots", "number"),
            col("counts.logs", "Logs", "number"),
            col("has_extracted_data", "Extracted data", "string"),
            col("redacted", "Redacted", "string")])],
        fieldcfg={"defaults": {"color": {"mode": "fixed", "fixedColor": "#14b8a6"}}, "overrides": []},
        options={"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "none",
                 "graphMode": "none", "textMode": "value_and_name", "orientation": "horizontal"},
        description="Evidence PRESENCE and COUNTS only. This panel proves the two-key "
                    "redaction rule: content is never fetched or rendered."))

    return P


def variables(demo):
    def q(name, label, values):
        # Grafana rebuilds custom-variable options from `query`, so a bare "All"
        # becomes value "All" and leaks into the filter (severity=All -> 0 rows).
        # Use the `label : value` syntax so "All" carries an EMPTY value, which
        # both the mock and real Darkmoon treat as "no filter" (`if severity:`).
        query = ", ".join(["All : "] + values)
        opts = [{"text": "All", "value": "", "selected": True}]
        opts += [{"text": v, "value": v, "selected": False} for v in values]
        return {"name": name, "label": label, "type": "custom",
                "query": query, "current": {"text": "All", "value": ""},
                "options": opts, "includeAll": False, "multi": False, "hide": 0}

    def textbox(name, label, default):
        return {"name": name, "label": label, "type": "textbox",
                "query": default, "current": {"text": default, "value": default}, "hide": 0}

    def constant(name, val):
        return {"name": name, "type": "constant", "query": val,
                "current": {"text": val, "value": val}, "hide": 2}

    if demo == "lab":
        base = "http://darkmoon-mock:8080"
    elif demo:
        base = DEMO_BASE
    else:
        base = "http://localhost:8080"
    ds_uid = "grafanacloud-infinity" if demo is True else "darkmoon-infinity"

    vars_ = [
        {"name": "darkmoon_ds", "label": "Darkmoon datasource",
         "type": "datasource", "query": "yesoreyeram-infinity-datasource",
         "current": {"text": ds_uid, "value": ds_uid}, "hide": 0},
        textbox("darkmoon_url", "Darkmoon API base URL", base),
        textbox("campaign_id", "Campaign (drill-down)", "camp_demo_04" if demo else ""),
        textbox("target_id", "Target (drill-down)", "tgt_web" if demo else ""),
        textbox("vuln_id", "Finding (drill-down)", "vuln_ef0ddafabc" if demo else ""),
        textbox("retest_id", "Retest (drill-down)", "retest_demo_1"),
    ]
    return {"list": vars_}


def build(demo):
    sfx = ".json" if demo is True else ""
    _id[0] = 0
    panels = build_panels(sfx)
    if demo == "lab":
        title, uid = "Darkmoon Security Posture (lab)", "darkmoon-posture"
    elif demo:
        title, uid = "Darkmoon Security Posture — Demo", "darkmoon-posture-demo"
    else:
        title, uid = "Darkmoon Security Posture", "darkmoon-posture"
    dash = {
        "uid": uid,
        "title": title,
        "tags": ["darkmoon", "security", "pentest", "vulnerabilities"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "editable": True,
        "graphTooltip": 0,
        "refresh": "30s",
        "time": {"from": "now-90d", "to": "now"},
        "templating": variables(demo),
        "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "grafana",
            "uid": "-- Grafana --"}, "enable": True, "hide": True, "type": "dashboard"}]},
        "links": [{"title": "Darkmoon", "url": "https://dark-moon.org", "type": "link",
                   "icon": "external link", "targetBlank": True}],
        "panels": panels,
        "description": ("Darkmoon Security Posture — mirrors the Darkmoon web app. "
                        "Overview KPIs, findings over time, severity/status distributions, "
                        "campaigns, targets, vulnerabilities, MITRE ATT&CK, technologies, "
                        "remediation PRs and retest verdicts. Safe fields only — never "
                        "renders evidence or report bodies."),
    }
    return dash


def main():
    os.makedirs(OUT, exist_ok=True)
    lab_dir = os.path.join(os.path.dirname(__file__), "..", "test", "dashboards")
    os.makedirs(lab_dir, exist_ok=True)
    for demo, path in (
            (False, os.path.join(OUT, "darkmoon-security-posture.json")),
            (True, os.path.join(OUT, "darkmoon-security-posture-demo.json")),
            ("lab", os.path.join(lab_dir, "darkmoon-security-posture-lab.json"))):
        d = build(demo)
        with open(path, "w") as f:
            json.dump(d, f, indent=2)
        print("wrote", os.path.basename(path), "panels:",
              len([p for p in d["panels"] if p["type"] != "row"]))


if __name__ == "__main__":
    main()
