"""Application layer shared by HTTP, scheduler, and tests."""
import copy
import hashlib
import json
import os
import secrets
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from api import json_storage as data
from api.live_push import init_live_campaign
from .jobs import Queue, Scheduler, launch_spec
from .store import Store, identifier, now

SEVERITIES = ("critical", "high", "medium", "low", "info")


def graph_for(campaign_id):
    nodes = data.load_infrastructure(identifier(campaign_id))
    edges, seen = [], set()
    ids = {n.get("id") for n in nodes}
    for node in nodes:
        parent = node.get("parent_node_id") or node.get("parent_id")
        if parent in ids and (parent, node.get("id")) not in seen:
            seen.add((parent, node.get("id")))
            edges.append({"source": parent, "target": node["id"], "kind": "contains"})
        for connection in node.get("connections", []) or []:
            other = connection.get("target") if isinstance(connection, dict) else connection
            if isinstance(other, str) and other in ids and (node.get("id"), other) not in seen:
                seen.add((node.get("id"), other))
                edges.append({"source": node["id"], "target": other, "kind": "observed"})
    return {"nodes": nodes, "edges": edges, "findings": data.load_vulnerabilities(campaign_id)}


class Service:
    def __init__(self, repo, root=None, launcher=None, timeout=7200):
        self.store = Store(root)
        self.launch_lock = threading.Lock()
        self.queue = Queue(self.store, repo, launcher, timeout, self._finished)
        self.scheduler = Scheduler(self.store, self.launch)
        self.token = self._token()
        from .auth import Accounts, CredentialVault
        from .operations import Operations
        from .api import API
        self.accounts = Accounts(self.store)
        self.vault = CredentialVault(self.store)
        self.operations = Operations(self)
        self.api = API(self)
        for job in self.store.items("jobs"):
            if job["status"] == "interrupted":
                self._finished(job)

    def _token(self):
        supplied = os.environ.get("DARKMOON_DASHBOARD_TOKEN", "")
        if supplied:
            if len(supplied) < 24:
                raise ValueError("DARKMOON_DASHBOARD_TOKEN must contain at least 24 characters")
            return supplied
        path = self.store.root / "access-token"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            token = path.read_text().strip()
            if len(token) < 24:
                raise ValueError(f"Invalid token file: {path}")
            os.chmod(path, 0o600)
            return token
        token = secrets.token_urlsafe(32)
        with os.fdopen(fd, "w") as stream:
            stream.write(token + "\n")
        return token

    def authenticated(self, value):
        return self.identity(value) is not None

    def identity(self, value):
        if secrets.compare_digest(str(value or ""), "Bearer " + self.token):
            return {"id": "workspace-owner", "username": "Workspace owner", "role": "admin", "authentication": "workspace-token"}
        if str(value or "").startswith("Bearer "):
            return self.accounts.identity(value[7:])
        return None

    def start(self):
        self.queue.start()
        self.scheduler.start()
        self.operations.start()

    def close(self):
        self.operations.close()
        self.scheduler.close()
        self.queue.close()

    def launch(self, raw, key=None, schedule_id=None):
        spec = launch_spec(raw)
        if spec.get("remediate") and not spec.get("git_repo") and not spec.get("create_repo"):
            raise ValueError("Automatic remediation needs a source repository or an explicit request to create a proposal repository")
        for field in ("credential_id", "assessment_credential_id", "assessment_token_id"):
            if spec.get(field) and not self.store.get("credentials", spec[field]):
                raise ValueError("Saved credential reference was not found")
        allowed = [x.strip() for x in os.environ.get("DARKMOON_TARGET_ALLOWLIST", "").split(",") if x.strip()]
        if allowed:
            import fnmatch
            targets = [spec["target"], *spec.get("targets", [])]
            for value in targets:
                if "/" in value and "://" not in value:
                    import ipaddress
                    try:
                        requested = ipaddress.ip_network(value, strict=False)
                    except ValueError:
                        requested = None
                    if requested:
                        networks = []
                        for pattern in allowed:
                            try:
                                networks.append(ipaddress.ip_network(pattern, strict=False))
                            except ValueError:
                                pass
                        if "*" not in allowed and not any(n.version == requested.version and requested.subnet_of(n) for n in networks):
                            raise PermissionError("Requested network is outside the configured network allowlist")
                        continue
                host = urlsplit(value if "://" in value else "//"+value).hostname or value
                if not any(fnmatch.fnmatchcase(host, pattern) for pattern in allowed):
                    raise PermissionError("Target is outside the configured allowlist")
        from .integrity import verify
        if os.environ.get("DARKMOON_GUARD_ENFORCE") == "1" and not verify(self.queue.repo, self.store)["ok"]:
            raise PermissionError("Integrity guard is locked; inspect and explicitly reseal the reviewed installation")
        if key is not None:
            identifier(key)
        with self.launch_lock:
            if key:
                old = next((j for j in self.store.items("jobs") if j.get("idempotency_key") == key), None)
                if old:
                    if old["spec"] != spec:
                        raise ValueError("Idempotency key already used with a different launch")
                    return old
            host = urlsplit(spec["target"] if "://" in spec["target"] else "//" + spec["target"]).hostname or spec["target"]
            initialized = init_live_campaign("web_" + uuid.uuid4().hex[:16], host, "", project_name=spec["name"])
            campaign = data.load_campaign(initialized["campaign_id"])
            campaign["name"] = spec["name"]
            campaign["report_format"] = spec["format"]
            campaign["scope"] = {k: spec[k] for k in ("targets", "out_of_scope", "rules", "safe_harbor")}
            data.save_campaign(campaign)
            try:
                return self.queue.enqueue(spec, initialized["campaign_id"], key, schedule_id)
            except Exception:
                campaign = data.load_campaign(initialized["campaign_id"])
                campaign.update(status="failed", launch_error="Could not enqueue launcher")
                data.save_campaign(campaign)
                raise

    def _finished(self, job):
        if job.get("kind") == "remediation":
            path = self.store.root / "remediation" / identifier(job["proposal_id"]) / "result.json"
            result = data._read_json(path)
            if isinstance(result, dict) and result.get("status") in {"queued", "running"}:
                result.update(status=job["status"] if job["status"] != "succeeded" else "failed",
                              error=job.get("error") or "Remediation process stopped before saving its result; inspect the job log",
                              finished_at=job["finished_at"])
                data._write_json(path, result)
            return
        campaign = data.load_campaign(job["campaign_id"])
        if campaign and campaign.get("status") == "running":
            campaign.update(status={"succeeded": "awaiting_review", "failed": "failed", "timed_out": "timed_out",
                                    "interrupted": "interrupted", "cancelled": "aborted"}.get(job["status"], "failed"),
                            launcher_status=job["status"], launcher_finished_at=job["finished_at"])
            data.save_campaign(campaign)
        if campaign and campaign.get("status") == "completed" and job.get("spec", {}).get("remediate"):
            from .remediation import select_sources, git
            source = job["spec"].get("git_repo")
            if not source and job["spec"].get("create_repo"):
                source = self.store.root / "proposal-repositories" / identifier(campaign["id"])
                source.mkdir(parents=True, exist_ok=True, mode=0o700)
                git(source, "init")
                (source/"README.md").write_text("# Remediation engagement\n\nSource code is needed to generate and validate application fixes.\n\n"+campaign["id"]+"\n")
                self.store.save("automation_errors", {"id": "source_"+uuid.uuid4().hex[:16], "campaign_id": campaign["id"],
                    "status": "source_required", "repo": str(source), "message": "Local proposal repository created; application source is required for code-level remediation"})
                return
            try:
                from .source_checkout import checkout
                source = checkout(self, source, campaign["id"], job["spec"].get("credential_id", ""))
            except Exception as exc:
                self.store.save("automation_errors", {"id": "checkout_"+uuid.uuid4().hex[:16], "campaign_id": campaign["id"],
                                "message": str(exc)[:1000], "created_at": now()})
                return
            for finding in data.load_vulnerabilities(campaign["id"]):
                if finding.get("status") not in {"confirmed", "exploited"}:
                    continue
                if any(p.get("campaign_id") == campaign["id"] and p.get("finding_id") == finding.get("id") for p in self.snapshot()["remediations"]):
                    continue
                try:
                    files = select_sources(source, finding)
                    self.prepare_remediation({"repo": source, "campaign_id": campaign["id"], "finding_id": finding["id"],
                                              "generate": True, "files": files, "validate": (Path(source)/".darkmoon/repro.json").is_file(),
                                              "credential_id": job["spec"].get("credential_id", "")})
                except Exception as exc:
                    self.store.save("automation_errors", {"id": "error_"+uuid.uuid4().hex[:16], "campaign_id": campaign["id"],
                                    "finding_id": finding["id"], "message": str(exc)[:1000], "created_at": now()})

    def prepare_remediation(self, raw):
        from .remediation import source_file
        campaign_id, finding_id = identifier(raw.get("campaign_id")), identifier(raw.get("finding_id"))
        finding = next((f for f in data.load_vulnerabilities(campaign_id) if f.get("id") == finding_id), None)
        if not finding:
            raise KeyError(finding_id)
        if finding.get("status") not in {"confirmed", "exploited"}:
            raise ValueError("Select a confirmed or exploited finding")
        repo = Path(str(raw.get("repo", ""))).expanduser().resolve()
        if not str(raw.get("repo", "")).strip() or not repo.is_dir():
            raise ValueError("Source repository must be an existing directory on the dashboard host")
        generate, validate = raw.get("generate", False), raw.get("validate", False)
        if not isinstance(generate, bool) or not isinstance(validate, bool):
            raise ValueError("generate and validate must be boolean")
        files = raw.get("files", [])
        if not isinstance(files, list) or not all(isinstance(f, str) for f in files) or len(files) > 8:
            raise ValueError("files must be an array of up to 8 relative source paths")
        if generate and not files:
            raise ValueError("Model generation requires relevant source files")
        for file in files:
            source_file(repo, file)
        if not generate and not isinstance(raw.get("edits"), list):
            raise ValueError("Supply structured edits or enable model generation")
        credential_id = raw.get("credential_id") or ""
        if credential_id and not self.store.get("credentials", identifier(credential_id)):
            raise ValueError("Credential reference not found")
        proposal_id = "rem_" + uuid.uuid4().hex[:16]
        directory = self.store.root / "remediation" / proposal_id
        directory.mkdir(parents=True, mode=0o700)
        data._write_json(directory / "edits.json", raw.get("edits", []))
        job = {"id": "job_" + uuid.uuid4().hex[:16], "kind": "remediation", "campaign_id": campaign_id,
               "proposal_id": proposal_id, "created_at": now(), "status": "queued",
               "spec": {"name": "Fix: " + str(finding.get("title", finding_id)), "target": str(repo)},
               "remediation": {"repo": str(repo), "finding_id": finding_id, "files": files,
                               "generate": generate, "validate": validate, "credential_id": credential_id,
                               "edits_path": str(directory / "edits.json")}}
        data._write_json(directory / "result.json", {"id": proposal_id, "job_id": job["id"], "campaign_id": campaign_id,
            "finding_id": finding_id, "title": finding.get("title", finding_id), "created_at": now(), "status": "queued", "published": False})
        def enqueue(state):
            jobs = state.setdefault("jobs", {})
            if sum(j["status"] in {"queued", "running"} for j in jobs.values()) >= 100:
                raise ValueError("Job queue is full")
            jobs[job["id"]] = job
            return job
        return self.store.update(enqueue)

    def campaign(self, campaign_id):
        campaign = data.load_campaign(identifier(campaign_id))
        if not campaign:
            raise KeyError(campaign_id)
        result = dict(campaign)
        result["findings"] = data.load_vulnerabilities(campaign_id)
        result["infrastructure"] = data.load_infrastructure(campaign_id)
        result["target"] = data.load_target(campaign.get("target_id", ""))
        result["stats"] = {s: sum(str(v.get("severity", "info")).lower() == s for v in result["findings"]) for s in SEVERITIES}
        result["stats"]["total_findings"] = len(result["findings"])
        return result

    def snapshot(self):
        findings = data.load_all_vulnerabilities()
        remediation_dir = self.store.root / "remediation"
        remediations = []
        for path in sorted(remediation_dir.glob("*/result.json")):
            item = data._read_json(path)
            if isinstance(item, dict):
                remediations.append(item)
        return {"projects": data.load_projects(), "targets": data.load_targets(), "campaigns": data.load_campaigns(),
                "findings": findings, "stats": {s: sum(str(f.get("severity", "info")).lower() == s for f in findings) for s in SEVERITIES},
                "jobs": self.store.items("jobs"), "schedules": self.store.items("schedules"), "remediations": remediations}

    def change_finding(self, campaign_id, finding_id, raw):
        identifier(campaign_id)
        identifier(finding_id)
        status = raw.get("status")
        if status not in {"unconfirmed", "confirmed", "exploited", "false_positive", "accepted_risk", "remediated", "resolved"}:
            raise ValueError("Invalid triage status")
        # Operator triage is distinct from exploit/retest evidence.
        path = data.VULNERABILITIES_DIR / f"{campaign_id}.json"
        with data._file_lock(path):
            findings = data.load_vulnerabilities(campaign_id)
            finding = next((f for f in findings if f.get("id") == finding_id), None)
            if not finding:
                raise KeyError(finding_id)
            finding.update(status=status, triaged_at=now(), triage_source="operator")
            data.save_vulnerabilities(campaign_id, findings)
            return finding

    def metadata(self):
        # Explicit allowlist: never forward hosts, titles, endpoints, evidence,
        # descriptions, commands, raw output or remediation source.
        return [{k: f.get(k) for k in ("id", "campaign_id", "severity", "status", "category", "mitre_attack_id", "iso27001_control")}
                for f in data.load_all_vulnerabilities()]

    def metrics(self):
        snapshot = self.snapshot()
        lines = ["# HELP darkmoon_findings Number of findings by severity.", "# TYPE darkmoon_findings gauge"]
        for severity in SEVERITIES:
            lines.append(f'darkmoon_findings{{severity="{severity}"}} {snapshot["stats"][severity]}')
        lines.extend(["# TYPE darkmoon_campaigns gauge", f'darkmoon_campaigns {len(snapshot["campaigns"])}',
                      "# TYPE darkmoon_jobs_active gauge", f'darkmoon_jobs_active {sum(j["status"] in {"queued", "running"} for j in snapshot["jobs"])}'])
        return "\n".join(lines) + "\n"
