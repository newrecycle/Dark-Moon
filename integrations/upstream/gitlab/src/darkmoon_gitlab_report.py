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

Stdlib only; degrades gracefully (missing/invalid input -> valid empty reports).
This is part of the GitLab component, not the darkmoon-ci CLI.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re as _re
import sys
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


def _sast_time(value: Any) -> str:
    """GitLab SAST schema requires 'yyyy-mm-ddThh:mm:ss' (no timezone suffix)."""
    m = _re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", str(value or ""))
    return m.group(1) if m else _now()


def _norm_sev(value: Any) -> str:
    s = str(value or "").strip().lower()
    return s if s in CQ_SEVERITY else "info"


def _endpoint_to_path(endpoint: Any) -> str:
    """'POST /rest/user/login' -> 'rest/user/login' (redaction-safe locus)."""
    e = str(endpoint or "").strip()
    if not e:
        return ".darkmoon/report.md"
    # drop a leading HTTP method
    e = _re.sub(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+", "", e, flags=_re.I)
    e = _re.sub(r"^[a-zA-Z]+://", "", e)   # scheme
    e = _re.sub(r"^[^/]+", "", e) if "://" in str(endpoint) else e  # host if any
    e = e.split("?")[0].strip().lstrip("/")
    return e or ".darkmoon/report.md"


def _fingerprint(f: Dict[str, Any], path: str) -> str:
    basis = "|".join([str(f.get("id") or ""), path, str(f.get("title") or "")])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _shared_text(f: Dict[str, Any]) -> str:
    """Redaction-safe: the finding TITLE only (never description/evidence)."""
    return (str(f.get("title") or "").strip() or str(f.get("id") or "Darkmoon finding"))[:1000]


def load_findings(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        _warn("findings file not found: %s -> empty reports" % path)
        return []
    except (OSError, ValueError) as exc:
        _warn("cannot parse findings (%s) -> empty reports" % exc)
        return []
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        arr = data.get("findings") or data.get("data") or []
    else:
        arr = []
    return [f for f in arr if isinstance(f, dict)]


def to_code_quality(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in findings:
        path = _endpoint_to_path(f.get("endpoint"))
        sev = _norm_sev(f.get("severity"))
        category = str(f.get("category") or "finding").strip() or "finding"
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
    category = str(f.get("category") or "finding").strip() or "finding"
    ids.append({"type": "darkmoon_category",
                "name": "Darkmoon: %s" % category, "value": category})
    cwe, owasp = CAT_ENRICH.get(category, (None, None))
    if cwe:
        num = cwe.replace("CWE-", "")
        ids.append({"type": "cwe", "name": cwe, "value": num,
                    "url": "https://cwe.mitre.org/data/definitions/%s.html" % num})
    cve = str(f.get("cve") or "").strip()
    if cve and cve.lower() != "null":
        ids.append({"type": "cve", "name": cve, "value": cve})
    mitre = str(f.get("mitreAttackId") or "").strip()
    if mitre:
        ids.append({"type": "darkmoon_mitre",
                    "name": str(f.get("mitreAttackName") or mitre), "value": mitre})
    return ids


def to_sast(findings: List[Dict[str, Any]], schema_version: str,
            tool_version: str, edition: str) -> Dict[str, Any]:
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
        solution = str(f.get("remediation") or "").strip()
        if solution:
            vuln["solution"] = solution
        vulns.append(vuln)
    vendor = {"name": "ASC-IT — Darkmoon"}
    engine = {"id": "darkmoon", "name": "Darkmoon", "version": tool_version, "vendor": vendor}
    now = _now()
    return {
        "version": schema_version,
        "scan": {
            "type": "sast", "status": "success",
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
    args = ap.parse_args(argv)

    findings = load_findings(args.findings)

    cq = to_code_quality(findings)
    _write(args.codequality, cq)
    _warn("wrote %d code-quality entries -> %s" % (len(cq), args.codequality))

    if args.sast:
        sast = to_sast(findings, args.sast_schema_version, args.tool_version, args.edition)
        _write(args.sast, sast)
        _warn("wrote %d SAST vulnerabilities -> %s" % (len(sast["vulnerabilities"]), args.sast))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
