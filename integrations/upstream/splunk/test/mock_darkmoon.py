#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal mock Darkmoon Pro REST API for testing the "Send to Darkmoon" alert
action offline. Records every launch to a JSON file and answers the two endpoints
the alert action calls. Standard library only.

  GET  /api/v1/system/info     -> {edition: pro, ...}
  POST /api/v1/retest          -> {retest_id, run_id, base_campaign_id}
  POST /api/v1/run/campaign    -> {run_id, pid, command}
  GET  /_calls                 -> the recorded launches (for assertions)
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

CALLS_FILE = os.environ.get("MOCK_CALLS_FILE", "/tmp/mock_darkmoon_calls.json")


def _record(entry):
    calls = []
    if os.path.exists(CALLS_FILE):
        try:
            with open(CALLS_FILE) as fh:
                calls = json.load(fh)
        except Exception:
            calls = []
    calls.append(entry)
    with open(CALLS_FILE, "w") as fh:
        json.dump(calls, fh)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/v1/system/info"):
            return self._send(200, {"edition": "pro", "api_version": "1.0.0",
                                    "contract_version": "1"})
        if self.path.startswith("/_calls"):
            calls = []
            if os.path.exists(CALLS_FILE):
                with open(CALLS_FILE) as fh:
                    calls = json.load(fh)
            return self._send(200, calls)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}
        has_auth = bool(self.headers.get("Authorization"))
        entry = {"path": self.path, "payload": payload, "has_auth": has_auth}
        _record(entry)
        if self.path.startswith("/api/v1/retest"):
            return self._send(200, {"retest_id": "retest_mock01",
                                    "run_id": "run_mock01",
                                    "base_campaign_id": "camp_mock"})
        if self.path.startswith("/api/v1/run/campaign"):
            return self._send(200, {"run_id": "run_mock02", "pid": 4242,
                                    "command": "opencode run"})
        return self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass  # quiet


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8443
    if os.path.exists(CALLS_FILE):
        os.remove(CALLS_FILE)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
