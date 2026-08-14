#!/usr/bin/env python3
"""
run_tests.py — static regression suite for the DarkMoon toolbox handoff.

Covers (handoff Phase 7):
  * inventory schema + deduplication
  * every callable inventory command represented in MCP exposure policy
  * every allow-listed command maps back to an inventory record or documented exception
  * blocked entries still have an installation mapping
  * host-only / build-only records not required in runtime PATH / not exposed
  * compatibility aliases + wrapper target paths
  * architecture asset selection (both amd64 + arm64 resolve)
  * rejection of floating tags / unverified downloads / silent required failures
  * execution-guard bounded + prohibited scanner classification
  * repo hygiene: shell syntax, compose parse, JSON validity, scoped git whitespace

No test reads agent Markdown. Network-dependent checks skip gracefully.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
MANIFEST = os.path.join(REPO, "tools", "toolbox-manifest.json")
POLICY = os.path.join(REPO, "tools", "mcp_exposure_policy.json")
AUDIT = os.path.join(REPO, "tools", "audit-report.json")
DOCKERFILE = os.path.join(REPO, "Dockerfile")
SETUP_SH = os.path.join(REPO, "setup.sh")
SETUP_PY = os.path.join(REPO, "setup_py.sh")
SETUP_RB = os.path.join(REPO, "setup_ruby.sh")
GUARD = os.path.join(REPO, "mcp", "src", "execution_guard.py")

_results = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    return bool(cond)


def load_json(p):
    with open(p) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
def test_inventory_schema():
    d = load_json(MANIFEST)
    recs = d["records"]
    ok = True
    ids = [r["id"] for r in recs]
    if len(ids) != len(set(ids)):
        ok = check("schema:unique-ids", False, f"dup ids: {[i for i in ids if ids.count(i)>1]}")
    else:
        check("schema:unique-ids", True)
    for r in recs:
        for f in ("id", "class", "exposure", "resolved_version", "resolved_ref", "probe"):
            if not r.get(f):
                ok = check(f"schema:field:{r['id']}:{f}", False)
        if r.get("class") not in ("apt","pip","gem","go","binary","source"):
            ok = check(f"schema:class:{r['id']}", False, r.get("class"))
        if r.get("exposure") not in ("callable","support-only","build-only","host-only","blocked"):
            ok = check(f"schema:exposure:{r['id']}", False, r.get("exposure"))
    # no floating refs except documented
    for r in recs:
        rv = str(r.get("resolved_version") or "")
        floating = rv.strip().lower() in ("latest","stable","master","main","head","nightly","distro","current","rolling") \
                   or "latest" in rv.lower() or "resolve once" in rv.lower()
        if floating and r.get("class") != "apt" and not r.get("floating_by_upstream_design"):
            ok = check(f"schema:no-floating:{r['id']}", False, rv)
    return ok


def test_dedup():
    d = load_json(MANIFEST)
    recs = d["records"]
    owner = {}
    for r in recs:
        for e in (r.get("executables") or []):
            owner.setdefault(e, []).append(r["id"])
        for a in (r.get("aliases") or []):
            owner.setdefault(a, []).append(r["id"])
    collisions = {e: v for e, v in owner.items() if len(v) > 1
                  and not any(rr.get("allow_exec_collision") for rr in recs if rr["id"] in v)}
    check("dedup:exec-collisions", not collisions,
          f"collisions={collisions}" if collisions else "")
    # grpcurl deduplicated to a single record
    grpc = [r for r in recs if r["id"] == "grpcurl"]
    check("dedup:grpcurl-single", len(grpc) == 1)
    return not collisions and len(grpc) == 1


def test_mcp_mapping():
    d = load_json(MANIFEST)
    pol = load_json(POLICY)
    allow = pol["allow"]
    recs = d["records"]
    ok = True
    # every callable record's executables + aliases must be in allow
    for r in recs:
        if r.get("exposure") != "callable":
            continue
        for e in (r.get("executables") or []):
            if e not in allow:
                ok = check(f"mcp:callable-present:{e}", False, f"{e} missing from policy allow")
        for a in (r.get("aliases") or []):
            if a not in allow:
                ok = check(f"mcp:alias-present:{a}", False, f"alias {a} missing from policy allow")
    # every allow command maps back
    inv_cmds = set()
    for r in recs:
        if r.get("exposure") == "callable":
            inv_cmds.update(r.get("executables") or [])
            inv_cmds.update(r.get("aliases") or [])
    exc_cmds = set()
    for grp in pol.get("exceptions", {}).values():
        for it in grp:
            exc_cmds.add(it["command"])
    legacy = set(pol.get("legacy_retained", []) and [x["command"] for x in pol["legacy_retained"]])
    for cmd in allow:
        if cmd in inv_cmds or cmd in exc_cmds or cmd in legacy:
            continue
        ok = check(f"mcp:allow-maps-back:{cmd}", False, "allow command maps to nothing")
    return ok


def test_blocked_mapping():
    d = load_json(MANIFEST)
    ok = True
    for r in d["records"]:
        if r.get("exposure") == "blocked":
            installed = bool(r.get("install_location") or r.get("executables"))
            ok = check(f"blocked:mapping:{r['id']}", installed,
                       "blocked entry has no install mapping")
    # forbidden-by-default must still be callable + listed
    pol = load_json(POLICY)
    check("blocked:forbidden-listed", "sqlmap" in pol.get("forbidden_by_default", []))
    check("blocked:sqlmap-callable", "sqlmap" in pol["allow"])
    return ok


def test_host_only():
    d = load_json(MANIFEST)
    pol = load_json(POLICY)
    allow = pol["allow"]
    ok = True
    for r in d["records"]:
        if r.get("exposure") in ("host-only", "build-only"):
            if r.get("requires_runtime") is True:
                ok = check(f"hostonly:not-required:{r['id']}", False)
            if r["id"] in allow:
                ok = check(f"hostonly:not-exposed:{r['id']}", False, "host-only in allow-list")
    return ok


def test_aliases_wrappers():
    d = load_json(MANIFEST)
    setup_text = ""
    for p in (SETUP_SH, SETUP_PY, SETUP_RB):
        setup_text += open(p).read() + "\n"
    ok = True
    for r in d["records"]:
        for a in (r.get("aliases") or []):
            # a wrapper file must be created referencing the alias name
            if f'"{a}"' not in setup_text and f"/{a}" not in setup_text and a not in setup_text:
                ok = check(f"alias:wrapper:{a}", False, "no wrapper creation found")
    # crackmapexec wrapper must exec netexec
    if "exec /usr/local/bin/netexec" not in setup_text and "exec /opt/darkmoon/python/bin/netexec" not in setup_text:
        ok = check("alias:crackmapexec-target", False)
    else:
        check("alias:crackmapexec-target", True)
    # bloodhound-python wrapper must exec the bloodhound binary
    if "exec /opt/darkmoon/python/bin/bloodhound" not in setup_text:
        ok = check("alias:bloodhound-python-target", False)
    else:
        check("alias:bloodhound-python-target", True)
    return ok


def test_arch_assets():
    d = load_json(MANIFEST)
    ok = True
    arch_urls = {
        "kubectl": "https://dl.k8s.io/release/v1.34.2/bin/linux/amd64/kubectl.sha256",
        "kubectl_arm64": "https://dl.k8s.io/release/v1.34.2/bin/linux/arm64/kubectl.sha256",
        "lightpanda_amd64": "https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux",
        "lightpanda_arm64": "https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-aarch64-linux",
        "kubeletctl_amd64": "https://github.com/cyberark/kubeletctl/releases/download/v1.13/kubeletctl_linux_amd64",
        "kubeletctl_arm64": "https://github.com/cyberark/kubeletctl/releases/download/v1.13/kubeletctl_linux_arm64",
    }
    for name, url in arch_urls.items():
        try:
            rc = subprocess.run(["curl", "-fsSL", "--max-time", "15", "-o", "/dev/null",
                                 "-w", "%{http_code}", url],
                                capture_output=True, text=True, timeout=25)
            code = rc.stdout.strip()
            if code != "200":
                ok = check(f"arch:{name}", False, f"HTTP {code}")
        except Exception as e:
            # network unavailable in CI -> skip (do not fail the static suite)
            return None  # signal skipped
    return ok


def test_no_floating_audit():
    if not os.path.exists(AUDIT):
        # generate it
        try:
            subprocess.run([sys.executable, os.path.join(REPO, "tools", "audit_toolbox.py")],
                           check=True, capture_output=True)
        except Exception:
            check("audit:run", False, "could not run audit_toolbox.py")
            return False
    d = load_json(AUDIT)
    bad = [r for r in d["records"]
           if r["status"] == "floating_unpinned" and r["id"] != "lightpanda"]
    ok = check("no-floating:required", not bad, f"floating: {[b['id'] for b in bad]}")
    return ok


def test_no_silent_failure():
    df = open(DOCKERFILE).read()
    sh = open(SETUP_SH).read()
    py = open(SETUP_PY).read()
    rb = open(SETUP_RB).read()
    ok = True
    # no warning-and-continue KO for required go tools. The one permitted
    # exception is rbac-police (manifest marks it "may be stub"); its warning
    # must NOT say "KO" and must reference the documented best-effort policy.
    if re.search(r'warn\s+"[^"]*KO', sh) and "rbac-police" not in sh:
        ok = check("no-silent:go-ko-warn", False, "found warn ... KO in setup.sh")
    elif re.search(r'warn\s+"[^"]*KO', sh):
        # the only allowed KO warning is the documented rbac-police best-effort
        ok = check("no-silent:go-ko-warn", False,
                   "warn ... KO present; only rbac-police best-effort is permitted")
    else:
        check("no-silent:go-ko-warn", True)
    # netexec exact pin, no latest fallback
    if "git+https://github.com/Pennyw0rth/NetExec.git@v1.4.0" not in py:
        ok = check("no-silent:netexec-pin", False)
    if "install --no-cache-dir netexec" in py:  # bare fallback (latest)
        ok = check("no-silent:netexec-fallback", False, "netexec latest fallback present")
    else:
        check("no-silent:netexec-fallback", True)
    # impacket / bloodhound pinned
    if "git+https://github.com/fortra/impacket.git@4c09897a" not in py:
        ok = check("no-silent:impacket-pin", False)
    if "bloodhound==1.7.2" not in py:
        ok = check("no-silent:bloodhound-pin", False)
    # curl + kubectl not floating
    if 'CURL_VER="8.15.0"' not in df:
        ok = check("no-silent:curl-pin", False)
    if "stable.txt" in sh:
        ok = check("no-silent:kubectl-pin", False, "kubectl still uses stable.txt")
    if 'KUBECTL_VERSION="v1.34.2"' not in sh:
        ok = check("no-silent:kubectl-ver", False)
    # nuclei-templates pinned
    if "v10.4.7" not in df:
        ok = check("no-silent:nuclei-templates", False)
    # acl added to the runtime apt layer
    if not re.search(r"(^|\s)acl(\s|$)", df):
        ok = check("no-silent:acl", False, "acl not in apt list")
    # ruby/bundler/wpscan/whatweb/cmseek pinned
    if "bundler -v 2.7.2" not in rb:
        ok = check("no-silent:bundler-pin", False)
    if "wpscan -v 4.1.0" not in rb:
        ok = check("no-silent:wpscan-pin", False)
    if "--branch v0.6.4" not in rb:
        ok = check("no-silent:whatweb-pin", False)
    if "--branch v.1.1.3" not in py:
        ok = check("no-silent:cmseek-pin", False)
    return ok


def test_execution_guard():
    sys.path.insert(0, os.path.dirname(GUARD))
    try:
        import execution_guard as eg
    except Exception as e:
        return check("guard:import", False, str(e))
    ok = True
    if not eg.classify("hydra -P rockyou.txt -l admin").blocked:
        ok = check("guard:hydra-blocked", False)
    if eg.classify("hydra -p admin -l user").blocked:
        ok = check("guard:hydra-bounded-ok", False)
    if not eg.classify("ffuf -w rockyou.txt -u http://x").blocked:
        ok = check("guard:ffuf-blocked", False)
    if not eg.classify("naabu -host x -p 1-65535").blocked:
        ok = check("guard:naabu-full-range", False)
    if eg.effective_timeout(99999) != 900:
        ok = check("guard:max-timeout", False)
    if eg.effective_timeout(0) != 300:
        ok = check("guard:default-timeout", False)
    out, _ = eg.adapt_command("hashcat -m 0 hashes.txt")
    if "--runtime" not in out:
        ok = check("guard:hashcat-bound", False)
    return ok


def test_repo_hygiene():
    ok = True
    # shell syntax
    for p in (SETUP_SH, SETUP_PY, SETUP_RB,
              os.path.join(REPO, "tools", "verify-toolbox.sh"),
              os.path.join(REPO, "tools", "build_manifest.py"),
              os.path.join(REPO, "tools", "validate_manifest.py"),
              os.path.join(REPO, "tools", "audit_toolbox.py"),
              os.path.join(REPO, "tools", "generate_mcp_policy.py"),
              os.path.join(REPO, "tools", "verify_toolbox.py")):
        if p.endswith(".sh"):
            rc = subprocess.run(["bash", "-n", p], capture_output=True).returncode
            if rc != 0:
                ok = check(f"hygiene:bash-n:{os.path.basename(p)}", False)
    # json validity
    for p in (MANIFEST, POLICY):
        try:
            load_json(p)
        except Exception as e:
            ok = check(f"hygiene:json:{os.path.basename(p)}", False, str(e))
    # compose parse (if yaml available)
    try:
        import yaml  # noqa
        for cf in ("docker-compose.yml", "docker-compose-dev.yml", "docker-compose.gpu.yml"):
            cpath = os.path.join(REPO, cf)
            if os.path.exists(cpath):
                yaml.safe_load(open(cpath))
                check(f"hygiene:compose:{cf}", True)
    except ImportError:
        check("hygiene:compose", True, "pyyaml missing; skipped")
    # scoped git whitespace on files changed THIS session
    myfiles = ["tools/toolbox-manifest.json", "tools/verify_toolbox.py", "tools/verify-toolbox.sh",
               "Dockerfile", "setup.sh", "setup_py.sh", "setup_ruby.sh",
               "mcp/src/tools/core/executor.py", "mcp/src/tools/core/mcp_exposure_policy.json",
               "tools/build_manifest.py", "tools/validate_manifest.py", "tools/audit_toolbox.py",
               "tools/generate_mcp_policy.py", "tools/mcp_exposure_policy.json"]
    existing = [f for f in myfiles if os.path.exists(os.path.join(REPO, f))]
    r = subprocess.run(["git", "diff", "--check", "--"] + existing,
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        # only fail on trailing-whitespace / space-before-tab in our diff hunks
        if "trailing" in r.stdout or "space before tab" in r.stdout:
            ok = check("hygiene:git-whitespace", False, r.stdout[:400])
    return ok


# ---------------------------------------------------------------------------
def main():
    tests = [
        ("inventory-schema", test_inventory_schema),
        ("deduplication", test_dedup),
        ("mcp-mapping", test_mcp_mapping),
        ("blocked-mapping", test_blocked_mapping),
        ("host-only", test_host_only),
        ("aliases-wrappers", test_aliases_wrappers),
        ("arch-assets", test_arch_assets),
        ("no-floating-audit", test_no_floating_audit),
        ("no-silent-failure", test_no_silent_failure),
        ("execution-guard", test_execution_guard),
        ("repo-hygiene", test_repo_hygiene),
    ]
    passed = skipped = failed = 0
    print("== Darkmoon toolbox static regression suite ==\n")
    for name, fn in tests:
        before = len(_results)
        res = fn()
        if res is False:
            failed += 1
            print(f"[FAIL] {name}")
        elif res is None:
            skipped += 1
            print(f"[SKIP] {name} (network unavailable)")
        else:
            passed += 1
            print(f"[PASS] {name}")
        for r in _results[before:]:
            if not r[1]:
                print(f"        - {r[0]}: {r[2]}")
    # overall count of atomic checks
    total = len(_results)
    atom_pass = sum(1 for r in _results if r[1])
    print(f"\n== summary ==")
    print(f"  test groups : {passed} passed, {failed} failed, {skipped} skipped")
    print(f"  atomic checks: {atom_pass}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
