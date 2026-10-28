"""Authenticated local dashboard. Run with python -m community.server.

Install mcp/community/requirements.txt before starting. One daemon owns the
job/scheduler state directory.
"""
import argparse
import fcntl
import hashlib
import json
import logging
import os
import signal
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from api import json_storage as data
from . import reports
from .service import Service, graph_for
from .store import Store, identifier

STATIC = Path(__file__).with_name("static")


class HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32


def handler_for(service, allowed_hosts):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, format, *args):
            # Avoid query strings, auth values, target data and tokens in logs.
            logging.info("HTTP %s %s", self.command, self.path.split("?", 1)[0][:160])

        def send(self, content, kind="application/json", status=200, filename=None, extra_headers=None):
            self.close_connection = True
            if isinstance(content, (dict, list)):
                content = json.dumps(content, ensure_ascii=False).encode()
            elif isinstance(content, str):
                content = content.encode()
            self.send_response(status)
            self.send_header("Content-Type", kind + ("; charset=utf-8" if kind.startswith("text/") or kind == "application/json" else ""))
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(content)

        def body(self):
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Transfer encoding is unsupported")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 256 * 1024:
                raise ValueError("Request body exceeds 256 KiB")
            if "application/json" not in self.headers.get("Content-Type", ""):
                raise ValueError("Content-Type must be application/json")
            value = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
            return value

        def _dispatch(self, method):
            try:
                self.dispatch(method)
            except KeyError:
                self.send({"error": "Not found"}, status=404)
            except PermissionError as exc:
                self.send({"error": str(exc)}, status=403)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.close_connection = True
                self.send({"error": str(exc)}, status=400)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            except Exception:
                logging.exception("Dashboard request failed")
                self.send({"error": "Internal error; see dashboard process log"}, status=500)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PATCH(self):
            self._dispatch("PATCH")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def dispatch(self, method):
            # Defend loopback services against DNS rebinding. Explicit reverse
            # proxy names can be added through --allow-host.
            host = urlsplit("//" + self.headers.get("Host", "")).hostname
            if host not in allowed_hosts:
                self.close_connection = True
                return self.send({"error": "Host is not allowed"}, status=403)
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                self.close_connection = True
                return self.send({"error": "Cross-origin requests are disabled"}, status=403)
            path = unquote(urlsplit(self.path).path)
            if method == "GET" and path in {"/", "/callback", "/app.js", "/app.css", "/workspace.js", "/paths.js", "/finding-query.js"}:
                name, kind = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                              "/callback": ("index.html", "text/html"), "/workspace.js": ("workspace.js", "text/javascript"),
                              "/app.css": ("app.css", "text/css"), "/paths.js": ("paths.js", "text/javascript"),
                              "/finding-query.js": ("finding-query.js", "text/javascript")}[path]
                return self.send((STATIC / name).read_bytes(), kind)
            if method == "GET" and path == "/healthz":
                return self.send({"status": "ok"})
            if service.api.public(self, method, path):
                return
            identity = service.identity(self.headers.get("Authorization"))
            if not identity:
                self.close_connection = True
                return self.send({"error": "Bearer token required"}, status=401)
            if service.api.dispatch(self, method, path, identity):
                return
            if method == "GET" and path == "/metrics":
                return self.send(service.metrics(), "text/plain; version=0.0.4")
            if method == "GET" and path in {"/api/v1/events", "/api/v1/events/stream"}:
                return self.events()
            if method == "GET" and path == "/api/v1/overview":
                return self.send(service.snapshot())
            if method == "GET" and path == "/api/v1/integrations/findings":
                return self.send(service.metadata())
            parts = path.strip("/").split("/")
            if parts[:2] != ["api", "v1"]:
                raise KeyError(path)
            parts = parts[2:]
            if method == "GET" and parts == ["capabilities"]:
                return self.send({"edition": "community", "version": 1, "publishing": False,
                                  "features": ["dashboard", "campaigns", "findings", "graph", "schedules", "reports", "local_remediation", "metadata", "metrics"]})
            if method == "GET" and len(parts) == 1 and parts[0] in {"projects", "targets", "campaigns", "findings", "jobs", "schedules", "remediations"}:
                return self.send(service.snapshot()[parts[0]])
            if method == "POST" and parts == ["campaigns"]:
                job = service.launch(self.body(), key=self.headers.get("Idempotency-Key"))
                return self.send(job, status=202)
            if method == "POST" and parts == ["remediations"]:
                return self.send(service.prepare_remediation(self.body()), status=202)
            if method == "GET" and len(parts) == 3 and parts[0] == "remediations" and parts[2] == "patch":
                proposal_id = identifier(parts[1])
                path = service.store.root / "remediation" / proposal_id / "fix.patch"
                if not path.is_file():
                    raise KeyError(proposal_id)
                return self.send(path.read_bytes(), "text/x-diff", filename=proposal_id + ".patch")
            if method == "GET" and len(parts) >= 2 and parts[0] == "campaigns":
                campaign = service.campaign(identifier(parts[1]))
                if len(parts) == 2:
                    return self.send(campaign)
                if len(parts) == 3:
                    if parts[2] == "findings":
                        return self.send(campaign["findings"])
                    if parts[2] == "graph":
                        return self.send(service.graph(parts[1]))
                    if parts[2] == "report.md":
                        return self.send(reports.markdown(campaign), "text/markdown", filename=parts[1] + ".md")
                    if parts[2] == "report.pdf":
                        try:
                            content = reports.pdf(campaign)
                        except ImportError:
                            return self.send({"error": "PDF export requires reportlab: install mcp/community/requirements.txt"}, status=503)
                        return self.send(content, "application/pdf", filename=parts[1] + ".pdf")
                    if parts[2] == "report.json":
                        return self.send(campaign, filename=parts[1] + ".json")
            if method == "PATCH" and len(parts) == 4 and parts[0] == "campaigns" and parts[2] == "findings":
                return self.send(service.change_finding(parts[1], parts[3], self.body()))
            if len(parts) in {2, 3} and parts[0] == "jobs":
                job = service.store.get("jobs", identifier(parts[1]))
                if not job:
                    raise KeyError(parts[1])
                if method == "GET" and len(parts) == 2:
                    return self.send(job)
                if method == "GET" and parts[2:] == ["log"]:
                    log = service.store.job_path(parts[1])
                    content = log.read_bytes() if log.exists() else b""
                    return self.send(content, "text/plain")
                if method == "POST" and parts[2:] == ["cancel"]:
                    self.body()
                    cancelled = service.queue.cancel(parts[1])
                    if cancelled["status"] == "cancelled":
                        service._finished(cancelled)
                    return self.send(cancelled)
            if method == "POST" and parts == ["schedules"]:
                return self.send(service.scheduler.create(self.body()), status=201)
            if len(parts) == 2 and parts[0] == "schedules":
                item = service.store.get("schedules", identifier(parts[1]))
                if not item:
                    raise KeyError(parts[1])
                if method == "PATCH":
                    raw = self.body()
                    if set(raw) != {"enabled"} or not isinstance(raw["enabled"], bool):
                        raise ValueError("PATCH accepts only {enabled: true/false}")
                    return self.send(service.scheduler.set_enabled(parts[1], raw["enabled"]))
                if method == "DELETE":
                    def remove(state):
                        state["schedules"].pop(item["id"], None)
                        return {"deleted": item["id"]}
                    return self.send(service.store.update(remove))
            raise KeyError(path)

        def events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            # Notify of revisions rather than streaming secrets or entire
            # assessment dumps. fetch() streams permit an Authorization header.
            previous = None
            from urllib.parse import parse_qs
            query = parse_qs(urlsplit(self.path).query)
            requested = set(query.get("events", [""])[0].split(",")) - {""}
            event_rows = service.store.items("events")
            last_id = self.headers.get("Last-Event-ID") or query.get("since", [None])[0]
            seen = {e["id"] for e in event_rows} if not last_id else set()
            if last_id and str(last_id).isdigit():
                seen = {e["id"] for e in event_rows if e.get("seq", 0) <= int(last_id)}
            elif last_id:
                for event in event_rows:
                    seen.add(event["id"])
                    if event["id"] == last_id:
                        break
            for _ in range(30):
                digest = hashlib.sha256(json.dumps(service.snapshot(), sort_keys=True).encode()).hexdigest()
                payload = f"event: revision\ndata: {digest}\n\n" if digest != previous else ": heartbeat\n\n"
                self.wfile.write(payload.encode())
                for event in service.store.items("events"):
                    if event["id"] not in seen:
                        seen.add(event["id"])
                        if not requested or event["event"] in requested:
                            self.wfile.write(("id: "+str(event.get("seq", event["id"]))+"\ndata: "+json.dumps(event)+"\n\n").encode())
                self.wfile.flush()
                previous = digest
                time.sleep(1)

        def run_events(self, run_id):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            offset = 0
            for _ in range(30):
                job = service.store.get("jobs", run_id)
                path = service.store.job_path(run_id)
                text = path.read_text(errors="replace") if path.exists() else ""
                if len(text) > offset:
                    self.wfile.write(("data: "+json.dumps({"type": "output", "text": text[offset:], "campaign_id": job["campaign_id"]})+"\n\n").encode())
                    offset = len(text)
                if job["status"] not in {"queued", "running"}:
                    self.wfile.write(("data: "+json.dumps({"type": "run_completed" if job["status"] == "succeeded" else "run_error", "status": job["status"], "campaign_id": job["campaign_id"]})+"\n\n").encode())
                    self.wfile.flush()
                    return
                self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()
                time.sleep(1)
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--allow-host", action="append", default=[])
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--job-timeout", type=int, default=7200)
    args = parser.parse_args(argv)
    launcher = json.loads(os.environ["DARKMOON_LAUNCH_ARGV"]) if os.environ.get("DARKMOON_LAUNCH_ARGV") else None
    state_store = Store(args.state_dir)
    lock = (state_store.root / "daemon.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("Another dashboard already owns this state directory")
    service = Service(args.repo, state_store.root, launcher, args.job_timeout)
    allowed = {"localhost", "127.0.0.1", "::1", *args.allow_host}
    if args.host not in {"0.0.0.0", "::"}:
        allowed.add(args.host)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    server = HTTPServer((args.host, args.port), handler_for(service, allowed))
    def terminate(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, terminate)
    service.start()
    print(f"DarkMoon Community: http://{args.host}:{server.server_port}\nToken file: {service.store.root / 'access-token'} (or DARKMOON_DASHBOARD_TOKEN)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.close()
        server.server_close()
        lock.close()


if __name__ == "__main__":
    main()
