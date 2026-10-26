#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a synthetic "Demo Shop" Darkmoon export for testing.

The objects deliberately include HOSTILE fields (evidence, raw, secrets, tokens,
long descriptions) so tests can prove the forwarder's safe-field allowlist drops
them and nothing sensitive reaches the index.

Never uses real client data — demo-shop.local only.
"""
import json
import os
import random
import sys
import datetime

random.seed(1337)
NOW = datetime.datetime.now(datetime.timezone.utc)

SEVERITIES = ["critical", "high", "medium", "low", "info"]
STATUSES = ["unconfirmed", "confirmed", "exploited", "remediated"]
CATEGORIES = ["injection", "auth", "access-control", "crypto", "config", "xss"]
TECHS = ["nginx", "wordpress", "php", "mysql", "openssh"]
MITRE = [("T1190", "Exploit Public-Facing Application"),
         ("T1059", "Command and Scripting Interpreter"),
         ("T1078", "Valid Accounts"),
         ("T1552", "Unsecured Credentials"),
         ("T1210", "Exploitation of Remote Services")]
AGENTS = ["sqli", "xss", "idor", "recon", "authz"]

# A fake secret that MUST NOT appear in indexed events.
POISON_TOKEN = "SECRETLEAK_ghp_deadbeefdeadbeefdeadbeef0123456789"


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def make():
    project_id = "proj_demoshop01"
    target = "demo-shop.local"
    target_id = "tgt_demoshop01"

    campaigns, vulns, retests, prs = [], [], [], []

    # 4 campaigns across the last 4 weeks
    for w in range(4):
        cdate = NOW - datetime.timedelta(days=(21 - w * 7), hours=random.randint(0, 6))
        cid = "camp_2026%02d%02d_%06x" % (cdate.month, cdate.day, random.randint(0, 0xffffff))
        n = random.randint(4, 7)
        sev_counts = {s: 0 for s in SEVERITIES}
        status_counts = {"exploited": 0, "confirmed": 0, "unconfirmed": 0}
        for i in range(n):
            sev = random.choices(SEVERITIES, weights=[2, 3, 4, 3, 2])[0]
            status = random.choices(STATUSES, weights=[3, 3, 2, 2])[0]
            sev_counts[sev] += 1
            if status in status_counts:
                status_counts[status] += 1
            m = random.choice(MITRE)
            fid = "vuln_%06x" % random.randint(0, 0xffffff)
            vulns.append({
                "id": fid, "finding_id": fid,
                "project_id": project_id, "campaign_id": cid,
                "target_id": target_id, "target": target,
                "title": "%s issue in %s" % (random.choice(CATEGORIES), random.choice(TECHS)),
                "severity": sev, "status": status,
                "category": random.choice(CATEGORIES),
                "cve": "CVE-2026-%04d" % random.randint(1000, 9999) if random.random() > 0.4 else None,
                "cvss_score": round(random.uniform(2.0, 9.9), 1),
                "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                "mitre_attack_id": m[0], "mitre_attack_name": m[1],
                "iso27001_control": "A.8.%d" % random.randint(1, 30),
                "endpoint": "/checkout?id=%d" % random.randint(1, 99),
                "technology": random.choice(TECHS),
                "discovered_by_agent": random.choice(AGENTS),
                "discovered_at": iso(cdate + datetime.timedelta(minutes=i)),
                "ts": iso(cdate + datetime.timedelta(minutes=i)),
                # ---- HOSTILE fields that MUST be dropped ----
                "description": "Full technical write-up with payloads. token=%s" % POISON_TOKEN,
                "remediation": "Do X. internal_note password=%s" % POISON_TOKEN,
                "evidence": {"request": "GET /?q=' OR 1=1 Authorization: Bearer %s" % POISON_TOKEN,
                             "response": "root:x:0:0 %s" % POISON_TOKEN,
                             "extracted_data": ["admin:%s" % POISON_TOKEN]},
                "raw": {"secret": POISON_TOKEN, "api_key": POISON_TOKEN},
            })
        total = sum(sev_counts.values())
        risk = "critical" if sev_counts["critical"] else ("high" if sev_counts["high"] else
               ("medium" if sev_counts["medium"] else ("low" if sev_counts["low"] else "none")))
        campaigns.append({
            "id": cid, "campaign_id": cid, "project_id": project_id,
            "target_id": target_id, "target": target,
            "status": "completed", "overall_risk": risk,
            "duration_seconds": random.randint(120, 2400),
            "date": iso(cdate), "ts": iso(cdate + datetime.timedelta(seconds=1)),
            "stats": {"total_findings": total, **sev_counts, **status_counts},
            # hostile
            "report": "SECRET REPORT BODY %s" % POISON_TOKEN,
        })

    # one running campaign (active)
    rc = NOW - datetime.timedelta(minutes=20)
    campaigns.append({
        "id": "camp_active01", "campaign_id": "camp_active01",
        "project_id": project_id, "target_id": target_id, "target": target,
        "status": "running", "overall_risk": "high", "duration_seconds": 0,
        "date": iso(rc), "ts": iso(rc), "stats": {"total_findings": 0},
    })

    # retests
    base_c = campaigns[0]["campaign_id"]
    new_c = campaigns[1]["campaign_id"]
    for verdict, base_s, new_s in [("fixed", "exploited", "remediated"),
                                   ("regressed", "remediated", "confirmed"),
                                   ("still_present", "confirmed", "confirmed"),
                                   ("new", None, "unconfirmed")]:
        f = random.choice(vulns)
        retests.append({
            "retest_id": "retest_%06x" % random.randint(0, 0xffffff),
            "base_campaign_id": base_c, "new_campaign_id": new_c,
            "finding_id": f["finding_id"], "title": f["title"],
            "severity": f["severity"], "target": target,
            "base_status": base_s, "new_status": new_s, "verdict": verdict,
            "event": "retest.completed",
            "ts": iso(NOW - datetime.timedelta(days=1, minutes=random.randint(0, 200))),
            "evidence": {"diff": POISON_TOKEN},  # hostile
        })

    # PRs
    for st, prov, conf in [("open", "github", 0.82), ("merged", "github", 0.91),
                           ("draft", "gitlab", 0.55)]:
        f = random.choice(vulns)
        prs.append({
            "pr_id": "pr_%06x" % random.randint(0, 0xffffff),
            "campaign_id": f["campaign_id"], "provider": prov,
            "repo": "demo-org/demo-shop", "number": random.randint(10, 400),
            "state": st, "confidence": conf,
            "url": "https://%s.example/demo-org/demo-shop/pull/%d" % (prov, random.randint(10, 400)),
            "finding_ids": [f["finding_id"]],
            "event": "pr.opened" if st in ("open", "draft") else "pr.updated",
            "ts": iso(NOW - datetime.timedelta(days=1, minutes=random.randint(0, 300))),
            "diff": "SECRET DIFF %s" % POISON_TOKEN,  # hostile
        })

    return {"campaigns": campaigns, "vulnerabilities": vulns,
            "retests": retests, "pull_requests": prs}, POISON_TOKEN


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fixtures", "darkmoon-export.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    data, poison = make()
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    print("wrote %s: %d campaigns, %d findings, %d retests, %d PRs" % (
        out, len(data["campaigns"]), len(data["vulnerabilities"]),
        len(data["retests"]), len(data["pull_requests"])))
    print("POISON_TOKEN=%s" % poison)
