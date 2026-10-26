#!/usr/bin/env python3
"""Unit tests for the mapper against the REAL darkmoon-ci finding shape.

Covers redaction (§4), degradation (§2.4), severity maps, endpoint->path, and
that the sensitive `description`/`evidence` never reach shared reports.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MAPPER = os.path.join(REPO, "src", "darkmoon_gitlab_report.py")
VALIDATE = os.path.join(HERE, "validate_schemas.py")

# a real-shaped finding whose description quotes infra/secrets that MUST NOT leak
SECRET_DESC = "Dumped admin@juice-sh.op password hash from 10.0.0.5:5432 — SECRET"
FINDING = {
    "id": "vuln_59058f",
    "campaignId": "camp_x", "projectId": "proj_x", "targetId": "tgt_x",
    "title": "SQL Injection Authentication Bypass on /rest/user/login",
    "severity": "critical", "status": "exploited", "category": "sql_injection",
    "cve": None, "cvssScore": 9.8, "cvssVector": "CVSS:3.1/AV:N",
    "mitreAttackId": "T1190", "mitreAttackName": "Exploit Public-Facing Application",
    "endpoint": "POST /rest/user/login",
    "description": SECRET_DESC,
    "remediation": "Use parameterized queries.",
    "discoveredByAgent": "nodejs", "discoveredAt": "2026-09-24T10:26:12Z",
    "evidence": None,
}

n_pass = n_fail = 0


def check(cond, msg):
    global n_pass, n_fail
    print(("  PASS: " if cond else "  FAIL: ") + msg)
    if cond:
        n_pass += 1
    else:
        n_fail += 1


def run_mapper(findings_path, cq, sast):
    return subprocess.run([sys.executable, MAPPER, "--findings", findings_path,
                           "--codequality", cq, "--sast", sast, "--edition", "oss"],
                          capture_output=True, text=True)


def test_shape_and_redaction(tmp):
    # findings --json emits a BARE ARRAY; the mapper must accept it
    fp = os.path.join(tmp, "arr.json")
    json.dump([FINDING], open(fp, "w"))
    cq, sast = os.path.join(tmp, "cq.json"), os.path.join(tmp, "sast.json")
    run_mapper(fp, cq, sast)
    cq_txt, sast_txt = open(cq).read(), open(sast).read()
    check(SECRET_DESC not in cq_txt and SECRET_DESC not in sast_txt,
          "sensitive description/infra never appears in shared reports")
    check("admin@juice-sh.op" not in cq_txt and "10.0.0.5" not in sast_txt,
          "no emails/IPs from description leak into shared reports")
    check("SQL Injection Authentication Bypass" in cq_txt,
          "redaction-safe TITLE is used on shared surfaces")
    cqd = json.loads(cq_txt)
    check(cqd[0]["severity"] == "blocker", "critical -> blocker (CodeClimate)")
    check(cqd[0]["location"]["path"] == "rest/user/login",
          "endpoint 'POST /rest/user/login' -> location.path 'rest/user/login'")
    check(cqd[0]["check_name"] == "darkmoon/sql_injection", "check_name = darkmoon/<category>")
    sd = json.loads(sast_txt)
    v = sd["vulnerabilities"][0]
    check(v["severity"] == "Critical", "critical -> Critical (SAST)")
    idtypes = {i["type"] for i in v["identifiers"]}
    check("cwe" in idtypes and "darkmoon_category" in idtypes and "darkmoon_mitre" in idtypes,
          "SAST identifiers include category + enriched CWE + MITRE")
    check("Z" not in sd["scan"]["start_time"], "SAST scan.start_time has no timezone suffix")


def test_object_wrapper(tmp):
    fp = os.path.join(tmp, "obj.json")
    json.dump({"contractVersion": "1.0.0", "findings": [FINDING]}, open(fp, "w"))
    cq, sast = os.path.join(tmp, "cq2.json"), os.path.join(tmp, "sast2.json")
    run_mapper(fp, cq, sast)
    check(len(json.loads(open(cq).read())) == 1, "mapper accepts {findings:[...]} object too")


def test_degradation(tmp):
    cq, sast = os.path.join(tmp, "cq3.json"), os.path.join(tmp, "sast3.json")
    r = run_mapper(os.path.join(tmp, "nope.json"), cq, sast)
    check(r.returncode == 0, "missing findings file -> mapper exits 0 (no crash)")
    check(json.loads(open(cq).read()) == [], "missing input -> empty code-quality array")
    check(json.loads(open(sast).read())["vulnerabilities"] == [], "missing input -> empty SAST vulns")
    open(os.path.join(tmp, "bad.json"), "w").write("{not json")
    r = run_mapper(os.path.join(tmp, "bad.json"), cq, sast)
    check(r.returncode == 0, "malformed findings file -> mapper exits 0 (no crash)")
    v = subprocess.run([sys.executable, VALIDATE, cq, sast], capture_output=True, text=True)
    check(v.returncode == 0, "empty reports still validate against live schemas")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        print("== finding shape + redaction (§4) =="); test_shape_and_redaction(tmp)
        print("== object wrapper =="); test_object_wrapper(tmp)
        print("== degradation (§2.4) =="); test_degradation(tmp)
    print("\n== UNIT SUMMARY: %d passed, %d failed ==" % (n_pass, n_fail))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
