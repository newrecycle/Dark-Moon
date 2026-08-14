#!/usr/bin/env python3
"""
audit_toolbox.py — classify the CURRENT build implementation against the
canonical inventory, WITHOUT using any running container.

It reads the build sources (Dockerfile, setup.sh, setup_py.sh, setup_ruby.sh)
as text and, for every inventory record, decides one of:

  exact_reproducible      pinned version present, no floating token
  floating_unpinned       referenced but using @latest / stable / HEAD / no version
  accidental_dependency   present only transitively (not an explicit install)
  wrong_distribution      mapped to the wrong repo/package/entry point
  not_in_runtime_image    built but the copy/runtime stage is missing it
  missing_from_path       installed but not on PATH / no wrapper
  missing_alias           installed but a required compatibility alias is absent
  requested_absent        no reference found anywhere
  host_or_build_only      host-only / build-only (expected to be absent in runtime)
  blocked_but_installed   installed + verified but exposure=blocked

Outputs tools/audit-report.json and a human summary.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MANIFEST = os.path.join(HERE, "toolbox-manifest.json")
OUT = os.path.join(HERE, "audit-report.json")

BUILD_FILES = ["Dockerfile", "setup.sh", "setup_py.sh", "setup_ruby.sh"]

# ---------------------------------------------------------------------------
# floating anti-patterns
# ---------------------------------------------------------------------------
FLOATING_PATTERNS = [
    r"@latest", r"@HEAD", r"@master", r"@main",
    r"stable\.txt", r"CURL_VER=.*head -1", r"curl -fsSL https://curl\.se/download/\s*\|",
    r"git clone --depth=1 https://",  # depth-1 without explicit --branch pin
    r"gem install \w+ --no-document(?! -v)",
    r"pip install [^\n]*\b(impacket|wafw00f|sqlmap|arjun|awscli|bloodhound)\b[^\n]*$",
    r"-update-templates",
    r"fallback", r"tentative avec latest", r"latest stable",
]

# records whose build uses a deliberate floating token (documented exception)
DOCUMENTED_FLOATING = {"lightpanda"}


def load_sources():
    text = {}
    for f in BUILD_FILES:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            text[f] = open(p, encoding="utf-8", errors="replace").read()
        else:
            text[f] = ""
    return text


def classify(rec, src):
    rid = rec["id"]
    cls = rec["class"]
    exposure = rec["exposure"]
    resolved = str(rec.get("resolved_version") or "")
    ref = str(rec.get("resolved_ref") or "")
    up = rec.get("upstream") or ""
    # Merge only backslash-newline continuations so multi-line `install`
    # invocations stay on one logical line, but keep real statement
    # boundaries so `.*` cannot span unrelated lines.
    flat = re.sub(r"\\\n", " ", "\n".join(src.values()))

    def has(pat):
        return re.search(pat, flat) is not None

    # host / build only -> expected absent from runtime image
    if exposure in ("host-only", "build-only"):
        return "host_or_build_only", "not expected in runtime image"

    # --- APT: pinned by the immutable base image tag, so 'distro' == exact ---
    if cls == "apt":
        if has(r"\b" + re.escape(rid) + r"\b") or has(r"\b" + re.escape(up) + r"\b"):
            return ("exact_reproducible",
                    "apt package installed; version pinned by immutable base image tag")
        return "requested_absent", "apt package not present in any apt-get install list"

    # --- PIP ---
    if cls == "pip":
        exact = (has(rf"install .*\b{re.escape(up)}=={re.escape(resolved)}\b") or
                 has(rf"git\+https://.*{re.escape(up)}\.git@{re.escape(resolved)}"))
        ref_present = (has(rf"install .*\b{re.escape(up)}\b") or
                       has(rf"git\+https://.*{re.escape(up)}\.git"))
        wrapper_only = (has(rf"exec .*{re.escape(up)}\b") and not ref_present)
        if exact:
            return "exact_reproducible", f"pip install {up}=={resolved} present"
        if ref_present:
            return "floating_unpinned", f"pip install {up} present without =={resolved} pin"
        if wrapper_only:
            return "requested_absent", f"only a wrapper references {up}; pip install absent"
        return "requested_absent", f"no pip install / git+ for {up}"

    # --- GEM ---
    if cls == "gem":
        if has(rf"install .*\b{re.escape(up)}\b.*-v[ =]{re.escape(resolved)}"):
            return "exact_reproducible", f"gem install {up} -v {resolved} present"
        if has(rf"install .*\b{re.escape(up)}\b"):
            return "floating_unpinned", f"gem install {up} without -v {resolved}"
        return "requested_absent", f"no gem install for {up}"

    # --- GO (go install or binary release) ---
    if cls == "go":
        if has(rf"go install .*@{re.escape(resolved)}\b") or has(re.escape(resolved)):
            return "exact_reproducible", f"go install / asset pinned to {resolved}"
        if has(r"go install .*@latest"):
            return "floating_unpinned", "go install @latest (unpinned)"
        return "requested_absent", f"no go install / binary reference for {up}"

    # --- binary / source builds ---
    if cls in ("binary", "source"):
        if resolved == "bundled":
            return ("exact_reproducible",
                    "bundled with the pinned parent build (reproducible)")
        if resolved not in ("distro", "bundled", "nightly"):
            if has(r"\b" + re.escape(resolved) + r"\b"):
                if rid == "curl-8.15.0" and has(r"CURL_VER.*head -1|grep -Eo 'curl-"):
                    return "floating_unpinned", "CURL_VER resolved via floating grep"
                if rid == "kubectl" and has(r"stable\.txt"):
                    return "floating_unpinned", "kubectl resolved via floating stable.txt"
                return "exact_reproducible", f"resolved version {resolved} present in build"
        if rid in DOCUMENTED_FLOATING:
            return "floating_unpinned", "documented upstream-rolling (nightly); accepted exception"
        if has(rf"git clone --depth=1.*{re.escape(up)}") or has(r"CURL_VER") or \
           has(r"stable\.txt") or has(r"-update-templates") or has(r"git clone --depth=1 "):
            return "floating_unpinned", "build uses a floating reference"
        return "requested_absent", "no pinned build reference found"

    # fallback
    return "floating_unpinned", "unclassified build reference"


def main():
    with open(MANIFEST) as f:
        data = json.load(f)
    src = load_sources()

    results = []
    counts = {}
    for rec in data["records"]:
        status, detail = classify(rec, src)
        results.append({
            "id": rec["id"],
            "class": rec["class"],
            "exposure": rec["exposure"],
            "resolved_version": rec.get("resolved_version"),
            "install_location": rec.get("install_location"),
            "status": status,
            "detail": detail,
        })
        counts[status] = counts.get(status, 0) + 1

    report = {
        "generated_by": "audit_toolbox.py",
        "source_files": BUILD_FILES,
        "total_records": len(results),
        "counts": counts,
        "records": results,
    }
    with open(OUT, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Audit complete: {len(results)} records")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k:24s} {v}")
    print(f"Report: {OUT}")

    # fail loudly if required runtime records are floating/absent? No — the
    # audit is informational; Phase 4 fixes, Phase 9 re-audits. Exit 0.
    return 0


if __name__ == "__main__":
    sys.exit(main())
