"""Disposable path-only HTTP fixture; never starts an assessment worker."""
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["DARKMOON_SHARED_DIR"])
os.environ["DARKMOON_DATA_DIR"] = str(root / "data")
from api import json_storage as data
from community.server import HTTPServer, handler_for
from community.service import Service

service = Service(root, root / "control", [sys.executable, "-c", "pass"])
cid = "camp_path_browser"
data.save_campaign({"id": cid, "status": "completed", "target_id": "target_browser"})
data._write_json(data.INFRASTRUCTURE_DIR / (cid + ".json"), [
    {"id": "a", "label": "Fixture entry", "connections": ["b"]},
    {"id": "b", "label": "Fixture service", "connections": ["c"]},
    {"id": "c", "label": "Fixture database"},
])
data.save_vulnerabilities(cid, [
    {"id": "f1", "campaign_id": cid, "node_id": "b", "title": "Fixture finding one",
     "status": "confirmed", "severity": "high", "evidence": {"output": "PRIVATE-PATH-BROWSER"}},
    {"id": "f2", "campaign_id": cid, "node_id": "c", "title": "Fixture finding two",
     "status": "exploited", "severity": "high", "evidence": {"output": "PRIVATE-PATH-BROWSER"}},
])
server = HTTPServer(("127.0.0.1", 0), handler_for(service, {"127.0.0.1"}))
print(json.dumps({"port": server.server_port, "token": service.token, "campaign_id": cid}), flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
    service.close()
