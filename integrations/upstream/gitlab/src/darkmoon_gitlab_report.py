#!/usr/bin/env python3
"""Map Darkmoon `darkmoon-ci findings ... --json` output to GitLab report formats.

Consumes the normalized, redaction-safe findings emitted by the portable
`darkmoon-ci` CLI (a JSON array, or an object with a `findings` / `data` array —
see CONTRACT.md) and emits:
  - gl-code-quality-report.json  (CodeClimate, artifacts:reports:codequality)
  - gl-sast-report.json          (GitLab SAST security-report-schemas)

Threat model (§4): only redaction-safe text (the finding TITLE + generic
metadata) reaches these shared reports. The finding `description`/`evidence`
(which can quote target infrastructure) is NEVER copied here — the full report is
obtained separately via `darkmoon-ci report --full --private` as an internal,
opt-in artifact.

Stdlib only; invalid input emits failure-status diagnostic reports and exit 1.
This is part of the GitLab component, not the darkmoon-ci CLI.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import re as _re
import sys
from urllib.parse import urlsplit
from typing import Any, Dict, List

# SAST schema version this mapper was written against (read live at build/test
# from security-report-schemas; overridable with --sast-schema-version).
DEFAULT_SAST_SCHEMA_VERSION = "15.2.5"

# native (lowercase) severity -> CodeClimate severity
CQ_SEVERITY = {
    "info": "info", "low": "minor", "medium": "major",
    "high": "critical", "critical": "blocker",
}
# native severity -> GitLab SAST severity (Title-case, per live schema enum)
SAST_SEVERITY = {
    "info": "Info", "low": "Low", "medium": "Medium",
    "high": "High", "critical": "Critical",
}

# Darkmoon category slug -> (CWE, OWASP) enrichment for identifiers.
CAT_ENRICH = {
    "sql_injection": ("CWE-89", "A03:2021-Injection"),
    "sqli": ("CWE-89", "A03:2021-Injection"),
    "xss": ("CWE-79", "A03:2021-Injection"),
    "ssrf": ("CWE-918", "A10:2021-SSRF"),
    "rce": ("CWE-94", "A03:2021-Injection"),
    "command_injection": ("CWE-77", "A03:2021-Injection"),
    "idor": ("CWE-639", "A01:2021-Broken Access Control"),
    "broken_access_control": ("CWE-284", "A01:2021-Broken Access Control"),
    "auth_bypass": ("CWE-287", "A07:2021-Identification and Authentication Failures"),
    "secret_exposure": ("CWE-522", "A07:2021-Identification and Authentication Failures"),
    "info_disclosure": ("CWE-200", "A05:2021-Security Misconfiguration"),
    "misconfiguration": ("CWE-16", "A05:2021-Security Misconfiguration"),
}


def _warn(msg: str) -> None:
    sys.stderr.write("darkmoon-gitlab-report: %s\n" % msg)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")




def _norm_sev(value: Any) -> str:
    s = str(value or "").strip().lower()
    return s if s in CQ_SEVERITY else "info"


def _endpoint_to_path(endpoint: Any) -> str:
    """Only a conservative static route path; never publish URL credentials."""
    value = str(endpoint or "").strip()
    value = _re.sub(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+", "", value, flags=_re.I)
    if value.lower().startswith(("http://", "https://")):
        try:
            parsed = urlsplit(value)
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                return ".darkmoon/report.md"
            value = parsed.path
        except ValueError:
            return ".darkmoon/report.md"
    # Query/fragment, absolute filesystem paths and opaque dynamic segments are
    # not safe project file names. An unknown endpoint has no source location.
    if "?" in value or "#" in value or "@" in value:
        return ".darkmoon/report.md"
    path = value.strip().lstrip("/")
    if (not _re.fullmatch(r"[A-Za-z0-9_./-]{1,255}", path)
            or ".." in path.split("/")):
        return ".darkmoon/report.md"
    return path


def _fingerprint(f: Dict[str, Any], path: str) -> str:
    basis = "|".join([str(f.get("id") or ""), path, str(f.get("title") or "")])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _shared_text(f: Dict[str, Any]) -> str:
    """Only the title; redact embedded URLs before publishing a shared report."""
    title = str(f.get("title") or "").strip() or str(f.get("id") or "Darkmoon finding")
    title = _re.sub(r"https?://[^\s<>]+", "[URL]", title, flags=_re.I)
    return title[:1000]


def _category(f: Dict[str, Any]) -> str:
    value = str(f.get("category") or "finding").strip()
    return value if _re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value) else "finding"


def verify_run_verdict(path: str, exit_code: int, findings: List[Dict[str, Any]], expected_policy: str) -> None:
    """Fail closed if the second findings read disagrees with the CLI verdict."""
    try:
        with open(path, encoding="utf-8") as stream:
            verdict = json.load(stream)
        if not isinstance(verdict, dict):
            raise ValueError()
        cid = verdict.get("campaignId")
        if not isinstance(cid, str) or not _re.fullmatch(r"[A-Za-z0-9_-]{1,200}", cid):
            raise ValueError()
        if any(row.get("campaignId") != cid for row in findings):
            raise ValueError()
        if type(verdict.get("total")) is not int or verdict["total"] != len(findings):
            raise ValueError()
        fail_on = verdict.get("failOn")
        policy = expected_policy.strip().lower()
        expected = (list(CQ_SEVERITY) if policy in ("all", "any") else
                    [] if policy in ("none", "") else
                    list(dict.fromkeys(word.strip() for word in policy.split(",") if word.strip())))
        if (not isinstance(fail_on, list) or fail_on != expected or len(fail_on) > 5
                or len(set(map(str, fail_on))) != len(fail_on)
                or any(not isinstance(x, str) or x not in CQ_SEVERITY for x in fail_on)):
            raise ValueError()
        offending = {severity: sum(row["severity"] == severity for row in findings)
                     for severity in fail_on}
        offending = {k: v for k, v in offending.items() if v}
        if verdict.get("offending") != offending:
            raise ValueError()
        should_fail = bool(offending)
        if (exit_code not in (0, 2)
                or verdict.get("verdict") != ("fail" if should_fail else "pass")
                or exit_code != (2 if should_fail else 0)):
            raise ValueError()
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        raise ValueError("Assessment identity, findings counts or fail-policy verdict disagree") from None


def load_findings(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ValueError("Cannot read a valid findings document") from exc
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict) and "findings" in data:
        arr = data["findings"]
    elif isinstance(data, dict) and "data" in data:
        arr = data["data"]
    else:
        raise ValueError("Findings document needs an array or a findings/data array")
    if not isinstance(arr, list):
        raise ValueError("Findings envelope needs an array")
    seen_ids = set()
    for f in arr:
        if not isinstance(f, dict) or not isinstance(f.get("id"), str) or not f["id"].strip():
            raise ValueError("Each finding needs a string identity")
        if f["id"] in seen_ids:
            raise ValueError("Findings document contains duplicate identities")
        seen_ids.add(f["id"])
        if not isinstance(f.get("severity"), str) or f["severity"] not in CQ_SEVERITY:
            raise ValueError("Each finding needs a recognized severity")
        for key in ("title", "category", "endpoint", "cve", "mitreAttackId", "mitreAttackName"):
            if f.get(key) is not None and not isinstance(f[key], str):
                raise ValueError("Finding text metadata has an invalid type")
        score = f.get("cvssScore")
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 10):
            raise ValueError("Finding CVSS score is invalid")
    return arr


def to_code_quality(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in findings:
        path = _endpoint_to_path(f.get("endpoint"))
        sev = _norm_sev(f.get("severity"))
        category = _category(f)
        cvss = f.get("cvssScore")
        tag = " [Darkmoon %s%s]" % (
            category, (" · CVSS %.1f" % cvss) if isinstance(cvss, (int, float)) else "")
        out.append({
            "description": _shared_text(f) + tag,
            "check_name": "darkmoon/%s" % category,
            "fingerprint": _fingerprint(f, path),
            "severity": CQ_SEVERITY[sev],
            "location": {"path": path, "lines": {"begin": 1}},
        })
    return out


def _identifiers(f: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids: List[Dict[str, Any]] = []
    category = _category(f)
    ids.append({"type": "darkmoon_category",
                "name": "Darkmoon: %s" % category, "value": category})
    cwe, owasp = CAT_ENRICH.get(category, (None, None))
    if cwe:
        num = cwe.replace("CWE-", "")
        ids.append({"type": "cwe", "name": cwe, "value": num,
                    "url": "https://cwe.mitre.org/data/definitions/%s.html" % num})
    cve = str(f.get("cve") or "").strip()
    if _re.fullmatch(r"CVE-[0-9]{4}-[0-9]{4,}", cve, flags=_re.I):
        ids.append({"type": "cve", "name": cve, "value": cve})
    mitre = str(f.get("mitreAttackId") or "").strip()
    if _re.fullmatch(r"T[0-9]{4}(?:\.[0-9]{3})?", mitre):
        ids.append({"type": "darkmoon_mitre",
                    "name": str(f.get("mitreAttackName") or mitre), "value": mitre})
    return ids


def to_sast(findings: List[Dict[str, Any]], schema_version: str,
            tool_version: str, edition: str, failed: bool = False) -> Dict[str, Any]:
    vulns: List[Dict[str, Any]] = []
    for f in findings:
        path = _endpoint_to_path(f.get("endpoint"))
        sev = _norm_sev(f.get("severity"))
        vuln = {
            "id": _fingerprint(f, path),
            "name": _shared_text(f)[:255],
            "description": _shared_text(f),  # redaction-safe title only
            "severity": SAST_SEVERITY[sev],
            "identifiers": _identifiers(f),
            "location": {"file": path, "start_line": 1},
        }
        vulns.append(vuln)
    vendor = {"name": "ASC-IT — Darkmoon"}
    engine = {"id": "darkmoon", "name": "Darkmoon", "version": tool_version, "vendor": vendor}
    now = _now()
    return {
        "version": schema_version,
        "scan": {
            "type": "sast", "status": "failure" if failed else "success",
            "start_time": now, "end_time": now,
            "analyzer": dict(engine), "scanner": dict(engine),
        },
        "vulnerabilities": vulns,
    }


def _write(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Map Darkmoon findings to GitLab reports")
    ap.add_argument("--findings", required=True)
    ap.add_argument("--codequality", required=True)
    ap.add_argument("--sast", default="")
    ap.add_argument("--sast-schema-version", default=DEFAULT_SAST_SCHEMA_VERSION)
    ap.add_argument("--tool-version", default="unknown")
    ap.add_argument("--edition", default="oss")
    ap.add_argument("--scan-failed", action="store_true", help="Mark diagnostic reports as an unsuccessful assessment")
    ap.add_argument("--run-json", default="", help="Completed CLI verdict for strict identity/count comparison")
    ap.add_argument("--run-exit-code", type=int, default=1)
    ap.add_argument("--expected-fail-on", default="critical,high")
    args = ap.parse_args(argv)

    failed = args.scan_failed
    try:
        findings = load_findings(args.findings)
    except ValueError as exc:
        _warn(str(exc) + "; assessment result is unavailable")
        findings = []
        failed = True

    if not failed and args.run_json:
        try:
            verify_run_verdict(args.run_json, args.run_exit_code, findings, args.expected_fail_on)
        except ValueError as exc:
            _warn(str(exc) + "; assessment result is unavailable")
            failed = True
            findings = []

    cq = to_code_quality(findings)
    _write(args.codequality, cq)
    _warn("wrote %d code-quality entries -> %s" % (len(cq), args.codequality))

    if args.sast:
        sast = to_sast(findings, args.sast_schema_version, args.tool_version, args.edition, failed=failed)
        _write(args.sast, sast)
        _warn("wrote %d SAST vulnerabilities -> %s" % (len(sast["vulnerabilities"]), args.sast))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
