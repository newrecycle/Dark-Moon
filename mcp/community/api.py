"""Pro-style REST contract, reconstructed against the public SDK and docs.

This is our implementation, not the unavailable proprietary application source.
No route publishes Git branches, opens PRs, merges code or provisions clouds.
"""
import json
import os
import re
import uuid
from collections import Counter
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

from api import json_storage as data
from . import reports
from .operations import evidence_meta, overview, safe_finding, timeseries
from .store import identifier, now

ROUTERS = ["projects", "targets", "campaigns", "vulnerabilities", "dashboard", "run", "scheduler", "auth",
           "credentials", "pull-requests", "system", "webhooks", "events", "retest", "metrics"]


def filtered(items, query, keys):
    return [item for item in items if all(not query.get(k) or str(item.get(k, "")) == query[k] for k in keys)]


def envelope(items):
    return {"data": items, "total": len(items)}


def info():
    return {"edition": "community", "api_version": "1.0.0", "contract_version": "1", "implementation": "independent",
            "features": {"auth": True, "credentials": True, "scheduler": True, "sse_progress": True,
                         "remediation": True, "privacy_gateway": True, "licensing": False, "webhooks": True,
                         "retest": True, "metrics": True, "publishing": False}, "routers": ROUTERS}


class API:
    def __init__(self, service):
        self.service = service
        self.store = service.store

    def public(self, handler, method, path):
        if method == "GET" and path == "/api/v1/system/info":
            handler.send(info())
            return True
        if method == "GET" and path == "/api/v1/auth/config":
            handler.send({"accounts_configured": bool(self.store.items("users")), "oidc": self.service.accounts.oidc_config()})
            return True
        if method == "POST" and path == "/api/v1/auth/login":
            raw = handler.body()
            try:
                handler.send(self.service.accounts.login(raw.get("username"), raw.get("password"), handler.client_address[0]))
            except PermissionError as exc:
                handler.send({"error": str(exc)}, status=429 if "Too many" in str(exc) else 401)
            return True
        if method == "GET" and path == "/api/v1/auth/oidc/start":
            result = self.service.accounts.oidc_begin()
            handler.send(result, extra_headers={"Set-Cookie": "darkmoon_oidc=" + result["state"] + "; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=300"})
            return True
        if method == "POST" and path == "/api/v1/auth/oidc/callback":
            raw = handler.body()
            cookies = SimpleCookie(handler.headers.get("Cookie", ""))
            if not cookies.get("darkmoon_oidc") or cookies["darkmoon_oidc"].value != raw.get("state"):
                raise PermissionError("OIDC browser state does not match")
            handler.send(self.service.accounts.oidc_finish(raw.get("code"), raw.get("state")),
                         extra_headers={"Set-Cookie": "darkmoon_oidc=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0"})
            return True
        return False

    def dispatch(self, handler, method, path, identity):
        if not path.startswith("/api/v1/"):
            return False
        parts = path[len("/api/v1/"):].strip("/").split("/")
        query = {k: v[-1] for k, v in parse_qs(urlsplit(handler.path).query).items()}
        resource = parts[0]
        admin = identity.get("role") == "admin"
        if method != "GET" and identity.get("role") == "viewer" and parts not in (["auth", "logout"], ["auth", "password"]):
            raise PermissionError("This account has read-only access")
        if resource in {"credentials", "webhooks"} or parts[:2] in (["auth", "users"], ["system", "integrity"]):
            if not admin:
                raise PermissionError("Administrator access is required")
        if resource == "auth":
            if method == "GET" and parts == ["auth", "me"]:
                handler.send({"user": identity})
            elif method == "POST" and parts == ["auth", "logout"]:
                self.service.accounts.logout(identity)
                handler.send({"logged_out": True})
            elif method == "POST" and parts == ["auth", "password"]:
                raw = handler.body()
                handler.send(self.service.accounts.password(identity, raw.get("old_password"), raw.get("new_password")))
            elif method == "GET" and parts == ["auth", "users"]:
                handler.send(envelope([self.service.accounts.public(u) for u in self.store.items("users")]))
            elif method == "POST" and parts == ["auth", "users"]:
                raw = handler.body()
                handler.send(self.service.accounts.create(raw.get("username"), raw.get("password"), raw.get("role", "viewer")), status=201)
            else:
                return False
            return True
        if resource == "credentials":
            if method == "GET" and len(parts) == 1:
                handler.send(envelope(self.service.vault.list()))
            elif method == "POST" and len(parts) == 1:
                handler.send({"data": self.service.vault.save(handler.body())}, status=201)
            elif len(parts) == 2 and method in {"PATCH", "PUT"}:
                if not self.store.get("credentials", parts[1]):
                    raise KeyError(parts[1])
                handler.send({"data": self.service.vault.save(handler.body(), parts[1])})
            elif method == "DELETE" and len(parts) == 2:
                handler.send(self.service.vault.delete(parts[1]))
            else:
                return False
            return True
        if resource in {"projects", "targets"}:
            load = data.load_projects if resource == "projects" else data.load_targets
            save = data.save_project if resource == "projects" else data.save_target
            if method == "GET" and len(parts) == 1:
                handler.send(envelope(filtered(load(), query, ("project_id", "status"))))
            elif method == "GET" and len(parts) >= 2:
                item = next((p for p in load() if p["id"] == identifier(parts[1])), None)
                if not item:
                    raise KeyError(parts[1])
                if parts[2:] == ["analytics"]:
                    campaigns = [c for c in data.load_campaigns() if c.get("project_id" if resource == "projects" else "target_id") == parts[1]]
                    handler.send({"data": overview(campaigns), "campaigns": campaigns,
                                  "timeseries": timeseries({"project_id" if resource == "projects" else "target_id": parts[1]})})
                elif len(parts) == 2:
                    handler.send({"data": item})
                else:
                    return False
            elif method in {"POST", "PATCH", "PUT"} and len(parts) <= 2:
                raw = handler.body()
                allowed = {"name", "description", "tags", "host", "ip", "project_id", "target_id", "status", "risk_level"}
                if not set(raw) <= allowed:
                    raise ValueError("Unsupported project/target fields")
                item = next((p for p in load() if len(parts) == 2 and p["id"] == parts[1]), None)
                if len(parts) == 2 and not item:
                    raise KeyError(parts[1])
                item = (item or {"id": ("proj_" if resource == "projects" else "tgt_")+uuid.uuid4().hex[:16], "created_at": now()}) | raw
                for key in ("project_id", "target_id"):
                    if item.get(key):
                        identifier(item[key])
                save(item)
                handler.send({"data": item}, status=201 if method == "POST" else 200)
            elif method == "DELETE" and len(parts) == 2:
                identifier(parts[1])
                if any(c.get("project_id" if resource == "projects" else "target_id") == parts[1] for c in data.load_campaigns()):
                    raise ValueError("Archive linked campaigns before deleting this record")
                file = data.PROJECTS_FILE if resource == "projects" else data.TARGETS_FILE
                with data._file_lock(file):
                    data._write_json(file, [p for p in load() if p["id"] != parts[1]])
                handler.send({"deleted": parts[1]})
            else:
                return False
            return True
        if resource == "campaigns" and method == "GET":
            if len(parts) == 1:
                handler.send(envelope(filtered(data.load_campaigns(), query, ("target_id", "project_id", "status"))))
            elif len(parts) == 2:
                campaign = self.service.campaign(parts[1])
                handler.send({"data": campaign | {"vulnerabilities": campaign["findings"]}, **campaign})
            elif parts[2:] == ["report"]:
                campaign = self.service.campaign(parts[1])
                handler.send({"campaign_id": campaign["id"], "format": "markdown", "content": reports.markdown(campaign)})
            elif parts[2:] == ["infrastructure"]:
                from .service import graph_for
                handler.send({"data": graph_for(parts[1])})
            else:
                return False
            return True
        if resource == "campaigns" and method == "POST" and len(parts) == 4 and parts[2:] == ["report", "pdf"]:
            from .report_security import secure_pdf
            raw = handler.body()
            content = secure_pdf(reports.pdf(self.service.campaign(parts[1])), self.store,
                                 password=raw.get("password"), sign=bool(raw.get("sign", True)))
            handler.send(content, "application/pdf", filename=identifier(parts[1])+".pdf")
            return True
        if resource == "vulnerabilities":
            items = filtered(data.load_all_vulnerabilities(), query, ("campaign_id", "project_id", "target_id", "severity", "status", "category"))
            if method == "GET" and len(parts) == 1:
                handler.send(envelope([safe_finding(v) for v in items]))
            elif method == "GET" and len(parts) >= 2:
                finding = data.load_vulnerability(identifier(parts[1]))
                if not finding:
                    raise KeyError(parts[1])
                if parts[2:] == ["evidence-meta"]:
                    handler.send(evidence_meta(finding))
                elif len(parts) == 2:
                    handler.send({"data": finding if admin else safe_finding(finding)})
                else:
                    return False
            elif method == "PATCH" and len(parts) == 2:
                finding = data.load_vulnerability(identifier(parts[1]))
                if not finding:
                    raise KeyError(parts[1])
                handler.send({"data": self.service.change_finding(finding["campaign_id"], finding["id"], handler.body())})
            else:
                return False
            return True
        if resource == "dashboard" and method == "GET":
            if parts[1:] in (["overview"], []):
                handler.send(overview())
            elif parts[1:] == ["analytics"]:
                handler.send({"overview": overview(), "timeseries": timeseries(query)})
            else:
                return False
            return True
        if resource == "run":
            if method == "POST" and parts[1:] == ["campaign"]:
                job = self.service.launch(handler.body(), key=handler.headers.get("Idempotency-Key"))
                handler.send({"run_id": job["id"], "campaign_id": job["campaign_id"], "status": job["status"]}, status=202)
            elif len(parts) == 3 and method == "GET" and parts[1] == "logs":
                job = self.store.get("jobs", identifier(parts[2]))
                if not job:
                    raise KeyError(parts[2])
                log = self.store.job_path(job["id"])
                lines = log.read_text(errors="replace").splitlines() if log.exists() else []
                handler.send({"data": [{"message": line} for line in lines[-2000:]], "status": job["status"], "campaign_id": job["campaign_id"]})
            elif len(parts) == 3 and parts[2] == "stop" and method == "POST":
                handler.body()
                handler.send(self.service.queue.cancel(parts[1]))
            elif len(parts) == 3 and parts[2] == "stream" and method == "GET":
                if not self.store.get("jobs", identifier(parts[1])):
                    raise KeyError(parts[1])
                handler.run_events(parts[1])
            elif len(parts) == 2 and method == "GET":
                job = self.store.get("jobs", identifier(parts[1]))
                if not job:
                    raise KeyError(parts[1])
                handler.send({"run_id": job["id"], **job})
            else:
                return False
            return True
        if resource == "scheduler":
            if method == "GET" and len(parts) == 1:
                handler.send(envelope(self.store.items("schedules")))
            elif method == "POST" and len(parts) == 1:
                raw = handler.body()
                if raw.get("run_at"):
                    raw["next_run"], raw["one_shot"] = raw["run_at"], True
                handler.send({"data": self.service.scheduler.create(raw)}, status=201)
            elif len(parts) == 2 and method in {"PATCH", "DELETE"}:
                item = self.store.get("schedules", identifier(parts[1]))
                if not item:
                    raise KeyError(parts[1])
                if method == "DELETE":
                    self.store.update(lambda state: state["schedules"].pop(parts[1]))
                    handler.send({"deleted": parts[1]})
                else:
                    raw = handler.body()
                    if set(raw) != {"enabled"} or not isinstance(raw["enabled"], bool):
                        raise ValueError("PATCH accepts an enabled boolean")
                    handler.send({"data": self.store.save("schedules", item | raw)})
            else:
                return False
            return True
        if resource == "pull-requests" and method == "GET":
            proposals = self.service.snapshot()["remediations"]
            records = [{"id": p["id"], "campaign_id": p.get("campaign_id"), "finding_ids": [p.get("finding_id")],
                        "status": p.get("status"), "title": p.get("title"), "url": p.get("publication", {}).get("url"),
                        "state": "open" if p.get("published") else p.get("status", "proposed"),
                        "provider": p.get("publication", {}).get("provider"), "confidence": p.get("judge", {}).get("confidence"),
                        "published": bool(p.get("published")), "validation": {phase: [{k: row.get(k) for k in ("name", "kind", "passed", "exit_code", "timed_out")}
                                      for row in p.get("validation", {}).get(phase, [])] for phase in ("before", "after")}} for p in proposals]
            if len(parts) == 1:
                handler.send(envelope(filtered(records, query, ("campaign_id", "status"))))
            elif len(parts) == 2:
                record = next((r for r in records if r["id"] == identifier(parts[1])), None)
                if not record:
                    raise KeyError(parts[1])
                handler.send({"data": record})
            else:
                return False
            return True
        if parts == ["source-files"] and method == "GET":
            if identity.get("role") == "viewer":raise PermissionError("Read-only accounts cannot inspect source repositories")
            import subprocess
            from pathlib import Path
            repo = Path(query.get("repo", "")).expanduser().resolve()
            if not query.get("repo") or not repo.is_dir():raise ValueError("Choose an existing local source repository")
            try:
                result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), "ls-files", "-z"],capture_output=True,timeout=10)
            except (OSError,subprocess.TimeoutExpired):raise ValueError("Could not list tracked source files") from None
            if result.returncode:raise ValueError("Source directory is not a Git repository")
            files = result.stdout.decode("utf-8",errors="replace").split("\0")
            files = [f for f in files if f and not any(ord(c)<32 for c in f)]
            handler.send({"files":files[:5000],"truncated":len(files)>5000})
            return True
        if parts == ["options"] and method == "GET":
            from .opencode import catalog
            snapshot = self.service.snapshot()
            handler.send({"targets":snapshot["targets"], "campaigns":snapshot["campaigns"],
                          "findings":[{k:v.get(k) for k in ("id","campaign_id","title","severity")} for v in snapshot["findings"]],
                          "credentials":self.service.vault.list() if identity.get("role") != "viewer" else [],
                          "repositories":sorted({j.get("spec",{}).get("git_repo") for j in self.store.items("jobs") if j.get("spec",{}).get("git_repo")} | {p.get("repo") for p in self.store.items("remediations") if p.get("repo")} | {p for p in os.environ.get("DARKMOON_SOURCE_REPOSITORIES", "").split(os.pathsep) if p}),
                          "opencode":catalog(self.service) if admin else None})
            return True
        if parts[:2] == ["system", "opencode"]:
            if not admin:raise PermissionError("Administrator access is required")
            from . import opencode
            if method == "GET" and len(parts) == 2:
                handler.send(opencode.catalog(self.service))
            elif method == "POST" and len(parts) == 3 and parts[2] in {"sync","connect","disconnect","oauth-start","oauth-finish"}:
                raw = handler.body()
                if parts[2] == "sync":result = opencode.sync(self.service)
                elif parts[2] == "connect":result = opencode.connect(self.service,raw)
                elif parts[2] == "disconnect":result = opencode.disconnect(self.service,raw)
                else:result = opencode.oauth(self.service,raw,finish=parts[2] == "oauth-finish")
                handler.send(result)
            else:return False
            return True
        if resource == "system" and method == "GET":
            if parts[1:] == ["update-status"]:
                from .updates import status
                handler.send(status(query.get("check") == "1"))
            elif parts[1:] == ["doctor"]:
                from .integrity import doctor
                handler.send(doctor(self.service.queue.repo, self.store))
            elif parts[1:] == ["providers"]:
                if not admin:
                    raise PermissionError("Administrator access is required")
                handler.send(envelope(self.store.items("providers")))
            elif parts[1:] == ["integrity"]:
                from .integrity import verify
                handler.send(verify(self.service.queue.repo, self.store))
            elif parts[1:] == ["privacy-audit"]:
                if not admin:
                    raise PermissionError("Administrator access is required")
                from .privacy_audit import audit_summary
                handler.send(audit_summary(self.store))
            else:
                return False
            return True
        if resource == "system" and method == "POST" and parts[1:] == ["providers"]:
            if not admin:
                raise PermissionError("Administrator access is required")
            from .configuration import profile
            handler.send({"data": profile(self.service, handler.body())}, status=201)
            return True
        if resource == "system" and method == "POST" and len(parts) == 4 and parts[1] == "providers" and parts[3] == "apply":
            if not admin:
                raise PermissionError("Administrator access is required")
            handler.body()
            from .configuration import apply
            handler.send(apply(self.service, parts[2]))
            return True
        if resource == "webhooks":
            if method == "GET" and len(parts) == 1:
                handler.send(envelope(self.store.items("webhooks")))
            elif method == "POST" and len(parts) == 1:
                handler.send({"data": self.service.operations.register(handler.body())}, status=201)
            elif len(parts) == 2 and method == "DELETE":
                def remove(state):
                    hook = state.setdefault("webhooks", {}).pop(identifier(parts[1]), None)
                    if not hook:
                        raise KeyError(parts[1])
                    state.setdefault("credentials", {}).pop(hook["credential_ref"], None)
                self.store.update(remove)
                handler.send({"deleted": parts[1]})
            elif len(parts) == 3 and parts[2] == "deliveries" and method == "GET":
                handler.send(envelope([d for d in self.store.items("deliveries") if d["webhook_id"] == identifier(parts[1])]))
            else:
                return False
            return True
        if resource == "events" and parts[1:] == ["history"] and method == "GET":
            handler.send(envelope(self.store.items("events")))
            return True
        if resource == "retest":
            if method == "POST" and len(parts) == 1:
                handler.send(self.service.operations.launch_retest(handler.body()), status=201)
            elif method == "GET" and len(parts) == 1:
                handler.send(envelope(self.store.items("retests")))
            elif method == "GET" and len(parts) == 2:
                record = self.store.get("retests", identifier(parts[1]))
                if not record:
                    raise KeyError(parts[1])
                handler.send(record)
            else:
                return False
            return True
        if resource == "metrics" and parts[1:] == ["timeseries"] and method == "GET":
            handler.send(timeseries(query))
            return True
        return False
