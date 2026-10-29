#!/usr/bin/env python3
"""Read-only acceptance against an explicitly owned, disposable GitLab host.

Run only AFTER creating a real GitLab pipeline with the generated component
on a localhost-bound test server and a supported licensed security tier.
A schema-valid file or successful artifact upload is not security ingestion.
"""
import ipaddress
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("GitLab test host redirected; refusing to forward token")


def artifact_report(raw):
    """An archive or arbitrary nonempty response does not prove report upload."""
    report = json.loads(raw)
    if (not isinstance(report, dict) or not isinstance(report.get("vulnerabilities"), list)
            or report.get("scan", {}).get("scanner", {}).get("id") != "darkmoon"
            or report.get("scan", {}).get("type") != "sast"
            or report.get("scan", {}).get("status") not in ("success", "failure")):
        raise ValueError("GitLab did not return the Darkmoon SAST JSON artifact")
    return report


def main():
    env = os.environ
    if env.get("GITLAB_ACCEPTANCE_OWNED") != "yes":
        raise SystemExit("REFUSED: set GITLAB_ACCEPTANCE_OWNED=yes for a disposable owned host")
    base = env.get("GITLAB_ACCEPTANCE_URL", "").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        raise SystemExit("REFUSED: invalid GitLab host URL")
    try:
        host = parsed.hostname or ""
        if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
            raise ValueError()
    except ValueError:
        raise SystemExit("REFUSED: this verifier requires loopback GitLab, not a shared instance")
    if parsed.path or parsed.query or parsed.fragment:
        raise SystemExit("REFUSED: unexpected host URL components")
    token = env.get("GITLAB_ACCEPTANCE_TOKEN", "")
    if not token:
        raise SystemExit("REFUSED: a temporary read-only API token is required")
    try:
        project = int(env["GITLAB_ACCEPTANCE_PROJECT_ID"])
        job = int(env["GITLAB_ACCEPTANCE_JOB_ID"])
        pipeline = int(env["GITLAB_ACCEPTANCE_PIPELINE_ID"])
        assert min(project, job, pipeline) > 0
    except (KeyError, AssertionError, ValueError):
        raise SystemExit("REFUSED: supply numeric project, job and pipeline IDs")
    opener = build_opener(NoRedirect)

    def get(resource):
        url = base + "/api/v4/projects/%d/" % project + resource
        response = opener.open(Request(url, headers={"PRIVATE-TOKEN": token}), timeout=15)
        with response:
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError("GitLab response exceeds verifier bound")
            return data

    try:
        record = json.loads(get("jobs/%d" % job))
        if record.get("pipeline", {}).get("id") != pipeline or record.get("status") != "success":
            raise ValueError("Only a successful job in the selected pipeline can prove ingestion")
        raw = get("jobs/%d/artifacts/gl-sast-report.json" % job)
        report = artifact_report(raw)
        if report["scan"]["status"] != "success" or not report["vulnerabilities"]:
            raise ValueError("Ingestion requires a successful nonempty SAST report")
        print("ARTIFACT_UPLOAD: PASS (GitLab returned nonempty SAST artifact)")
        # Ultimate is required to query project vulnerability findings.
        query = urlencode({"pipeline_id": pipeline, "per_page": 100})
        findings = json.loads(get("vulnerability_findings?" + query))
        if not isinstance(findings, list):
            raise ValueError("GitLab vulnerability findings response is not a list")
        matching = [f for f in findings
                    if f.get("report_type") == "sast"
                    and (f.get("scanner", {}).get("external_id") == "darkmoon"
                         or str(f.get("scanner", {}).get("name", "")).lower() == "darkmoon")]
        if len(matching) != len(report["vulnerabilities"]):
            raise ValueError("Ingested Darkmoon count does not match the uploaded report")
        print("SERVER_INGESTION: PASS (%d Darkmoon findings from pipeline %d)" %
              (len(matching), pipeline))
        return 0
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        # HTTP 403/404 is not a successful empty report: could be tier,
        # permissions, release compatibility or ingestion failure.
        print("SERVER_INGESTION: NOT VERIFIED (%s)" % type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
