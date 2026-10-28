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
    from .assessment_catalog import NOISE_LEVELS, SEVERITY_CAPS
    if flags["noise"] and flags["noise"] not in NOISE_LEVELS:
        raise ValueError("Noise must be stealth, low or moderate")
    if flags["severity"] and flags["severity"] not in SEVERITY_CAPS:
        raise ValueError("Choose one maximum severity cap: critical, high, medium or low")
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
    result["format"] = {"markdown": "standard", "hackerone": "h1"}.get(result["format"], result["format"])
    if result["format"] not in {"standard", "markdown", "h1", "hackerone", "bugcrowd", "custom"}:
        raise ValueError("Unsupported report format")
    for key in ("rules", "safe_harbor"):
        value = raw.get(key) or ""
        if not isinstance(value, str) or len(value) > 8000:
            raise ValueError(f"{key} must be text of at most 8000 characters")
        result[key] = value
    result["safe_harbor_applies"] = str(raw.get("safe_harbor_applies") or "")
    if result["safe_harbor_applies"] not in {"", "yes", "no"}:
        raise ValueError("Safe harbor applies must be yes or no")
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
    flags += " PROGRAM=" + json.dumps(spec["name"])
    if spec.get("targets"):
        flags += " TARGETS=" + ",".join(spec["targets"])
    if spec.get("out_of_scope"):
        flags += " OUT=" + ",".join(spec["out_of_scope"])
    if spec.get("rules"):
        flags += " RULES=" + json.dumps(spec["rules"])
    if spec.get("safe_harbor_applies"):
        flags += " SAFE_HARBOR=" + spec["safe_harbor_applies"]
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

    def enqueue(self, spec, campaign_id, key=None, schedule_id=None, actor=None):
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
                   "idempotency_key": key, "schedule_id": schedule_id, "request_actor": actor}
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
            from .auth import CredentialVault
            vault = CredentialVault(self.store)
            actor = job.get("request_actor")
            refs = (("credential_id", "source_checkout"),) if job.get("kind") == "remediation" else (
                ("credential_id", "source_checkout"),
                ("assessment_credential_id", "assessment_login"),
                ("assessment_token_id", "assessment_token"))
            source = job.get("remediation", {}) if job.get("kind") == "remediation" else job["spec"]
            for field, capability in refs:
                if source.get(field):
                    try:
                        vault.require(source[field], capability, actor=actor)
                    except KeyError:
                        raise ValueError("Queued credential is no longer authorized") from None
            if job.get("kind") == "remediation":
                argv = self._remediation_argv(job)
            else:
                from .credential_launch import prepare
                prompt = prepare(self.repo, self.store, prompt_for(job["spec"], job["campaign_id"]), job["spec"], actor=actor)
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

    def _validate_credential_refs(self, spec, state=None):
        # Use the same saved-reference rule as Service.launch, at schedule
        # definition time for compatibility requests. The normal launcher
        # still rechecks references before any execution.
        records = (state if state is not None else self.store.read()).get("credentials", {})
        for key in ("credential_id", "assessment_credential_id", "assessment_token_id"):
            if spec.get(key) and spec[key] not in records:
                raise ValueError("Saved credential reference was not found")

    def definition(self, raw):
        from .calendar_rules import normalize_rule, next_occurrence
        from .scheduler_compat import is_flat_create, normalize_create
        flat = is_flat_create(raw)
        raw = normalize_create(raw, launch_spec)
        spec = launch_spec(raw.get("spec", raw))
        if flat:
            self._validate_credential_refs(spec)
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool) or not isinstance(raw.get("one_shot", False), bool):
            raise ValueError("enabled and one_shot must be boolean")
        rule = normalize_rule(raw["rule"]) if "rule" in raw else None
        interval = rule.get("seconds", 86400) if rule else raw.get("interval_seconds", 86400)
        if not rule:
            try: interval = int(interval)
            except (ValueError, TypeError, OverflowError): raise ValueError("Interval must be an integer number of seconds") from None
        if type(interval) is not int or not 60 <= interval <= 366 * 86400:
            raise ValueError("Interval must be between 60 seconds and 366 days")
        first = next_occurrence(rule) if rule else instant(raw.get("next_run") or raw.get("run_at") or now())
        if first is None:
            raise ValueError("No supported occurrence remains for this rule")
        display_name = raw.get("display_name", spec["name"])
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 160:
            raise ValueError("Schedule display name must contain 1 to 160 characters")
        return {"spec": spec, "display_name": display_name.strip(), "enabled": enabled,
                "interval_seconds": interval, "next_run": first.isoformat(),
                "one_shot": rule["kind"] == "once" if rule else raw.get("one_shot", False) or bool(raw.get("run_at")),
                **({"rule": rule} if rule else {})}

    def create(self, raw):
        item = self.definition(raw) | {"id": "sched_" + uuid.uuid4().hex[:16], "version": 1, "created_at": now()}
        return self.store.save("schedules", item)

    def preview(self, raw, clock=None):
        from .calendar_rules import next_occurrence
        item = self.definition(raw)
        clock = clock or datetime.now(timezone.utc)
        if clock.tzinfo is None or clock.utcoffset() is None:
            raise ValueError("Preview clock must have a timezone")
        clock = clock.astimezone(timezone.utc)
        current, rows = instant(item["next_run"]), []
        from .calendar_rules import zone_for
        zone = zone_for(item.get("rule", {}).get("timezone", "UTC"))
        for _ in range(5):
            rows.append({"utc": current.isoformat(), "local": current.astimezone(zone).isoformat(), "overdue": current < clock})
            if item["one_shot"]: break
            current = next_occurrence(item["rule"], max(clock, current)) if item.get("rule") else max(clock, current) + timedelta(seconds=item["interval_seconds"])
            if current is None: break
        return {"occurrences": rows, "timezone": str(zone), "gap_policy": "skip", "missing_month_day_policy": "skip", "definition": item}

    def update(self, schedule_id, raw):
        from .calendar_rules import normalize_rule, next_occurrence
        from .scheduler_compat import is_flat_update, normalize_update
        if not isinstance(raw, dict):
            raise ValueError("Schedule body must be an object")
        flat = is_flat_update(raw)
        if (not flat and set(raw) - {"version", "enabled", "spec", "rule", "display_name"}
                or not set(raw) - {"version"}):
            raise ValueError("Edit enabled, spec, rule or display_name with the current version")
        if "enabled" in raw and not isinstance(raw["enabled"], bool):
            raise ValueError("enabled must be boolean")
        legacy_toggle = set(raw) == {"enabled"}
        if not legacy_toggle and type(raw.get("version")) is not int:
            raise ValueError("Schedule edits require the current integer version")
        # Validate nested-schema edits as before. Flat edits merge inside the
        # locked transaction *after* checking the current version.
        spec = launch_spec(raw["spec"]) if not flat and "spec" in raw else None
        rule = normalize_rule(raw["rule"]) if not flat and "rule" in raw else None
        name = raw.get("display_name") if not flat else None
        if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 160):
            raise ValueError("Schedule display name must contain 1 to 160 characters")
        def change(state):
            item = state.get("schedules", {}).get(identifier(schedule_id))
            if item is None: raise KeyError(schedule_id)
            version = item.get("version", 1)
            if not legacy_toggle and raw["version"] != version:
                raise ValueError("Schedule changed; reload its current version before saving")
            edits = normalize_update(raw, item, launch_spec) if flat else raw
            next_spec = launch_spec(edits["spec"]) if flat and "spec" in edits else spec
            next_rule = normalize_rule(edits["rule"]) if flat and "rule" in edits else rule
            next_name = edits.get("display_name") if flat else name
            if next_name is not None and (not isinstance(next_name, str) or not next_name.strip() or len(next_name) > 160):
                raise ValueError("Schedule display name must contain 1 to 160 characters")
            if flat and next_spec is not None:
                self._validate_credential_refs(next_spec, state)
            spec_changed = next_spec is not None and next_spec != item["spec"]
            rule_changed = next_rule is not None and next_rule != item.get("rule")
            if next_spec is not None: item["spec"] = next_spec
            if next_name is not None: item["display_name"] = next_name.strip()
            if rule_changed:
                first = next_occurrence(next_rule)
                if first is None: raise ValueError("No supported occurrence remains")
                item.update(rule=next_rule, next_run=first.isoformat(), one_shot=next_rule["kind"] == "once",
                            interval_seconds=next_rule.get("seconds", 86400))
            if "enabled" in edits: item["enabled"] = edits["enabled"]
            if spec_changed or rule_changed:
                item.update(last_claim_id=None, last_disposition="definition_changed", last_error=None)
                item.pop("last_job_id", None)
            item.update(version=version+1, updated_at=now())
            return item
        return self.store.update(change)

    def set_enabled(self, schedule_id, enabled):
        return self.update(schedule_id, {"enabled": enabled})

    def duplicate(self, schedule_id, raw):
        if set(raw) != {"version"} or type(raw["version"]) is not int:
            raise ValueError("Duplicate requires the current integer version")
        def copy_record(state):
            old = state.get("schedules", {}).get(identifier(schedule_id))
            if not old: raise KeyError(schedule_id)
            if old.get("version",1) != raw["version"]: raise ValueError("Schedule changed; reload before duplicating")
            item = {k: old[k] for k in ("spec", "rule", "interval_seconds", "next_run", "one_shot") if k in old}
            # Store serialization makes this a separate record; no historical
            # job links are copied, and duplicates always start paused.
            item.update(id="sched_"+uuid.uuid4().hex[:16], display_name=(old.get("display_name",old["spec"]["name"])+" (copy)")[:160],
                        enabled=False, version=1, created_at=now())
            state["schedules"][item["id"]] = item
            return item
        return self.store.update(copy_record)

    def delete(self, schedule_id):
        def remove(state):
            schedules = state.get("schedules", {})
            if identifier(schedule_id) not in schedules: raise KeyError(schedule_id)
            del schedules[schedule_id]
            return {"deleted": schedule_id}
        return self.store.update(remove)

    def history(self, schedule_id):
        if not self.store.get("schedules", identifier(schedule_id)): raise KeyError(schedule_id)
        rows = sorted((h for h in self.store.items("schedule_history") if h["schedule_id"] == schedule_id), key=lambda h: (h["claimed_at"],h["id"]), reverse=True)
        for row in rows:
            job = self.store.get("jobs", row.get("job_id", "missing"))
            if job: row["job_status"], row["campaign_id"] = job["status"], job.get("campaign_id")
        return rows

    def tick(self, clock=None):
        clock = clock or datetime.now(timezone.utc)
        if clock.tzinfo is None or clock.utcoffset() is None:
            raise ValueError("Scheduler clock must have a timezone")
        clock = clock.astimezone(timezone.utc)
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
                from .calendar_rules import next_occurrence
                next_due = next_occurrence(item["rule"], clock) if item.get("rule") else clock + timedelta(seconds=item["interval_seconds"])
                history_id = "occ_" + uuid.uuid4().hex[:24]
                rows = state.setdefault("schedule_history", {})
                rows[history_id] = {"id":history_id, "schedule_id":item["id"], "due_at":due, "claimed_at":clock.isoformat(),
                                    "disposition":"skipped_overlap" if active else "launching"}
                if active: rows[history_id]["finished_at"] = clock.isoformat()
                prior = sorted((h for h in rows.values() if h["schedule_id"] == item["id"]), key=lambda h:(h["claimed_at"],h["id"]))
                for old in prior[:-100]: rows.pop(old["id"],None)
                item.update(next_run=next_due.isoformat() if next_due else due, last_claim_id=history_id,
                            last_tick=clock.isoformat(), last_error=None,
                            last_disposition="skipped_overlap" if active else "launching")
                if next_due is None or (item.get("one_shot") and not active):
                    item["enabled"] = False
                return {"item": item, "due": due, "active": active, "history_id":history_id}
            # Recheck existence/enabled state and advance atomically, so an HTTP
            # pause/delete cannot be undone by this tick's stale snapshot.
            claimed = self.store.update(claim)
            if not claimed or claimed["active"]:
                continue
            item = claimed["item"]
            try:
                import hashlib
                key = "schedule_" + hashlib.sha256((item["id"] + claimed["due"] + str(item.get("version",1))).encode()).hexdigest()[:32]
                job = self.launch(item["spec"], key=key, schedule_id=item["id"])
                completion = {"last_job_id": job["id"], "last_disposition": "queued"}
            except Exception as exc:
                completion = {"last_error": str(exc), "last_disposition": "failed"}
            def finish(state):
                history = state.get("schedule_history", {}).get(claimed["history_id"])
                if history:
                    history.update(disposition=completion["last_disposition"], finished_at=now())
                    if completion.get("last_job_id"): history["job_id"] = completion["last_job_id"]
                    if completion.get("last_error"): history["error"] = completion["last_error"][:2000]
                current = state.get("schedules", {}).get(item["id"])
                if current and current.get("last_claim_id") == claimed["history_id"] and current.get("next_run") == item["next_run"] and current.get("last_tick") == item["last_tick"]:
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
