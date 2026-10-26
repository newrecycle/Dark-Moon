#!/usr/bin/env python3
"""
Darkmoon REST **mock / fixture server** for reproducible local testing.

Serves the synthetic Demo Shop dataset (fixtures/api/v1/**) at the EXACT Darkmoon
REST paths, and — unlike static hosting — honours query parameters so the
PRODUCTION Grafana dashboard exercises it just like a real Darkmoon Pro API:

  GET /api/v1/system/info
  GET /api/v1/dashboard/overview
  GET /api/v1/campaigns[?target_id&status]
  GET /api/v1/campaigns/{id}
  GET /api/v1/vulnerabilities[?severity&status&category&campaign_id&target_id&project_id]
  GET /api/v1/vulnerabilities/{id}
  GET /api/v1/vulnerabilities/{id}/evidence-meta
  GET /api/v1/targets[?risk_level]
  GET /api/v1/metrics/timeseries?metric=severity|status|category&group=day
  GET /api/v1/pull-requests[?campaign_id]
  GET /api/v1/retest/{id}
  GET /health

It never serves anything but the fixtures on disk. No real data, no secrets.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api", "v1")
PORT = int(os.environ.get("PORT", "8080"))


def load(rel):
    p = os.path.join(BASE, rel)
    if not os.path.isfile(p):
        return None
    with open(p) as f:
        return json.load(f)


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quieter
        pass

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        q = {k: v[0] for k, v in parse_qs(u.query).items()}

        if path in ("/", "/health"):
            return self._send({"status": "ok", "data_dir": "fixtures", "mock": True})

        if not path.startswith("/api/v1"):
            return self._send({"error": f"Unexpected path: {path}"}, 404)

        sub = path[len("/api/v1"):]  # e.g. /vulnerabilities

        # metrics/timeseries -> pick the per-metric fixture
        if sub == "/metrics/timeseries":
            metric = q.get("metric", "severity")
            data = load(f"metrics/timeseries.{metric}.json") or load("metrics/timeseries.json")
            return self._send(data if data else {"metric": metric, "group": "day", "series": []})

        # vulnerabilities filters
        if sub == "/vulnerabilities":
            data = load("vulnerabilities.json") or {"data": [], "total": 0}
            rows = data.get("data", [])
            for key in ("severity", "status", "category", "campaign_id", "target_id", "project_id"):
                if q.get(key):
                    rows = [r for r in rows if str(r.get(key)) == q[key]]
            return self._send({"data": rows, "total": len(rows),
                               "stats": data.get("stats", {})})

        # campaigns filters
        if sub == "/campaigns":
            data = load("campaigns.json") or {"data": [], "total": 0}
            rows = data.get("data", [])
            if q.get("target_id"):
                rows = [r for r in rows if r.get("target_id") == q["target_id"]]
            if q.get("status"):
                rows = [r for r in rows if r.get("status") == q["status"]]
            return self._send({"data": rows, "total": len(rows)})

        # targets filters
        if sub == "/targets":
            data = load("targets.json") or {"data": [], "total": 0}
            rows = data.get("data", [])
            if q.get("risk_level"):
                rows = [r for r in rows if r.get("risk_level") == q["risk_level"]]
            return self._send({"data": rows, "total": len(rows)})

        # pull-requests filter
        if sub == "/pull-requests":
            data = load("pull-requests.json") or {"data": [], "total": 0}
            rows = data.get("data", [])
            if q.get("campaign_id"):
                rows = [r for r in rows if r.get("campaign_id") == q["campaign_id"]]
            return self._send({"data": rows, "total": len(rows)})

        # everything else: map path -> fixture file
        rel = sub.lstrip("/") + ".json"
        data = load(rel)
        if data is not None:
            return self._send(data)
        return self._send({"error": f"not found: {path}"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()


if __name__ == "__main__":
    print(f"Darkmoon mock (Demo Shop) on :{PORT}  fixtures={BASE}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
