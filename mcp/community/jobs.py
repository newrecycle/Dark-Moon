"""Persistent queue, bounded processes and interval scheduling; no shell parsing."""
import json
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .store import identifier, now

ACTIVE = {"queued", "running"}
FINISHED = {"succeeded", "failed", "cancelled", "timed_out", "interrupted"}


def instant(value):
    if not isinstance(value, str):
        raise ValueError("Time must be an ISO-8601 string with timezone")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Time must include a timezone, e.g. 2026-11-01T18:00:00Z")
    return result.astimezone(timezone.utc)


def launch_spec(raw):
    if not isinstance(raw, dict):
        raise ValueError("Expected a launch object")
    target = str(raw.get("target", "")).strip()
    if not target or len(target) > 2048 or any(c.isspace() for c in target) or any(c in target for c in '\"\'`<>\\'):
        raise ValueError("Target must be one host, IP, CIDR or URL without whitespace or quotes")
    # The prompt parser treats spaces as flag delimiters; keep user values out
    # of that grammar. Names are JSON-quoted separately in the context block.
    import re
    flags = {}
    for key in ("focus", "exclude", "severity", "noise"):
        value = raw.get(key) or ""
        if isinstance(value, list):
            value = ",".join(str(v) for v in value)
        value = str(value).strip()
        if value and not re.fullmatch(r"[A-Za-z0-9_,./:-]{1,500}", value):
            raise ValueError(f"Invalid {key}: use comma-separated tokens")
        flags[key] = value
    name = str(raw.get("name") or raw.get("program") or "Assessment")[:160].strip() or "Assessment"
    result = {"target": target, "name": name, **flags}
    for key in ("targets", "out_of_scope"):
        values = raw.get(key) or []
        if isinstance(values, str):
            values = [v.strip() for v in values.split(",") if v.strip()]
        if not isinstance(values, list) or len(values) > 100:
            raise ValueError(f"{key} must be an array of up to 100 targets")
        for value in values:
            if not isinstance(value, str) or not value or len(value) > 2048 or any(c.isspace() or c in '\"\'`<>\\' for c in value):
                raise ValueError(f"Invalid target in {key}")
        result[key] = values
    result["format"] = str(raw.get("format") or "standard")
    if result["format"] not in {"standard", "markdown", "h1", "hackerone", "bugcrowd", "custom"}:
        raise ValueError("Unsupported report format")
    for key in ("rules", "safe_harbor"):
        value = raw.get(key) or ""
        if not isinstance(value, str) or len(value) > 8000:
            raise ValueError(f"{key} must be text of at most 8000 characters")
        result[key] = value
    if raw.get("credentials") or raw.get("tokens"):
        raise ValueError("Store secrets in the credential vault and pass credential_id; raw launch secrets are unsupported")
    for key in ("remediate", "create_repo"):
        value = raw.get(key, False)
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        result[key] = value
    result["git_repo"] = str(raw.get("git_repo") or "")
    result["credential_id"] = str(raw.get("credential_id") or "")
    for key in ("assessment_credential_id", "assessment_token_id"):
        result[key] = str(raw.get(key) or "")
        if result[key]:
            identifier(result[key])
    if result["credential_id"]:
        identifier(result["credential_id"])
    return result


def prompt_for(spec, campaign_id):
    flags = " ".join(f"{k.upper()}={v}" for k, v in spec.items() if k in {"focus", "exclude", "severity", "noise", "format"} and v)
    context = json.dumps({"campaign_id": identifier(campaign_id), "campaign_name": spec["name"],
                          "additional_targets": spec.get("targets", []), "out_of_scope": spec.get("out_of_scope", []),
                          "rules": spec.get("rules", ""), "safe_harbor": spec.get("safe_harbor", "")})
    return (f"TARGET: {spec['target']} {flags}\n"
            f"Existing campaign CONTEXT: {context}\n"
            "Use this existing campaign_id for every finding and infrastructure push. "
            "The additional targets are in scope; out_of_scope assets are excluded. Respect the supplied engagement rules. "
            "Do not initialize a second campaign. Finalize this campaign with the full findings report. "
            "Remediation publishing is disabled: do not push git branches or open pull requests.")


class Queue:
    def __init__(self, store, repo, launcher=None, timeout=7200, on_finish=None):
        self.store, self.repo = store, Path(repo).resolve()
        self.launcher = launcher or [str(self.repo / "darkmoon.sh")]
        if not isinstance(self.launcher, list) or not self.launcher or not all(isinstance(x, str) for x in self.launcher):
            raise ValueError("Launcher must be a JSON array of argv strings")
        self.timeout, self.on_finish = timeout, on_finish
        self.stop_event = threading.Event()
        self.thread = None
        self.process = None
        # A process from the previous daemon must never be assumed completed or
        # re-executed (it may have left external side effects).
        def recover(state):
            for job in state.get("jobs", {}).values():
                if job["status"] == "running":
                    job.update(status="interrupted", finished_at=now(), error="Dashboard restarted; inspect the agent session before rerunning")
        self.store.update(recover)

    def enqueue(self, spec, campaign_id, key=None, schedule_id=None):
        spec = launch_spec(spec)
        if key is not None:
            identifier(key)
        def change(state):
            jobs = state.setdefault("jobs", {})
            if key:
                old = next((j for j in jobs.values() if j.get("idempotency_key") == key), None)
                if old:
                    if old["spec"] != spec:
                        raise ValueError("Idempotency key already used with a different launch")
                    return old
            if sum(j["status"] in ACTIVE for j in jobs.values()) >= 100:
                raise ValueError("Job queue is full")
            job = {"id": "job_" + uuid.uuid4().hex[:16], "campaign_id": identifier(campaign_id),
                   "spec": spec, "status": "queued", "created_at": now(),
                   "idempotency_key": key, "schedule_id": schedule_id}
            jobs[job["id"]] = job
            return job
        return self.store.update(change)

    def cancel(self, job_id):
        def change(state):
            job = state.get("jobs", {}).get(identifier(job_id))
            if not job:
                raise KeyError(job_id)
            if job["status"] in ACTIVE:
                job.update(cancel_requested=True)
                if job["status"] == "queued":
                    job.update(status="cancelled", finished_at=now())
            return job
        return self.store.update(change)

    def _patch(self, job_id, **values):
        def change(state):
            job = state["jobs"][job_id]
            job.update(values)
            return job
        return self.store.update(change)

    def start(self):
        self.thread = threading.Thread(target=self._loop, name="community-queue", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=8)

    def _loop(self):
        while not self.stop_event.is_set():
            jobs = sorted((j for j in self.store.items("jobs") if j["status"] == "queued"), key=lambda j: j["created_at"])
            if jobs:
                try:
                    self.run_one(jobs[0])
                except Exception:
                    import logging
                    logging.exception("Job failed unexpectedly; inspect its persisted state")
            else:
                self.stop_event.wait(.5)

    def run_one(self, job):
        job_id = job["id"]
        def claim(state):
            current = state["jobs"][job_id]
            if current["status"] != "queued":
                return False
            current.update(status="running", started_at=now())
            return True
        if not self.store.update(claim):
            return
        log_path = self.store.job_path(job_id)
        log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        proc = None
        status, exit_code, error = "failed", None, None
        try:
            if job.get("kind") == "remediation":
                argv = self._remediation_argv(job)
            else:
                from .credential_launch import prepare
                prompt = prepare(self.repo, self.store, prompt_for(job["spec"], job["campaign_id"]), job["spec"])
                argv = self.launcher + [prompt]
            task_env = dict(os.environ)
            task_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + task_env.get("PYTHONPATH", "")
            proc = subprocess.Popen(argv, env=task_env,
                                    cwd=self.repo, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            self.process = proc
            selector = selectors.DefaultSelector()
            selector.register(proc.stdout, selectors.EVENT_READ)
            deadline, size = time.monotonic() + self.timeout, 0
            with log_path.open("wb") as stream:
                os.chmod(log_path, 0o600)
                while True:
                    current = self.store.get("jobs", job_id)
                    if self.stop_event.is_set() or current.get("cancel_requested") or time.monotonic() >= deadline:
                        status = "interrupted" if self.stop_event.is_set() else ("cancelled" if current.get("cancel_requested") else "timed_out")
                        break
                    for key, _ in selector.select(timeout=.2):
                        chunk = os.read(key.fd, 65536)
                        if chunk:
                            if size < 8 * 1024 * 1024:
                                stream.write(chunk[:8 * 1024 * 1024 - size])
                                stream.flush()
                            size += len(chunk)
                        else:
                            selector.unregister(key.fileobj)
                    if proc.poll() is not None and not selector.get_map():
                        exit_code = proc.returncode
                        status = "succeeded" if exit_code == 0 else "failed"
                        break
                if size > 8 * 1024 * 1024:
                    stream.write(b"\n[log truncated at 8 MiB]\n")
            selector.close()
        except (OSError, ValueError) as exc:
            error = str(exc)
        finally:
            if proc:
                # Kill the process group even if the launcher already exited;
                # descendants must not outlive cancellation or its deadline.
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if proc.stdout:
                    proc.stdout.close()
            self.process = None
            result = self._patch(job_id, status=status, exit_code=exit_code, error=error, finished_at=now())
            if self.on_finish:
                self.on_finish(result)

    def _remediation_argv(self, job):
        settings = job["remediation"]
        argv = [sys.executable, "-m", "community.remediation", "--repo", settings["repo"],
                "--campaign-id", job["campaign_id"], "--finding-id", settings["finding_id"],
                "--proposal-id", job["proposal_id"], "--state-dir", str(self.store.root)]
        if settings["generate"]:
            argv.append("--generate")
            for file in settings["files"]:
                argv.extend(["--file", file])
        else:
            argv.extend(["--edits", settings["edits_path"]])
        if settings["validate"]:
            argv.append("--validate")
        if settings.get("credential_id"):
            argv.extend(["--credential-ref", settings["credential_id"]])
        return argv


class Scheduler:
    def __init__(self, store, launch):
        self.store, self.launch = store, launch
        self.stop_event = threading.Event()
        self.thread = None

    def create(self, raw):
        spec = launch_spec(raw)
        interval = int(raw.get("interval_seconds", 86400))
        if interval < 60 or interval > 366 * 86400:
            raise ValueError("Interval must be between 60 seconds and 366 days")
        next_run = instant(raw.get("next_run") or now()).isoformat()
        if not isinstance(raw.get("enabled", True), bool):
            raise ValueError("enabled must be boolean")
        item = {"id": "sched_" + uuid.uuid4().hex[:16], "spec": spec, "enabled": raw.get("enabled", True),
                "interval_seconds": interval, "next_run": next_run, "one_shot": bool(raw.get("one_shot", False)), "created_at": now()}
        return self.store.save("schedules", item)

    def set_enabled(self, schedule_id, enabled):
        def change(state):
            item = state.get("schedules", {}).get(identifier(schedule_id))
            if item is None:
                raise KeyError(schedule_id)
            item["enabled"] = enabled
            return item
        return self.store.update(change)

    def tick(self, clock=None):
        clock = clock or datetime.now(timezone.utc)
        for candidate in self.store.items("schedules"):
            if not candidate["enabled"] or instant(candidate["next_run"]) > clock:
                continue
            def claim(state):
                item = state.get("schedules", {}).get(candidate["id"])
                if not item or not item["enabled"] or instant(item["next_run"]) > clock:
                    return None
                active = any(j.get("schedule_id") == item["id"] and j["status"] in ACTIVE
                             for j in state.get("jobs", {}).values())
                due = item["next_run"]
                item.update(next_run=(clock + timedelta(seconds=item["interval_seconds"])).isoformat(),
                            last_tick=clock.isoformat(), last_error=None,
                            last_disposition="skipped_overlap" if active else "launching")
                if item.get("one_shot") and not active:
                    item["enabled"] = False
                return {"item": item, "due": due, "active": active}
            # Recheck existence/enabled state and advance atomically, so an HTTP
            # pause/delete cannot be undone by this tick's stale snapshot.
            claimed = self.store.update(claim)
            if not claimed or claimed["active"]:
                continue
            item = claimed["item"]
            try:
                import hashlib
                key = "schedule_" + hashlib.sha256((item["id"] + claimed["due"]).encode()).hexdigest()[:32]
                job = self.launch(item["spec"], key=key, schedule_id=item["id"])
                completion = {"last_job_id": job["id"], "last_disposition": "queued"}
            except Exception as exc:
                completion = {"last_error": str(exc), "last_disposition": "failed"}
            def finish(state):
                current = state.get("schedules", {}).get(item["id"])
                if current and current.get("next_run") == item["next_run"] and current.get("last_tick") == item["last_tick"]:
                    current.update(completion)
            self.store.update(finish)

    def start(self):
        def loop():
            while not self.stop_event.is_set():
                try:
                    self.tick()
                except Exception:
                    import logging
                    logging.exception("Scheduler tick failed")
                self.stop_event.wait(1)
        self.thread = threading.Thread(target=loop, name="community-scheduler", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
