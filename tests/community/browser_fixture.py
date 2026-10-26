"""Disposable offline workspace for browser acceptance tests; fake scan launcher."""
import json
import os
import sys
import threading
from pathlib import Path

os.environ["DARKMOON_DATA_DIR"] = str(Path(os.environ["DARKMOON_SHARED_DIR"]) / "darkmoon-data")

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

for i, (host, name) in enumerate((("staging.example.com", "Staging application review"), ("api.example.com", "Public API assessment"), ("identity.example.com", "Identity service review"))):
    campaign = init_live_campaign(f"browser_{i}", host, f"192.0.2.{i+1}", project_name=name,
        ports=[{"port": 443, "service": "https"}, {"port": 8080, "service": "http"}],
        technologies=[{"name": "Python", "version": "3.12"}, {"name": "PostgreSQL", "version": "16"}])
    for j, severity in enumerate(("high", "medium", "low")):
        push_finding(campaign["campaign_id"], {"id": f"vuln_{i}_{j}",
            "title": ("SQL injection in search" if j == 0 else ("Verbose error disclosure" if j == 1 else "Missing response security header")),
            "severity": severity, "status": "confirmed", "cvss_score": (8.1 if j == 0 else 5.3),
            "category": "sqli" if j == 0 else "configuration", "node_id": "target_"+campaign["target_id"], "endpoint": f"https://{host}/search",
            "description": "Untrusted input reaches a database query. <script>window.injected=true</script>",
            "evidence": {"commands": ["python reproduce.py --case search"], "logs": ["Differential response recorded in the isolated fixture."]},
            "remediation": "Use bound parameters and preserve normal search behavior.", "mitre_attack_id": "T1190", "iso27001_control": "A.8.28",
            "discovered_by_agent": "web-assessment"})
    record = data.load_campaign(campaign["campaign_id"])
    record.update(status="completed", executive_summary="Three findings were recorded during this isolated fixture assessment. Prioritize parameterized queries, then harden error responses.")
    data.save_campaign(record)

service = Service(Path(__file__).resolve().parents[2], launcher=[sys.executable, "-c", "print('Offline fake assessment launcher')"])
service.accounts.create("fixture-admin", "offline-fixture-password", "admin")
service.operations.transport = lambda *args: (_ for _ in ()).throw(AssertionError("External webhook transport is disabled in browser fixtures"))
service.start()
server = HTTPServer(("127.0.0.1", 0), handler_for(service, {"127.0.0.1"}))
print(json.dumps({"port": server.server_port, "token": service.token, "source_repo": str(repo),
                  "campaign_id": data.load_campaigns()[0]["id"], "finding_id": "vuln_0_0"}), flush=True)
try:
    server.serve_forever()
finally:
    service.close()
    server.server_close()
