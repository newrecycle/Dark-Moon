#!/usr/bin/env python3
"""Owned-loopback Dark Moon metadata fixture. Never scans, publishes or notifies.

The synthetic target is 127.0.0.1 and only exactly scoped retests are admitted.
Test response modes can be changed using a POST to /__fixture__/mode, on loopback.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from urllib.parse import parse_qs, urlsplit

TARGET = "fixture_target"
CAMPAIGN = "fixture_campaign"
FINDING = "fixture_finding"
TOKEN = "fixture-darkmoon-token"
state = {"mode": "valid", "posts": []}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def write(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def get(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self.write(401, {"error": "unavailable"})
        path = urlsplit(self.path)
        if state["mode"] == "unavailable":
            return self.write(503, {"error": "unavailable"})
        params = parse_qs(path.query)
        rows = {
            "/api/v1/targets": [{"id": TARGET, "host": "demo-shop.local"}],
            "/api/v1/campaigns": [{"id": CAMPAIGN, "target_id": TARGET}],
            "/api/v1/vulnerabilities": [{"id": FINDING, "campaign_id": CAMPAIGN, "target_id": TARGET}],
        }.get(path.path)
        if rows is None:
            return self.write(404, {"error": "not found"})
        if state["mode"] == "empty":
            rows = []
        if state["mode"] == "foreign" and path.path == "/api/v1/vulnerabilities":
            rows = [{"id": FINDING, "campaign_id": "foreign_campaign", "target_id": TARGET}]
        if state["mode"] == "malformed":
            return self.write(200, {"data": "not-an-array"})
        if path.path == "/api/v1/campaigns" and params.get("target_id") != [TARGET]:
            rows = []
        if path.path == "/api/v1/vulnerabilities" and (params.get("campaign_id") != [CAMPAIGN]
            or params.get("target_id") != [TARGET] or params.get("q") != [FINDING]):
            rows = []
        return self.write(200, {"data": rows, "total": len(rows),
                                 "has_more": False, "offset": 0, "next_offset": None})

    def do_GET(self):
        if urlsplit(self.path).path == "/__fixture__/state":
            return self.write(200, {"mode": state["mode"], "posts": state["posts"]})
        return self.get()

    def do_POST(self):
        if urlsplit(self.path).path == "/__fixture__/mode":
            raw = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 1024)))
            if raw.get("mode") not in ("valid", "empty", "foreign", "malformed", "unavailable", "bad_launch"):
                return self.write(400, {"error": "bad mode"})
            state["mode"] = raw["mode"]
            return self.write(200, {"ok": True})
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self.write(401, {"error": "unauthorized"})
        if self.path != "/api/v1/retest":
            return self.write(404, {"error": "not found"})
        try:
            raw = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 4096)))
        except (ValueError, TypeError):
            return self.write(400, {"error": "invalid"})
        if (raw.get("target_id") != TARGET or raw.get("campaign_id") != CAMPAIGN
                or raw.get("finding_ids") != [FINDING]
                or raw.get("safe_harbor") != "non-destructive"):
            return self.write(400, {"error": "scope mismatch"})
        state["posts"].append({"target_id": TARGET, "campaign_id": CAMPAIGN, "finding_ids": [FINDING]})
        if state["mode"] == "bad_launch":
            return self.write(200, {"id": "conflicting", "retest_id": "fixture_retest"})
        return self.write(200, {"id": "fixture_retest", "retest_id": "fixture_retest",
                                 "target_id": TARGET, "base_campaign_id": CAMPAIGN,
                                 "before_ids": [FINDING], "status": "running"})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(json.dumps({"base_url": "http://127.0.0.1:" + str(server.server_port),
                      "target_id": TARGET, "campaign_id": CAMPAIGN,
                      "finding_id": FINDING}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
