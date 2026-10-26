#!/usr/bin/env python3
"""Real DarkMoon workflow/toolbox analysis of an owned loopback lab; no LLM.

Requires Docker on Linux and tools/lab/Dockerfile. Never accepts an external
assessment target, operator credentials, Docker socket mounts or user volumes.
"""

import argparse
import json
import os
import platform
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="darkmoon-ui-lab")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    if os.environ.get("DOCKER_HOST", "") and not os.environ["DOCKER_HOST"].startswith(
        "unix://"
    ):
        raise ValueError("This loopback lab requires a local Unix-socket Docker engine")
    os.environ["DARKMOON_NO_TELEMETRY"] = "1"
    os.environ["DARKMOON_DATA_DIR"] = str(root / "data")
    os.environ["DARKMOON_REPORTS_DIR"] = str(root / "reports")
    os.environ["DARKMOON_DASHBOARD_TOKEN"] = uuid.uuid4().hex
    os.environ.pop("DARKMOON_ADMIN_PASSWORD", None)
    os.environ.pop("DARKMOON_OPENCODE_URL", None)
    from src.docker_client import DarkmoonDockerClient
    from src.tools.workflows.base import BaseWorkflow
    from api import json_storage as data
    from api.live_push import init_live_campaign, push_finding, finalize_campaign
    from community.server import HTTPServer, handler_for
    from community.service import Service

    class Lab(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            body = "<h1>Owned DarkMoon lab</h1>"
            if parsed.path == "/reflect":
                body += parse_qs(parsed.query).get("value", [""])[0]
            status = 401 if parsed.path == "/private" else 200
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode())))
            self.end_headers()
            self.wfile.write(body.encode())

    target = ThreadingHTTPServer(("127.0.0.1", 0), Lab)
    threading.Thread(target=target.serve_forever, daemon=True).start()
    client = DarkmoonDockerClient(
        container_name="darkmoon-ui-lab-" + uuid.uuid4().hex[:12]
    )
    container = None
    service = dashboard = None
    started = time.monotonic()
    try:
        container = client.client.containers.run(
            args.image,
            detach=True,
            name=client.container_name,
            network_mode="host",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            read_only=True,
            pids_limit=64,
            mem_limit="256m",
        )
        workflow = BaseWorkflow(client)
        base = "http://127.0.0.1:" + str(target.server_port)
        campaign_id = init_live_campaign(
            "owned_lab_" + uuid.uuid4().hex[:8],
            base,
            "127.0.0.1",
            project_name="Owned loopback HTTP analysis",
            ports=[{"port": target.server_port, "service": "http"}],
            technologies=[
                {"name": "Python http.server", "version": platform.python_version()}
            ],
        )["campaign_id"]
        service_node = next(
            n["id"]
            for n in data.load_infrastructure(campaign_id)
            if n.get("node_type") == "service"
        )
        probes = [
            ("headers", base + "/", "HTTP response headers"),
            (
                "reflection",
                base + "/reflect?value=%3Cstrong%3Edm-probe%3C%2Fstrong%3E",
                "Inert HTML reflection",
            ),
            ("private", base + "/private", "Unauthorized access rejection"),
        ]
        evidence = {}
        for key, url, label in probes:
            command = "curl --noproxy '*' --max-time 10 -sS -i '" + url + "'"
            ok, _, output = workflow.execute_step(
                label, command, timeout=15, parse_json=False
            )
            if not ok:
                raise RuntimeError("Real toolbox probe failed: " + key)
            evidence[key] = {
                "commands": [command],
                "raw_request": "GET " + url + " HTTP/1.1",
                "raw_response": output,
                "logs": [
                    "Real Docker exec via DarkMoon BaseWorkflow and DarkmoonDockerClient"
                ],
            }
        headers = evidence["headers"]["raw_response"].lower()
        if (
            "x-content-type-options:" not in headers
            and "content-security-policy:" not in headers
        ):
            push_finding(
                campaign_id,
                {
                    "id": "vuln_lab_headers",
                    "title": "Lab omits browser hardening headers",
                    "severity": "low",
                    "status": "confirmed",
                    "category": "configuration",
                    "discovered_by_agent": "owned-lab-workflow",
                    "node_id": service_node,
                    "endpoint": base,
                    "description": "CSP and X-Content-Type-Options were absent from the measured lab response. This is a hardening observation, not proof of exploitation.",
                    "evidence": evidence["headers"],
                    "remediation": "Set an appropriate CSP and X-Content-Type-Options: nosniff.",
                },
            )
        if "<strong>dm-probe</strong>" in evidence["reflection"]["raw_response"]:
            push_finding(
                campaign_id,
                {
                    "id": "vuln_lab_html",
                    "title": "Lab reflects unescaped inert HTML",
                    "severity": "medium",
                    "status": "confirmed",
                    "category": "html-injection",
                    "discovered_by_agent": "owned-lab-workflow",
                    "node_id": service_node,
                    "endpoint": base + "/reflect",
                    "description": "An inert strong element was reflected literally into text/html. JavaScript execution and XSS were not tested or asserted.",
                    "evidence": evidence["reflection"],
                    "remediation": "HTML-escape untrusted values before rendering.",
                },
            )
        assert "401 Unauthorized" in evidence["private"]["raw_response"]
        finalize_campaign(
            campaign_id,
            duration_seconds=int(time.monotonic() - started),
            executive_summary="Owned loopback analysis: measured HTML reflection and missing browser hardening headers; private route returned 401. Deterministic DarkMoon workflow, no LLM or exploitation claim.",
        )
        campaign = data.load_campaign(campaign_id)
        campaign["analysis_origin"] = {
            "kind": "owned-loopback-lab",
            "engine": "DarkMoon BaseWorkflow / DarkmoonDockerClient",
            "llm_used": False,
        }
        data.save_campaign(campaign)
        service = Service(
            Path(__file__).resolve().parents[1], root / "control", launcher=["false"]
        )
        dashboard = HTTPServer(("127.0.0.1", 0), handler_for(service, {"127.0.0.1"}))
        threading.Thread(target=dashboard.serve_forever, daemon=True).start()
        checks = []
        for route in [
            "/api/v1/campaigns/" + campaign_id,
            "/api/v1/options",
            "/api/v1/campaigns/" + campaign_id + "/graph",
            "/api/v1/campaigns/" + campaign_id + "/report.md",
            "/api/v1/campaigns/" + campaign_id + "/report.pdf",
        ]:
            req = urllib.request.Request(
                "http://127.0.0.1:" + str(dashboard.server_port) + route,
                headers={"Authorization": "Bearer " + service.token},
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                content = response.read()
            assert content
            checks.append(route)
        result = {
            "status": "passed",
            "campaign_id": campaign_id,
            "target": base,
            "engine": "real DarkMoon Docker adapter and BaseWorkflow",
            "llm_assessment": False,
            "findings": len(data.load_vulnerabilities(campaign_id)),
            "private_route_status": 401,
            "webui_routes_checked": checks,
            "external_targets_contacted": False,
            "probes": evidence,
        }
        assert result["findings"] == 2
        (root / "analysis.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({k: v for k, v in result.items() if k != "probes"}, indent=2))
    finally:
        if dashboard:
            dashboard.shutdown()
            dashboard.server_close()
        if service:
            service.close()
        if container:
            container.remove(force=True)
        target.shutdown()
        target.server_close()


if __name__ == "__main__":
    main()
