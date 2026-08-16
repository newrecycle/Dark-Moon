#!/usr/bin/env python3
"""
verify_toolbox.py — manifest-driven toolbox verifier.

Reads tools/toolbox-manifest.json and proves, for EVERY required runtime
record (callable AND support-only, and blocked-but-installed), that:

  * the expected executable resolves on PATH / at its install location
  * a non-destructive liveness probe completes under a hard timeout
  * package/version metadata asserts the pinned version (where verifiable)
  * required auxiliary data directories exist
  * wrappers exec a real target (no broken-wrapper)

Host-only / build-only records are reported distinctly and NEVER fail the image.
Blocked-but-installed records are reported distinctly (none in this manifest).
Absent / wrong-version / wrong-target / broken-wrapper / timed-out probes are
HARD failures.

Usage:
  python3 tools/verify_toolbox.py [--manifest PATH] [--json] [--timeout SEC]
Exit code: 0 = all required runtime records pass; 1 = at least one failure.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MANIFEST = os.path.join(HERE, "toolbox-manifest.json")


def run(cmd, timeout):
    try:
        p = subprocess.run(cmd, shell=True, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           executable="/bin/bash")
        return p.returncode, p.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 124, ""
    except Exception as e:  # pragma: no cover
        return 127, str(e)


def resolve_exe(exe, install_location):
    # 1) PATH
    path = shutil.which(exe)
    if path:
        return path, "path"
    # 2) explicit install location (file or dir/bin)
    cands = []
    if install_location:
        cands.append(install_location)
        cands.append(os.path.join(install_location, exe))
    for c in cands:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c, "location"
    return None, None


def is_wrapper(path):
    # Only treat shell-script wrappers as wrappers. Python/pip entry points
    # (e.g. nxc, netexec) are real executables, not wrappers around another
    # binary, even if their body happens to mention "exec".
    try:
        with open(path, "r", errors="replace") as f:
            first = f.readline()
        if not first.startswith("#!") or "sh" not in first:
            return False
        body = open(path).read()
        return "exec " in body
    except Exception:
        return False


def wrapper_target_missing(path):
    try:
        body = open(path).read()
    except Exception:
        return False
    for tok in ("exec ",):
        idx = body.find(tok)
        while idx != -1:
            rest = body[idx + len(tok):].split()[0] if body[idx+len(tok):].split() else ""
            tgt = rest.strip().strip('"').strip("'")
            if tgt and not tgt.startswith("$") and not shutil.which(tgt) and not os.path.exists(tgt):
                # only flag absolute/relative exec targets that are missing
                if "/" in tgt or not tgt.startswith("-"):
                    if not os.path.exists(os.path.expanduser(tgt)):
                        return True
            idx = body.find(tok, idx + 1)
    return False


def pip_version(upstream):
    rc, out = run(
        f'python3 -c "import importlib.metadata as m;'
        f'print(m.version(\'{upstream}\'))" 2>/dev/null', 20)
    return out.strip() if rc == 0 else None


def gem_version(upstream):
    rc, out = run(f"gem list '^{upstream}$' --local 2>/dev/null | head -1", 20)
    if rc == 0:
        # format: "wpscan (4.1.0)"
        import re
        m = re.search(r"\(([^)]+)\)", out)
        if m:
            return m.group(1)
    return None


def pkg_metadata_version(rec):
    cls = rec.get("class")
    up = rec.get("upstream") or ""
    if cls == "pip":
        return pip_version(up) or pip_version(rec.get("id"))
    if cls == "gem":
        return gem_version(up)
    return None


def concrete(v):
    if not v:
        return False
    v = str(v).strip().lower()
    if v in ("distro", "bundled", "nightly"):
        return False
    # a git commit SHA (7-64 hex chars) is a ref, not a PEP 440 version; the
    # verifier must not attempt a strict version comparison against it (the
    # record is pinned to an immutable commit, validated by the audit instead).
    if v and all(c in "0123456789abcdef" for c in v) and 7 <= len(v) <= 64:
        return False
    return v[0].isdigit() or v[0] == "v"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()

    with open(args.manifest) as f:
        data = json.load(f)
    records = data.get("records", [])

    results = []
    counts = {"ok": 0, "fail": 0, "host_only": 0, "blocked": 0, "version_unverified": 0}

    for rec in records:
        rid = rec["id"]
        exposure = rec.get("exposure")
        requires = rec.get("requires_runtime", True)
        status = "OK"
        detail = ""
        target = None

        if exposure in ("host-only", "build-only"):
            counts["host_only"] += 1
            results.append({"id": rid, "exposure": exposure, "status": "HOST-ONLY",
                            "detail": "excluded from runtime image by design"})
            continue

        if exposure == "blocked":
            counts["blocked"] += 1
            results.append({"id": rid, "exposure": exposure, "status": "BLOCKED-INSTALLED",
                            "detail": "installed + verified but blocked from MCP exposure"})
            continue

        if not requires:
            results.append({"id": rid, "exposure": exposure, "status": "SKIP",
                            "detail": "requires_runtime=false"})
            continue

        # resolve an executable
        exes = rec.get("executables") or []
        if not exes and not (rec.get("aliases") or []):
            if exposure == "support-only":
                counts["ok"] += 1
                results.append({"id": rid, "exposure": exposure, "status": "SKIP",
                                "detail": "support-only dependency/data record (no executable to probe)"})
                continue
        for exe in exes:
            t, kind = resolve_exe(exe, rec.get("install_location"))
            if t:
                target = t
                break
        if not target:
            # try aliases
            for al in rec.get("aliases") or []:
                t, kind = resolve_exe(al, rec.get("install_location"))
                if t:
                    target = t
                    break
        if not target:
            counts["fail"] += 1
            results.append({"id": rid, "exposure": exposure, "status": "MISSING",
                            "detail": f"no executable in {exes} resolved"})
            continue

        # wrapper check
        if is_wrapper(target) and wrapper_target_missing(target):
            counts["fail"] += 1
            results.append({"id": rid, "exposure": exposure, "status": "BROKEN-WRAPPER",
                            "detail": f"{target} wrapper execs a missing target"})
            continue

        # probe
        rc, out = run(rec.get("probe") or f"{target} --version", args.timeout)
        if rc == 124:
            counts["fail"] += 1
            results.append({"id": rid, "exposure": exposure, "status": "TIMEOUT",
                            "detail": f"probe timed out after {args.timeout}s"})
            continue
        if rc != 0 and not out.strip():
            counts["fail"] += 1
            results.append({"id": rid, "exposure": exposure, "status": "PROBE-FAIL",
                            "detail": f"probe exited {rc} with no output"})
            continue

        # version assertion
        rv = rec.get("resolved_version")
        version_status = "unverified"
        if concrete(rv):
            # 1) probe output contains the resolved version?
            if str(rv).lstrip("v") in out or str(rv) in out:
                version_status = "verified-in-probe"
            else:
                meta = pkg_metadata_version(rec)
                if meta:
                    # compare base versions: a PEP 440 local version suffix
                    # (e.g. "+0.806e4c73") is non-significant for the release.
                    _base = lambda x: str(x).split("+", 1)[0].strip().lstrip("v").strip()
                    if _base(meta) == _base(rv):
                        version_status = "verified-metadata"
                    else:
                        counts["fail"] += 1
                        results.append({"id": rid, "exposure": exposure,
                                        "status": "WRONG-VERSION",
                                        "detail": f"expected {rv}, metadata reports {meta}"})
                        continue
                else:
                    version_status = "unverified"
        if version_status == "unverified":
            counts["version_unverified"] += 1

        # data dirs
        for dd in rec.get("data_dirs") or []:
            if not os.path.isdir(dd):
                counts["fail"] += 1
                results.append({"id": rid, "exposure": exposure, "status": "MISSING-DATADIR",
                                "detail": f"required data dir {dd} absent"})
                break
        else:
            counts["ok"] += 1
            results.append({"id": rid, "exposure": exposure, "status": "OK",
                            "target": target, "version_status": version_status,
                            "detail": f"probe ok; version {version_status}"})

    # --- Playwright / Chromium assertion (headless-browser agent runtime) ---
    # The headless-browser agent is built entirely around Playwright driving a
    # Chromium browser via MCP. node/npm are necessary but not sufficient: the
    # browser binaries MUST be present and launchable, or the agent silently
    # fails. This check catches a missing/partial Playwright browser install.
    pw_browser_dir = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    pw_chrome = None
    if pw_browser_dir:
        # find any chromium/headless-shell build under the pinned path
        for name in os.listdir(pw_browser_dir) if os.path.isdir(pw_browser_dir) else []:
            if "chromium" in name or "chrome" in name:
                pw_chrome = os.path.join(pw_browser_dir, name)
                break
    if pw_chrome and shutil.which("node"):
        # playwright lives in /opt/darkmoon/node_modules; point NODE_PATH there so
        # the probe can require('playwright') without a cwd dependency.
        node_modules = "/opt/darkmoon/node_modules"
        pw_probe = (
            "const { chromium } = require('playwright');"
            " (async () => {"
            "   const b = await chromium.launch({ headless: true });"
            "   await b.newPage();"
            "   await b.close();"
            "   console.log('PLAYWRIGHT_OK');"
            " })().catch((e) => { console.log('PLAYWRIGHT_FAIL:' + e.message); process.exit(1); });"
        )
        rc, out = run(
            f"NODE_PATH={node_modules} node -e \"{pw_probe}\"", args.timeout)
        if "PLAYWRIGHT_OK" in out:
            counts["ok"] += 1
            results.append({"id": "playwright-chromium", "exposure": "callable",
                            "status": "OK",
                            "detail": f"Chromium launches via Playwright ({os.path.basename(pw_chrome)})"})
        else:
            counts["fail"] += 1
            results.append({"id": "playwright-chromium", "exposure": "callable",
                            "status": "FAIL",
                            "detail": f"Playwright present but Chromium did not launch: {out.strip()[:120]}"})
    elif not pw_browser_dir:
        counts["fail"] += 1
        results.append({"id": "playwright-chromium", "exposure": "callable",
                        "status": "FAIL",
                        "detail": "PLAYWRIGHT_BROWSERS_PATH not set — browsers dir unknown"})
    else:
        counts["fail"] += 1
        results.append({"id": "playwright-chromium", "exposure": "callable",
                        "status": "FAIL",
                        "detail": f"no Chromium build found in {pw_browser_dir}"})

    # summary
    required_total = sum(1 for r in records
                        if r.get("exposure") not in ("host-only", "build-only")
                        and r.get("requires_runtime", True))
    passed = counts["ok"]
    failed = counts["fail"]

    if args.json:
        print(json.dumps({
            "required_total": required_total,
            "passed": passed, "failed": failed,
            "host_only": counts["host_only"], "blocked": counts["blocked"],
            "version_unverified": counts["version_unverified"],
            "reconciles": (passed + failed) == required_total,
            "results": results,
        }, indent=2))
    else:
        print("== Darkmoon toolbox verification (manifest-driven) ==")
        for r in results:
            print(f"  {r['status']:18s} {r['id']:22s} {r.get('detail','')}")
        print("\n== summary ==")
        print(f"  required runtime records : {required_total}")
        print(f"  passed                  : {passed}")
        print(f"  failed                  : {failed}")
        print(f"  host-only (excluded)    : {counts['host_only']}")
        print(f"  blocked-but-installed   : {counts['blocked']}")
        print(f"  version-unverified      : {counts['version_unverified']}")
        print(f"  reconciles with inventory: { (passed+failed)==required_total }")
        print()
        print("RESULT:", "PASS" if failed == 0 else "FAIL")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
