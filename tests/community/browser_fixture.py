"""Disposable offline workspace for browser acceptance tests; fake scan launcher."""

import json
import os
import sys
import threading
from pathlib import Path

os.environ["DARKMOON_DATA_DIR"] = str(
    Path(os.environ["DARKMOON_SHARED_DIR"]) / "darkmoon-data"
)

from api import json_storage as data
from api.live_push import init_live_campaign, push_finding
from community.remediation import git
from community.server import HTTPServer, handler_for
from community.service import Service

root = Path(os.environ["DARKMOON_SHARED_DIR"])
repo = root / "source-repo"
repo.mkdir(parents=True)
git(repo, "init")
git(repo, "config", "user.email", "test@example.invalid")
git(repo, "config", "user.name", "Offline browser fixture")
(repo / "app.py").write_text("message = 'vulnerable'\n")
git(repo, "add", ".")
git(repo, "commit", "-m", "Fixture")

for i, (host, name) in enumerate(
    (
        ("staging.example.com", "Staging application review"),
        ("api.example.com", "Public API assessment"),
        ("identity.example.com", "Identity service review"),
    )
):
    campaign = init_live_campaign(
        f"browser_{i}",
        host,
        f"192.0.2.{i + 1}",
        project_name=name,
        ports=[{"port": 443, "service": "https"}, {"port": 8080, "service": "http"}],
        technologies=[
            {"name": "Python", "version": "3.12"},
            {"name": "PostgreSQL", "version": "16"},
        ],
    )
    for j, severity in enumerate(("high", "medium", "low")):
        push_finding(
            campaign["campaign_id"],
            {
                "id": f"vuln_{i}_{j}",
                "title": (
                    "SQL injection in search"
                    if j == 0
                    else (
                        "Verbose error disclosure"
                        if j == 1
                        else "Missing response security header"
                    )
                ),
                "severity": severity,
                "status": "confirmed",
                "cvss_score": (8.1 if j == 0 else 5.3),
                "category": "sqli" if j == 0 else "configuration",
                "node_id": "target_" + campaign["target_id"],
                "endpoint": f"https://{host}/search",
                "description": "Untrusted input reaches a database query. <script>window.injected=true</script>",
                "evidence": {
                    "commands": ["python reproduce.py --case search"],
                    "logs": ["Differential response recorded in the isolated fixture."],
                },
                "remediation": "Use bound parameters and preserve normal search behavior.",
                "mitre_attack_id": "T1190",
                "iso27001_control": "A.8.28",
                "discovered_by_agent": "web-assessment",
            },
        )
    record = data.load_campaign(campaign["campaign_id"])
    record.update(
        status="completed",
        executive_summary="Three findings were recorded during this isolated fixture assessment. Prioritize parameterized queries, then harden error responses.",
    )
    data.save_campaign(record)

service = Service(
    root, launcher=[sys.executable, "-c", "print('Offline fake assessment launcher')"]
)
os.environ["DARKMOON_SOURCE_REPOSITORIES"] = str(repo)
config_dir = Path(os.environ["DARKMOON_DATA_DIR"])
(config_dir / "opencode.json").write_text(
    json.dumps(
        {
            "model": "openai/fixture-model",
            "mcp": {"darkmoon": {"enabled": True}},
            "provider": {
                "openai": {
                    "name": "OpenAI fixture",
                    "models": {
                        "fixture-model": {"name": "Fixture model"},
                        "fixture-second": {"name": "Second fixture model"},
                    },
                }
            },
        }
    )
)
(config_dir / "auth.json").write_text(
    json.dumps(
        {
            "openai": {
                "type": "oauth",
                "access": "fixture-native-access-not-for-ui",
                "refresh": "fixture-native-refresh-not-for-ui",
                "expires": 9999999999999,
            }
        }
    )
)
# A real loopback HTTP fixture for the documented native OpenCode contract.
# It never contacts a provider, runs a model, or opens an external browser.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class NativeHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        import base64

        expected = (
            "Basic " + base64.b64encode(b"opencode:fixture-bridge-password").decode()
        )
        if self.headers.get("Authorization") != expected:
            self.send_response(401)
            self.end_headers()
            return
        config = json.loads((config_dir / "opencode.json").read_text())
        auth = json.loads((config_dir / "auth.json").read_text())
        body = json.loads(
            self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"
        )
        result = True
        if self.command == "GET" and self.path == "/global/health":
            result = {"healthy": True, "version": "fixture-native"}
        elif self.command == "GET" and self.path == "/config":
            result = config
        elif self.command == "GET" and self.path == "/provider":
            result = {
                "all": [
                    {
                        "id": pid,
                        "name": p.get("name", pid),
                        "models": p.get("models", {}),
                    }
                    for pid, p in config["provider"].items()
                ],
                "connected": list(auth),
            }
        elif self.command == "GET" and self.path == "/provider/auth":
            result = {
                "openai": [
                    {"type": "api", "label": "API key"},
                    {"type": "oauth", "label": "Browser sign-in (fixture)"},
                ]
            }
        elif self.command == "PATCH" and self.path == "/global/config":
            config.update(body)
            (config_dir / "opencode.json").write_text(json.dumps(config))
        elif self.command == "PUT" and self.path.startswith("/auth/"):
            auth[self.path.rsplit("/", 1)[1]] = body
            (config_dir / "auth.json").write_text(json.dumps(auth))
        elif self.command == "DELETE" and self.path.startswith("/auth/"):
            auth.pop(self.path.rsplit("/", 1)[1], None)
            (config_dir / "auth.json").write_text(json.dumps(auth))
        elif self.path.endswith("/oauth/authorize"):
            result = {
                "url": "https://provider.example.invalid/authorize",
                "method": "auto",
                "instructions": "Fixture approval only; do not navigate externally. Click Save to complete.",
            }
        elif self.path.endswith("/oauth/callback"):
            auth["openai"] = {
                "type": "oauth",
                "access": "new-fixture-access-not-for-ui",
                "refresh": "new-fixture-refresh-not-for-ui",
                "expires": 9999999999999,
            }
            (config_dir / "auth.json").write_text(json.dumps(auth))
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request
    do_PATCH = handle_request
    do_DELETE = handle_request


class ModelHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/slow/models":
            __import__("time").sleep(0.3)
        if self.path not in {"/v1/models", "/slow/models"}:
            self.send_response(404)
            self.end_headers()
            return
        content = json.dumps(
            {
                "data": [
                    {"id": "available-one", "name": "Available one"},
                    {"id": "available-two", "name": "Available two"},
                ]
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


model_server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
threading.Thread(target=model_server.serve_forever, daemon=True).start()
native_server = ThreadingHTTPServer(("127.0.0.1", 0), NativeHandler)
threading.Thread(target=native_server.serve_forever, daemon=True).start()
os.environ["DARKMOON_OPENCODE_URL"] = "http://127.0.0.1:" + str(
    native_server.server_port
)
os.environ["OPENCODE_SERVER_PASSWORD"] = "fixture-bridge-password"
from community import updates

updates.status = lambda check=False: {
    "checked": bool(check),
    "update_available": False,
    "source": "offline-fixture",
}
from community.report_security import init_signer

os.environ["DARKMOON_SIGNING_PASSWORD"] = "fixture-report-signing-password"
init_signer(service.store, "Browser fixture", "fixture-report-signing-password")

service.accounts.create("fixture-admin", "offline-fixture-password", "admin")
service.operations.transport = lambda *args: (_ for _ in ()).throw(
    AssertionError("External webhook transport is disabled in browser fixtures")
)
service.start()
server = HTTPServer(("127.0.0.1", 0), handler_for(service, {"127.0.0.1"}))
print(
    json.dumps(
        {
            "port": server.server_port,
            "model_endpoint": "http://127.0.0.1:"
            + str(model_server.server_port)
            + "/v1",
            "token": service.token,
            "source_repo": str(repo),
            "campaign_id": data.load_campaigns()[0]["id"],
            "finding_id": "vuln_0_0",
        }
    ),
    flush=True,
)
try:
    server.serve_forever()
finally:
    model_server.shutdown()
    model_server.server_close()
    native_server.shutdown()
    native_server.server_close()
    service.close()
    server.server_close()
