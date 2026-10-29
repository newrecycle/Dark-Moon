"""Operator-reviewed paths referencing recorded connections and finding evidence.

These records are annotations, not independently verified exploit chains. Every
read rechecks references and evidence fingerprints; stale records remain visible
but cannot be played as current evidence-backed paths.
"""
import hashlib
import json
import copy
import uuid

from .store import identifier, now

SUPPORTED_STATUSES = {"confirmed", "exploited", "remediated", "resolved"}
MAX_REVISIONS = 100
MAX_REVIEW_BYTES = 8 * 1024 * 1024


class PathConflictError(ValueError):
    """The reviewed path changed after the editor loaded it."""


def has_content(value):
    if isinstance(value, dict):
        return any(has_content(v) for v in value.values())
    if isinstance(value, list):
        return any(has_content(v) for v in value)
    return bool(value.strip()) if isinstance(value, str) else value is not None


def evidence_digest(finding):
    evidence = {k: finding[k] for k in ("evidence", "evidence_output", "evidence_commands")
                if finding.get(k) not in (None, "", [], {})}
    if not has_content(evidence):
        raise ValueError("Supporting finding has no recorded evidence")
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def validate_steps(graph, steps, recorded=False):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 32:
        raise ValueError("A path requires 1 to 32 ordered steps")
    edges = {e["id"]: e for e in graph["edges"]}
    findings = {f.get("id"): f for f in graph["findings"]}
    nodes = {n.get("id") for n in graph["nodes"]}
    previous, seen, result = None, set(), []
    for number, step in enumerate(steps, 1):
        prefix = f"Step {number}: "
        if not isinstance(step, dict) or set(step) - {
            "edge_id", "finding_id", "rationale", *( {"evidence_sha256"} if recorded else set())
        }:
            raise ValueError(prefix + "unsupported step fields")
        edge = edges.get(step.get("edge_id"))
        if not edge or edge["kind"] != "observed" or edge["source"] == edge["target"] or edge["source"] not in nodes or edge["target"] not in nodes:
            raise ValueError(prefix + "select an existing recorded connection; containment is not an attack step")
        if edge["id"] in seen or (previous is not None and edge["source"] != previous):
            raise ValueError(prefix + "connections must be contiguous, directed and not repeated")
        finding = findings.get(step.get("finding_id"))
        if not finding or finding.get("campaign_id") != graph["campaign_id"] or finding.get("status") not in SUPPORTED_STATUSES:
            raise ValueError(prefix + "select a confirmed or historically confirmed finding in this campaign")
        if not {finding.get("node_id"), finding.get("infra_node_id")} & {edge["source"], edge["target"]}:
            raise ValueError(prefix + "finding must be linked to one of this connection's assets")
        rationale = step.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 4000:
            raise ValueError(prefix + "explain how the recorded evidence supports this connection (up to 4000 characters)")
        digest = evidence_digest(finding)
        if recorded and step.get("evidence_sha256") != digest:
            raise ValueError(prefix + "supporting evidence changed; record a new review")
        result.append({"edge_id": edge["id"], "finding_id": finding["id"],
                       "rationale": rationale.strip(), "evidence_sha256": digest})
        seen.add(edge["id"])
        previous = edge["target"]
    return result


def list_paths(store, campaign_id, graph):
    records = [p for p in store.items("attack_paths") if p.get("campaign_id") == campaign_id]
    result = []
    for path in sorted(records, key=lambda p: (p["created_at"], p["id"])):
        try:
            validate_steps(graph, path["steps"], recorded=True)
            issues = []
        except ValueError as exc:
            issues = [str(exc)]
        result.append(path | {"version": path.get("version", 1), "valid": not issues, "issues": issues})
    return result


def reviewed_input(raw, *, editing=False):
    fields = {"title", "steps", "reviewed"} | ({"version"} if editing else set())
    if not isinstance(raw, dict) or set(raw) != fields or raw.get("reviewed") is not True:
        raise ValueError("Provide title, steps and explicit reviewed: true")
    title = raw["title"]
    if not isinstance(title, str) or not title.strip() or len(title) > 160:
        raise ValueError("Path title must contain 1 to 160 characters")
    if editing and (type(raw["version"]) is not int or raw["version"] < 1):
        raise ValueError("Provide the current positive integer version")
    return title.strip()


def revision(path):
    # Revisions never copy arbitrary extension fields or finding evidence bodies.
    return copy.deepcopy({key: path[key] for key in (
        "id", "campaign_id", "title", "steps", "created_at", "recorded_by", "basis",
        "version", "updated_at", "reviewed_by") if key in path}) | {"version": path.get("version", 1)}


def keep_revision(state, path):
    key = path["id"] + "." + str(path.get("version", 1))
    revisions = state.setdefault("attack_path_revisions", {})
    value = revision(path)
    if key in revisions and revisions[key] != value:
        raise ValueError("Recorded path revision conflicts with retained history")
    if key not in revisions:
        def size(row):
            return len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        retained = sum(size(row) for row in revisions.values() if row.get("campaign_id") == path["campaign_id"])
        if retained + size(value) > MAX_REVIEW_BYTES:
            raise ValueError("Campaign path reviews exceed the 8 MiB review payload budget; no history was removed")
    revisions.setdefault(key, value)


def create_path(service, campaign_id, raw, identity):
    campaign_id = identifier(campaign_id)
    title = reviewed_input(raw)
    steps = validate_steps(service.graph(campaign_id), raw["steps"])
    path = {"id": "path_" + uuid.uuid4().hex, "campaign_id": campaign_id, "title": title.strip(),
            "steps": steps, "created_at": now(), "recorded_by": identity["id"],
            "basis": "operator_review_of_recorded_evidence", "version": 1}
    def save(state):
        paths = state.setdefault("attack_paths", {})
        if sum(p.get("campaign_id") == campaign_id for p in paths.values()) >= 100:
            raise ValueError("A campaign supports at most 100 recorded paths")
        paths[path["id"]] = path
        keep_revision(state, path)
        return path
    return service.store.update(save) | {"valid": True, "issues": []}


def update_path(service, campaign_id, path_id, raw, identity):
    campaign_id, path_id = identifier(campaign_id), identifier(path_id)
    title = reviewed_input(raw, editing=True)
    steps = validate_steps(service.graph(campaign_id), raw["steps"])
    def save(state):
        path = state.setdefault("attack_paths", {}).get(path_id)
        if not path or path.get("campaign_id") != campaign_id:
            raise KeyError(path_id)
        current = path.get("version", 1)
        if raw["version"] != current:
            raise PathConflictError("Path changed; reload its current version before saving")
        if current >= MAX_REVISIONS:
            raise ValueError("A path supports at most 100 immutable revisions; record a new path")
        # Legacy records become revision 1 without rewriting their review identity.
        keep_revision(state, path)
        updated = path | {"title": title, "steps": steps, "version": current + 1,
                          "updated_at": now(), "reviewed_by": identity["id"]}
        keep_revision(state, updated)
        state["attack_paths"][path_id] = updated
        return updated
    return service.store.update(save) | {"valid": True, "issues": []}


def path_history(service, campaign_id, path_id):
    campaign_id, path_id = identifier(campaign_id), identifier(path_id)
    # A single store snapshot keeps current-version and history metadata coherent.
    state = service.store.inspect(lambda state: {key: dict(state.get(key, {})) for key in ("attack_paths", "attack_path_revisions")})
    path = state.get("attack_paths", {}).get(path_id)
    if path and path.get("campaign_id") != campaign_id:
        raise KeyError(path_id)
    rows = [revision(row) for row in state.get("attack_path_revisions", {}).values()
            if row.get("id") == path_id and row.get("campaign_id") == campaign_id]
    if path and not any(row["version"] == path.get("version", 1) for row in rows):
        rows.append(revision(path))
    if not rows:
        raise KeyError(path_id)
    rows.sort(key=lambda row: row["version"])
    return {"data": rows, "total": len(rows), "current_version": path.get("version", 1) if path else None,
            "deleted": path is None, "basis": "operator_review_of_recorded_evidence"}


def delete_path(service, campaign_id, path_id):
    campaign_id, path_id = identifier(campaign_id), identifier(path_id)
    def remove(state):
        paths = state.setdefault("attack_paths", {})
        if paths.get(path_id, {}).get("campaign_id") != campaign_id:
            raise KeyError(path_id)
        keep_revision(state, paths[path_id])
        del paths[path_id]
        return {"deleted": path_id}
    return service.store.update(remove)
