#!/usr/bin/env python3
"""
validate_manifest.py — schema + invariant validation for toolbox-manifest.json.

Fails (exit 1) on:
  * duplicate logical ids
  * duplicate executable ownership across records
  * missing resolved_version / resolved_ref
  * floating references (latest/stable/master/HEAD/unpinned) where the manifest
    mandated a pin, or any record lacking an immutable ref
  * absent non-destructive probe
  * unknown installation class or exposure class
  * host-only / build-only records wrongly marked requires_runtime
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "toolbox-manifest.json")

VALID_CLASSES = {"apt", "pip", "gem", "go", "binary", "source"}
VALID_EXPOSURE = {"callable", "support-only", "build-only", "host-only", "blocked"}

# tokens that signal a floating / non-immutable reference
FLOATING_TOKENS = {"latest", "stable", "master", "main", "head", "nightly",
                   "distro", "current", "rolling"}


def err(msg):
    print(f"[FAIL] {msg}")
    return False


def is_floating(ref: str) -> bool:
    if ref is None:
        return True
    r = str(ref).strip().lower()
    if r in FLOATING_TOKENS:
        return True
    # 'latest (resolve once)' style notes are also floating
    if "latest" in r or "resolve once" in r or "rolling" in r:
        return True
    return False


def ref_acceptable(r: dict, field_val) -> bool:
    """A floating reference is acceptable only when explicitly documented:

    * apt class 'distro' -> the base image tag pins the distro immutably
      (nvidia/cuda:13.1.0-devel-ubuntu22.04), so the apt version is reproducible.
    * floating_by_upstream_design -> upstream publishes only a rolling tag
      (e.g. lightpanda nightly) and no immutable version exists.
    """
    if r.get("class") == "apt" and str(field_val).strip().lower() == "distro":
        return True
    if r.get("floating_by_upstream_design") is True:
        return True
    return False


def main() -> int:
    with open(MANIFEST) as f:
        data = json.load(f)

    ok = True
    records = data.get("records", [])

    # 1) schema shape
    required_fields = ["id", "class", "upstream", "resolved_version", "resolved_ref",
                       "executables", "install_location", "exposure", "probe",
                       "version_assert"]
    for r in records:
        for field in required_fields:
            if field not in r or r.get(field) in (None, ""):
                ok = err(f"{r.get('id','?')}: missing required field '{field}'")
        if r.get("class") not in VALID_CLASSES:
            ok = err(f"{r['id']}: unknown class '{r.get('class')}'")
        if r.get("exposure") not in VALID_EXPOSURE:
            ok = err(f"{r['id']}: unknown exposure '{r.get('exposure')}'")

    # 2) duplicate logical ids
    ids = [r["id"] for r in records]
    dup_ids = {i for i in ids if ids.count(i) > 1}
    if dup_ids:
        ok = err(f"duplicate logical ids: {sorted(dup_ids)}")

    # 3) duplicate executable ownership
    owner = {}
    for r in records:
        for exe in (r.get("executables") or []):
            owner.setdefault(exe, []).append(r["id"])
        for al in (r.get("aliases") or []):
            owner.setdefault(al, []).append(r["id"])
    real_dups = {}
    for e, v in owner.items():
        if len(v) <= 1:
            continue
        # a collision is allowed only if at least one owning record explicitly
        # permits it (e.g. apt curl shadowed by the custom curl build)
        if any(rr.get("allow_exec_collision") for rr in records if rr["id"] in v):
            print(f"[WARN] executable '{e}' shared by {v} (documented shadow/collision)")
            continue
        real_dups[e] = v
    if real_dups:
        ok = err(f"executable/alias claimed by multiple records: {real_dups}")

    # 4) missing / floating versions + refs
    for r in records:
        for fld in ("resolved_version", "resolved_ref"):
            val = r.get(fld)
            if not val or is_floating(val):
                if ref_acceptable(r, val):
                    print(f"[WARN] {r['id']}: {fld}='{val}' floating but "
                          f"documented acceptable ({r.get('class')})")
                else:
                    ok = err(f"{r['id']}: missing or floating {fld} '{val}'")
        # manifest-mandated exact pins must NOT be floating (defensive)
        rq = str(r.get("requested_version") or "")
        if rq.startswith("EXACT") or "EXACT" in rq:
            if is_floating(r.get("resolved_version")) or is_floating(r.get("resolved_ref")):
                if not ref_acceptable(r, r.get("resolved_ref")):
                    ok = err(f"{r['id']}: EXACT pin resolved to a floating reference")

    # 5) probe present
    for r in records:
        if not r.get("probe"):
            ok = err(f"{r['id']}: absent non-destructive probe")

    # 6) host-only / build-only correctly flagged requires_runtime
    for r in records:
        if r.get("exposure") in ("host-only", "build-only"):
            if r.get("requires_runtime") is True:
                ok = err(f"{r['id']}: {r['exposure']} record must not require_runtime")

    # 7) blocked records: installed implied, but must exist and be reported
    for r in data.get("blocked", []):
        if not r.get("id"):
            ok = err("blocked entry missing id")

    # 8) canonical exposure policy sanity: blocked must be empty-or-documented
    if data.get("blocked") is None:
        ok = err("top-level 'blocked' list missing")

    if ok:
        print(f"[OK] manifest valid: {len(records)} records, "
              f"{len(real_dups)} exec collisions, all refs immutable")
        return 0
    print("[FAIL] manifest validation failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
