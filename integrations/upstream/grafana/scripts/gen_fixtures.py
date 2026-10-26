#!/usr/bin/env python3
"""
Generate the synthetic **Demo Shop** fixture dataset for the Darkmoon Grafana
integration.

Every file mirrors an EXACT Darkmoon REST response shape (verified against
Dark-Moon-Front-API/mcp/api/routes_*.py). Written under fixtures/api/v1/** as
static JSON so it can be served two ways:

  1. by the docker-compose mock server (fixtures/mock_server.py), which honours
     query params -> exercises the PRODUCTION dashboard exactly like real Darkmoon;
  2. straight from raw.githubusercontent.com (query strings ignored) -> powers the
     self-contained DEMO dashboard + the live Grafana Cloud screenshots.

SAFETY: this is 100% synthetic ("Demo Shop", demo-shop.local, zeroed secrets).
No real client data. Evidence bodies are deliberately fake so tests can assert
the dashboards NEVER render description/evidence/raw.
"""
import json
import os
import hashlib
from datetime import datetime, timedelta

ROOT = os.path.join(os.path.dirname(__file__), "..", "fixtures", "api", "v1")

CONTRACT_VERSION = "1"

# ---------------------------------------------------------------------------
# Targets (Demo Shop estate)
# ---------------------------------------------------------------------------
TARGETS = [
    {"id": "tgt_web", "host": "demo-shop.local", "ip": "10.10.0.11",
     "status": "compromised", "risk_level": "critical",
     "technologies": [
         {"name": "nginx", "version": "1.18.0", "category": "webserver"},
         {"name": "PHP", "version": "7.4", "category": "language"},
         {"name": "WordPress", "version": "6.2", "category": "cms"},
     ]},
    {"id": "tgt_api", "host": "api.demo-shop.local", "ip": "10.10.0.12",
     "status": "vulnerable", "risk_level": "high",
     "technologies": [
         {"name": "Node.js", "version": "18.16", "category": "runtime"},
         {"name": "Express", "version": "4.18", "category": "framework"},
         {"name": "PostgreSQL", "version": "14", "category": "database"},
     ]},
    {"id": "tgt_iot", "host": "kiosk.demo-shop.local", "ip": "10.10.0.30",
     "status": "vulnerable", "risk_level": "high",
     "technologies": [
         {"name": "BusyBox", "version": "1.30", "category": "os"},
         {"name": "lighttpd", "version": "1.4", "category": "webserver"},
     ]},
    {"id": "tgt_pay", "host": "pay.demo-shop.local", "ip": "10.10.0.13",
     "status": "scanned", "risk_level": "medium",
     "technologies": [
         {"name": "Java", "version": "17", "category": "runtime"},
         {"name": "Spring Boot", "version": "3.1", "category": "framework"},
     ]},
]

# ---------------------------------------------------------------------------
# Campaigns over time (for trend / evolution). Oldest -> newest.
# ---------------------------------------------------------------------------
D0 = datetime(2026, 8, 20)
CAMPAIGNS_META = [
    ("camp_demo_01", "tgt_web", D0,                 "stopped"),
    ("camp_demo_02", "tgt_api", D0 + timedelta(3),  "completed"),
    ("camp_demo_03", "tgt_iot", D0 + timedelta(9),  "completed"),
    ("camp_demo_04", "tgt_web", D0 + timedelta(16), "completed"),   # retest-ish of web
    ("camp_demo_05", "tgt_pay", D0 + timedelta(22), "completed"),
    ("camp_demo_06", "tgt_api", D0 + timedelta(30), "running"),
]

# ---------------------------------------------------------------------------
# Vulnerabilities. Each carries the full safe field-set + a fake description &
# zeroed evidence (to prove redaction). status in {exploited,confirmed,unconfirmed,remediated}
# ---------------------------------------------------------------------------
def vid(campaign, n):
    return f"vuln_{hashlib.md5(f'{campaign}{n}'.encode()).hexdigest()[:10]}"

FAKE_EVIDENCE = {
    "commands": ["<redacted-in-demo>"], "payloads": [], "raw_request": "",
    "raw_response": "", "extracted_data": None, "screenshots": [], "logs": [],
    "explanation": "SYNTHETIC demo evidence — never rendered by any dashboard.",
}

VULNS = [
    # --- camp_demo_01 (web, first pass) ---
    dict(c="camp_demo_01", t="tgt_web", title="SQL Injection in /product?id",
         severity="critical", status="exploited", category="sql_injection",
         cve="CVE-2026-1001", cvss=9.8, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
         mid="T1190", mname="Exploit Public-Facing Application", iso="A.14.2.5",
         endpoint="/product?id=", agent="web-app"),
    dict(c="camp_demo_01", t="tgt_web", title="Reflected XSS in search box",
         severity="high", status="confirmed", category="xss",
         cve=None, cvss=7.4, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N",
         mid="T1059", mname="Command and Scripting Interpreter", iso="A.14.2.5",
         endpoint="/search?q=", agent="web-app"),
    dict(c="camp_demo_01", t="tgt_web", title="WordPress admin weak password",
         severity="high", status="exploited", category="broken_authentication",
         cve=None, cvss=8.1, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
         mid="T1110", mname="Brute Force", iso="A.9.4.3",
         endpoint="/wp-login.php", agent="web-app"),
    dict(c="camp_demo_01", t="tgt_web", title="Missing security headers (CSP/HSTS)",
         severity="low", status="confirmed", category="misconfiguration",
         cve=None, cvss=3.1, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N",
         mid="T1592", mname="Gather Victim Host Information", iso="A.14.1.2",
         endpoint="/", agent="web-app"),
    # --- camp_demo_02 (api) ---
    dict(c="camp_demo_02", t="tgt_api", title="IDOR on /api/orders/{id}",
         severity="critical", status="exploited", category="broken_access_control",
         cve=None, cvss=9.1, vec="CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N",
         mid="T1190", mname="Exploit Public-Facing Application", iso="A.9.4.1",
         endpoint="/api/orders/{id}", agent="api-security"),
    dict(c="camp_demo_02", t="tgt_api", title="JWT 'none' algorithm accepted",
         severity="high", status="confirmed", category="broken_authentication",
         cve=None, cvss=8.2, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:N",
         mid="T1550", mname="Use Alternate Authentication Material", iso="A.9.4.2",
         endpoint="/api/auth/token", agent="api-security"),
    dict(c="camp_demo_02", t="tgt_api", title="Verbose error leaks stack trace",
         severity="medium", status="confirmed", category="information_disclosure",
         cve=None, cvss=5.3, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N",
         mid="T1592", mname="Gather Victim Host Information", iso="A.12.4.1",
         endpoint="/api/checkout", agent="api-security"),
    dict(c="camp_demo_02", t="tgt_api", title="Rate limiting absent on login",
         severity="medium", status="unconfirmed", category="misconfiguration",
         cve=None, cvss=5.0, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L",
         mid="T1110", mname="Brute Force", iso="A.9.4.1",
         endpoint="/api/auth/login", agent="api-security"),
    # --- camp_demo_03 (iot) ---
    dict(c="camp_demo_03", t="tgt_iot", title="Unauthenticated firmware upload",
         severity="critical", status="exploited", category="remote_code_execution",
         cve=None, cvss=9.9, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
         mid="T1133", mname="External Remote Services", iso="A.14.2.5",
         endpoint="/cgi-bin/upgrade", agent="iot-firmware"),
    dict(c="camp_demo_03", t="tgt_iot", title="Hardcoded telnet credentials",
         severity="high", status="confirmed", category="broken_authentication",
         cve="CVE-2026-2050", cvss=8.8, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
         mid="T1078", mname="Valid Accounts", iso="A.9.2.4",
         endpoint="telnet://:23", agent="iot-firmware"),
    dict(c="camp_demo_03", t="tgt_iot", title="Outdated BusyBox (known CVEs)",
         severity="medium", status="confirmed", category="vulnerable_component",
         cve="CVE-2022-48174", cvss=6.5, vec="CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:L",
         mid="T1195", mname="Supply Chain Compromise", iso="A.12.6.1",
         endpoint="/", agent="iot-firmware"),
    # --- camp_demo_04 (web retest: SQLi fixed, headers fixed, new one appears) ---
    dict(c="camp_demo_04", t="tgt_web", title="SQL Injection in /product?id",
         severity="critical", status="remediated", category="sql_injection",
         cve="CVE-2026-1001", cvss=9.8, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
         mid="T1190", mname="Exploit Public-Facing Application", iso="A.14.2.5",
         endpoint="/product?id=", agent="web-app"),
    dict(c="camp_demo_04", t="tgt_web", title="Reflected XSS in search box",
         severity="high", status="confirmed", category="xss",
         cve=None, cvss=7.4, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N",
         mid="T1059", mname="Command and Scripting Interpreter", iso="A.14.2.5",
         endpoint="/search?q=", agent="web-app"),
    dict(c="camp_demo_04", t="tgt_web", title="Server-Side Request Forgery in webhook",
         severity="high", status="confirmed", category="ssrf",
         cve=None, cvss=8.6, vec="CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:L/A:N",
         mid="T1190", mname="Exploit Public-Facing Application", iso="A.13.1.3",
         endpoint="/admin/webhook", agent="web-app"),
    # --- camp_demo_05 (pay) ---
    dict(c="camp_demo_05", t="tgt_pay", title="TLS 1.0 enabled on payment endpoint",
         severity="medium", status="confirmed", category="misconfiguration",
         cve=None, cvss=5.9, vec="CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N",
         mid="T1040", mname="Network Sniffing", iso="A.10.1.1",
         endpoint="/pay/checkout", agent="web-app"),
    dict(c="camp_demo_05", t="tgt_pay", title="Directory listing exposes /backup",
         severity="low", status="confirmed", category="information_disclosure",
         cve=None, cvss=4.3, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N",
         mid="T1083", mname="File and Directory Discovery", iso="A.12.4.1",
         endpoint="/backup/", agent="web-app"),
    # --- camp_demo_06 (api, running - partial) ---
    dict(c="camp_demo_06", t="tgt_api", title="GraphQL introspection enabled",
         severity="low", status="unconfirmed", category="information_disclosure",
         cve=None, cvss=3.7, vec="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N",
         mid="T1592", mname="Gather Victim Host Information", iso="A.12.4.1",
         endpoint="/graphql", agent="api-security"),
]


def build_vuln(v, idx):
    _id = vid(v["c"], idx)
    return {
        "id": _id,
        "campaign_id": v["c"],
        "target_id": v["t"],
        "project_id": "proj_demoshop",
        "title": v["title"],
        "severity": v["severity"],
        "status": v["status"],
        "category": v["category"],
        "cve": v["cve"],
        "cwe": None,
        "cvss_score": v["cvss"],
        "cvss_vector": v["vec"],
        "mitre_attack_id": v["mid"],
        "mitre_attack_name": v["mname"],
        "iso27001_control": v["iso"],
        "endpoint": v["endpoint"],
        "discovered_by_agent": v["agent"],
        "description": f"[SYNTHETIC] {v['title']} on the Demo Shop estate. "
                       "This description is intentionally present so tests can prove "
                       "the Grafana dashboards never render it on a shared surface.",
        "evidence": dict(FAKE_EVIDENCE),
        "remediation": "Apply the documented fix; re-run a Darkmoon retest to verify.",
    }


ALL_VULNS = [build_vuln(v, i) for i, v in enumerate(VULNS)]
OPEN_STATES = {"exploited", "confirmed", "unconfirmed"}  # not remediated/resolved/closed/fixed


def vulns_for_campaign(cid):
    return [v for v in ALL_VULNS if v["campaign_id"] == cid]


def stats_for(vlist):
    s = {"total_findings": len(vlist), "critical": 0, "high": 0, "medium": 0,
         "low": 0, "info": 0, "exploited": 0, "confirmed": 0, "unconfirmed": 0}
    for v in vlist:
        if v["severity"] in s:
            s[v["severity"]] += 1
        if v["status"] in ("exploited", "confirmed", "unconfirmed"):
            s[v["status"]] += 1
    return s


RISK_RANK = ["critical", "high", "medium", "low", "info", "none"]


def overall_risk(vlist):
    for r in RISK_RANK:
        if any(v["severity"] == r for v in vlist):
            return r
    return "none"


def build_campaigns():
    out = []
    for cid, tid, date, status in CAMPAIGNS_META:
        vlist = vulns_for_campaign(cid)
        st = stats_for(vlist)
        out.append({
            "id": cid,
            "project_id": "proj_demoshop",
            "target_id": tid,
            "session_id": f"sess_{cid}",
            "date": date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": status,
            "stats": st,
            "overall_risk": overall_risk(vlist) if vlist else "none",
            "agents_dispatched": [],
            "is_subagent": False,
        })
    return out


CAMPAIGNS = build_campaigns()
CAMP_BY_ID = {c["id"]: c for c in CAMPAIGNS}


def open_vulns_for_target(tid):
    return len([v for v in ALL_VULNS if v["target_id"] == tid and v["status"] in OPEN_STATES])


def build_targets():
    out = []
    for t in TARGETS:
        e = dict(t)
        e["project_id"] = "proj_demoshop"
        e["open_vuln"] = open_vulns_for_target(t["id"])
        # last_seen = latest campaign date on this target
        dates = [c["date"] for c in CAMPAIGNS if c["target_id"] == t["id"]]
        e["last_seen"] = max(dates) if dates else None
        out.append(e)
    return out


ENRICHED_TARGETS = build_targets()


def build_overview():
    sev = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    cat = {}
    stt = {"exploited": 0, "confirmed": 0, "unconfirmed": 0, "remediated": 0}
    for v in ALL_VULNS:
        if v["severity"] in sev:
            sev[v["severity"]] += 1
        cat[v["category"]] = cat.get(v["category"], 0) + 1
        if v["status"] in stt:
            stt[v["status"]] += 1
    recent = []
    for c in sorted(CAMPAIGNS, key=lambda c: c["date"], reverse=True)[:10]:
        host = next((t["host"] for t in ENRICHED_TARGETS if t["id"] == c["target_id"]), c["target_id"])
        recent.append({"campaign_id": c["id"], "target": host, "date": c["date"][:10],
                       "risk": c["overall_risk"], "findings": c["stats"]["total_findings"]})
    at_risk = []
    for t in ENRICHED_TARGETS:
        if t["risk_level"] in ("critical", "high", "medium"):
            at_risk.append({"target_id": t["id"], "host": t["host"],
                            "risk_level": t["risk_level"], "open_vulns": t["open_vuln"]})
    return {
        "projects_count": 1,
        "targets_count": len(ENRICHED_TARGETS),
        "campaigns_count": len(CAMPAIGNS),
        "total_vulnerabilities": len(ALL_VULNS),
        "severity_distribution": sev,
        "category_distribution": cat,
        "status_distribution": stt,
        "recent_campaigns": recent,
        "targets_at_risk": at_risk,
    }


def build_timeseries(metric):
    # group by day, over campaign dates; series = distinct metric values
    grid = {}  # bucket -> key -> count
    order = []
    keys = []
    for c in sorted(CAMPAIGNS, key=lambda c: c["date"]):
        b = c["date"][:10]
        if b not in grid:
            grid[b] = {}
            order.append(b)
        for v in vulns_for_campaign(c["id"]):
            k = str(v.get(metric, "unknown") or "unknown").lower()
            grid[b][k] = grid[b].get(k, 0) + 1
            if k not in keys:
                keys.append(k)
    series = [{"key": k, "points": [{"t": b, "value": grid[b].get(k, 0)} for b in order]}
              for k in keys]
    return {"metric": metric, "group": "day", "series": series}


def build_pull_requests():
    return [
        {"id": "pr_demo_1", "campaign_id": "camp_demo_04", "provider": "github",
         "repo": "ASCIT31/demo-shop", "number": 128, "state": "open",
         "url": "https://github.com/ASCIT31/demo-shop/pull/128",
         "title": "fix(sql): parameterize /product query (Darkmoon)",
         "finding_ids": [ALL_VULNS[0]["id"]],
         "diff_stat": {"files": 2, "additions": 14, "deletions": 6},
         "validation": {"reproduced": True, "confidence": 0.92,
                        "gates": ["exploit", "regression"], "passed": True},
         "created_at": "2026-09-05T10:00:00Z", "created_by_agent": "remediation"},
        {"id": "pr_demo_2", "campaign_id": "camp_demo_04", "provider": "github",
         "repo": "ASCIT31/demo-shop", "number": 131, "state": "merged",
         "url": "https://github.com/ASCIT31/demo-shop/pull/131",
         "title": "fix(headers): add CSP + HSTS (Darkmoon)",
         "finding_ids": [ALL_VULNS[3]["id"]],
         "diff_stat": {"files": 1, "additions": 9, "deletions": 0},
         "validation": {"reproduced": True, "confidence": 0.99,
                        "gates": ["regression"], "passed": True},
         "created_at": "2026-09-04T09:00:00Z", "created_by_agent": "remediation"},
    ]


def build_retest():
    # web retest: base camp_demo_01 -> new camp_demo_04
    base = vulns_for_campaign("camp_demo_01")
    new = vulns_for_campaign("camp_demo_04")
    new_titles = {v["title"]: v for v in new}
    findings = []
    for bv in base:
        nv = new_titles.get(bv["title"])
        if nv is None:
            verdict = "fixed"; new_status = None
        elif nv["status"] == "remediated":
            verdict = "fixed"; new_status = "remediated"
        else:
            verdict = "still_present"; new_status = nv["status"]
        findings.append({"finding_id": bv["id"], "title": bv["title"],
                         "severity": bv["severity"], "verdict": verdict,
                         "base_status": bv["status"], "new_status": new_status})
    # brand-new finding in retest
    for nv in new:
        if nv["title"] not in {b["title"] for b in base}:
            findings.append({"finding_id": nv["id"], "title": nv["title"],
                             "severity": nv["severity"], "verdict": "new",
                             "base_status": None, "new_status": nv["status"]})
    summary = {"fixed": 0, "still_present": 0, "regressed": 0, "new": 0}
    for f in findings:
        if f["verdict"] in summary:
            summary[f["verdict"]] += 1
    return {
        "retest_id": "retest_demo_1", "base_campaign_id": "camp_demo_01",
        "new_campaign_id": "camp_demo_04", "target_id": "tgt_web",
        "run_id": "run_demo_retest", "status": "completed",
        "verdicts_summary": summary, "findings": findings,
    }


def build_system_info():
    return {
        "edition": "pro", "api_version": "1.0.0", "product_version": "demo-fixture",
        "product_built_at": "2026-09-25T00:00:00Z", "contract_version": CONTRACT_VERSION,
        "capabilities": ["auth", "campaigns", "credentials", "dashboard",
                         "pull-requests", "run", "scheduler", "system", "targets",
                         "vulnerabilities", "projects", "metrics", "events", "retest",
                         "webhooks"],
        "features": {"auth": True, "credentials": True, "scheduler": True,
                     "sse_progress": True, "remediation": True,
                     "privacy_gateway": True, "licensing": True},
    }


def write(path, obj):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        json.dump(obj, f, indent=1)
    print("wrote", os.path.relpath(full, os.path.join(ROOT, "..", "..")))


def main():
    # Core list/aggregate endpoints
    write("system/info.json", build_system_info())
    write("dashboard/overview.json", build_overview())
    write("campaigns.json", {"data": CAMPAIGNS, "total": len(CAMPAIGNS)})
    for c in CAMPAIGNS:
        vl = vulns_for_campaign(c["id"])
        write(f"campaigns/{c['id']}.json",
              {"data": {**c, "vulnerabilities": vl,
                        "open_vuln": len([v for v in vl if v["status"] in OPEN_STATES])}})
    # vulnerabilities (full list) + stats
    by_sev, by_cat, by_stt = {}, {}, {}
    for v in ALL_VULNS:
        by_sev[v["severity"]] = by_sev.get(v["severity"], 0) + 1
        by_cat[v["category"]] = by_cat.get(v["category"], 0) + 1
        by_stt[v["status"]] = by_stt.get(v["status"], 0) + 1
    write("vulnerabilities.json", {"data": ALL_VULNS, "total": len(ALL_VULNS),
          "stats": {"by_severity": by_sev, "by_category": by_cat, "by_status": by_stt}})
    for v in ALL_VULNS:
        write(f"vulnerabilities/{v['id']}.json", {"data": v})
        write(f"vulnerabilities/{v['id']}/evidence-meta.json", {
            "vuln_id": v["id"], "has_evidence": True,
            "counts": {"commands": 1, "payloads": 0, "screenshots": 0, "logs": 0, "requests": 0},
            "command_names": ["<redacted>"], "has_screenshot": False,
            "has_extracted_data": False, "redacted": True})
    # targets
    write("targets.json", {"data": ENRICHED_TARGETS, "total": len(ENRICHED_TARGETS)})
    # metrics timeseries (per-metric static variants for the static demo)
    write("metrics/timeseries.json", build_timeseries("severity"))
    write("metrics/timeseries.severity.json", build_timeseries("severity"))
    write("metrics/timeseries.category.json", build_timeseries("category"))
    write("metrics/timeseries.status.json", build_timeseries("status"))
    # pull-requests
    prs = build_pull_requests()
    write("pull-requests.json", {"data": prs, "total": len(prs)})
    # retest
    write("retest/retest_demo_1.json", build_retest())
    print("\nDemo Shop dataset:", len(ALL_VULNS), "vulns,", len(CAMPAIGNS),
          "campaigns,", len(ENRICHED_TARGETS), "targets")


if __name__ == "__main__":
    main()
