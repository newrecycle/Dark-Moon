#!/usr/bin/env python3
"""
generate_mcp_policy.py — derive the MCP command-exposure policy from the
canonical toolbox inventory (tools/toolbox-manifest.json).

Output: tools/mcp_exposure_policy.json

Policy contents:
  allow            : every callable inventory command + compatibility alias,
                     plus explicitly documented core-shell / platform exceptions.
  blocked          : installed-but-blocked commands (none in this manifest).
  do_not_install   : commands that must NOT be installed by the toolbox
                     (pre-existing binaries referenced by agents).
  legacy_baseline  : the previous hard-coded executor allow-list, kept for
                     non-destructive coverage diffing (every legacy command must
                     be covered by allow or blocked; otherwise it is added to
                     exceptions.legacy so nothing regresses).

Design rules (handoff Phase 5):
  * Do NOT expose build-only interpreters / package managers / support-only
    commands merely because they exist in the image. Those are excluded from
    `allow` (e.g. python3, ruby, pip3, bundler are support-only).
  * sqlmap is CALLABLE but FORBIDDEN-BY-DEFAULT at runtime — recorded under
    `forbidden_by_default`, not under `blocked`.
  * Every command in `allow` maps to an inventory record or a documented
    exception (verified by tools/tests/test_mcp_policy.py).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "toolbox-manifest.json")
OUT = os.path.join(HERE, "mcp_exposure_policy.json")

# Previous hard-coded executor allow-list (executor.py as found at handoff).
# Used only to guarantee we do not silently drop a previously callable tool.
LEGACY_BASELINE = {
    "naabu", "httpx", "nuclei", "ffuf", "dirb", "wafw00f", "sqlmap", "arjun",
    "finalrecon", "lightpanda", "bash", "cat", "chmod", "node", "npm", "npx",
    "vulnx", "hydra", "whatweb", "cmseek", "wpscan", "subfinder", "waybackurls",
    "katana", "dig", "nslookup", "curl", "wget", "ping", "netexec",
    "crackmapexec", "bloodhound-python", "hashcat", "Get-GPPPassword.py",
    "GetADComputers.py", "GetADUsers.py", "GetLAPSPassword.py", "GetNPUsers.py",
    "GetUserSPNs.py", "smbclient.py", "smbexec.py",
    "smbserver.py", "findDelegation.py", "addcomputer.py", "exchange.py",
    "raiseChild.py", "rdp_check.py", "registry-read.py", "regsecrets.py",
    "rpcdump.py", "rpcmap.py", "ticketConverter.py", "ticketer.py", "tstool.py",
    "owneredit.py", "ping.py", "psexec.py", "sambaPipe.py", "samedit.py",
    "samrdump.py", "sniff.py", "sniffer.py", "secretsdump.py", "snmpwalk",
    "dcomexec.py", "dpapi.py", "filetime.py", "getArch.py", "getPac.py",
    "getST.py", "getTGT.py", "goldenPac.py", "jp.py", "keylistattack.py",
    "lookupsid.py", "mimikatz.py", "minikerberos-asreproast",
    "minikerberos-ccache2kirbi", "minikerberos-ccacheedit",
    "minikerberos-ccacheroast", "minikerberos-cve202233647",
    "minikerberos-cve202233679", "minikerberos-getNTPKInit",
    "minikerberos-getS4U2proxy", "minikerberos-getS4U2self",
    "minikerberos-getTGS", "minikerberos-getTGT", "minikerberos-keylist",
    "minikerberos-kirbi2ccache", "minikerberos-pw", "mqtt_check.py",
    "mssqlclient.py", "mssqlinstance.py", "wmiexec.py", "wmipersist.py",
    "wmiquery.py", "changepasswd.py", "badsuccessor.py", "net.py", "netview.py",
    "ntfs-read.py", "ntlmrelayx.py", "kubectl", "kubeletctl", "kubescape",
    "aws", "az", "gcloud", "gsutil", "bq", "git", "psql", "mysql",
    "mysqladmin", "redis-cli", "binwalk", "unsquashfs", "sasquatch",
    "firmwalker", "nc", "john", "unshadow", "sqlite3", "strings", "arp-scan",
    "file", "jq", "grep", "awk", "sed", "zip", "unzip",
}


def main():
    with open(MANIFEST) as f:
        data = json.load(f)

    # 1) inventory-derived callable commands
    inventory_cmds = {}
    for r in data["records"]:
        if r["exposure"] != "callable":
            continue
        for e in r.get("executables", []) or []:
            inventory_cmds.setdefault(e, []).append(r["id"])
        for a in r.get("aliases", []) or []:
            inventory_cmds.setdefault(a, []).append(r["id"])

    # 2) documented exceptions
    exceptions = {
        "core_shell": data.get("core_shell_exceptions", []),
        "platform": data.get("platform_exceptions", []),
    }
    exception_cmds = {}
    for grp in exceptions.values():
        for item in grp:
            exception_cmds[item["command"]] = item.get("reason", "")

    # 3) forbidden-by-default (callable but runtime-restricted)
    forbidden = [r["id"] for r in data["records"]
                 if r.get("exposure") == "callable"
                 and (r.get("runtime_policy") == "forbidden_by_default"
                      or "forbidden_by_default" in (r.get("notes") or "").lower())]

    # 4) assemble allow set = inventory callable + exceptions
    allow = {}
    for cmd, ids in inventory_cmds.items():
        allow[cmd] = {"source": "inventory", "records": sorted(set(ids))}
    for cmd, reason in exception_cmds.items():
        if cmd not in allow:
            allow[cmd] = {"source": "exception", "reason": reason}

    # 5) non-destructive coverage: any legacy command not yet covered is kept
    #    as a legacy exception so we never regress previously callable tools.
    legacy_missing = sorted(c for c in LEGACY_BASELINE if c not in allow)
    legacy_exceptions = []
    for c in legacy_missing:
        legacy_exceptions.append({"command": c,
                                  "reason": "legacy callable tool not in manifest; retained for non-destructive compatibility"})
        allow[c] = {"source": "legacy", "reason": "retained for compatibility"}

    policy = {
        "schema_version": "1.0",
        "generated_by": "generate_mcp_policy.py",
        "source_inventory": "tools/toolbox-manifest.json",
        "allow": allow,
        "forbidden_by_default": forbidden,
        "blocked": data.get("blocked", []),
        "do_not_install": data.get("do_not_install", []),
        "exceptions": exceptions,
        "legacy_baseline_size": len(LEGACY_BASELINE),
        "legacy_retained_count": len(legacy_missing),
        "legacy_retained": legacy_exceptions,
        "counts": {
            "allow": len(allow),
            "inventory_derived": sum(1 for v in allow.values() if v["source"] == "inventory"),
            "exception_derived": sum(1 for v in allow.values() if v["source"] == "exception"),
            "legacy_retained": len(legacy_missing),
            "blocked": len(data.get("blocked", [])),
            "forbidden_by_default": len(forbidden),
        },
    }

    with open(OUT, "w") as f:
        json.dump(policy, f, indent=2)

    print(f"Wrote {OUT}")
    print(f"  allow commands         : {policy['counts']['allow']}")
    print(f"    inventory-derived    : {policy['counts']['inventory_derived']}")
    print(f"    exception-derived    : {policy['counts']['exception_derived']}")
    print(f"    legacy-retained      : {policy['counts']['legacy_retained']}")
    print(f"  blocked (installed)    : {policy['counts']['blocked']}")
    print(f"  forbidden-by-default   : {policy['counts']['forbidden_by_default']} ({forbidden})")
    if legacy_missing:
        print(f"  legacy retained        : {legacy_missing}")


if __name__ == "__main__":
    main()
