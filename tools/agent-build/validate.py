#!/usr/bin/env python3
"""
Conformance validator for Darkmoon sub-agent .md files.

Enforces the mandatory rules from docs/hldd/writing-agents.md so a new agent can
never silently drift from the fleet. Runs on generated agents (tools/agent-build/out)
by default, or on any list of files passed as arguments. Exit non-zero on any failure.

This doubles as the pre-commit / anti-regression gate for agent authoring.
"""
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CANON = os.path.join(REPO, "conf", "agents", "graphql.md")


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def canonical_banner():
    text = read(CANON)
    lines = text.split("\n")
    fences = [i for i, l in enumerate(lines) if l.startswith("=" * 40)]
    open_i = fences[0]
    close_i = next(i for i in fences if i > open_i and "confidence" in lines[i - 1])
    return "\n".join(lines[open_i:close_i + 1])


# Blocks that belong ONLY to the orchestrator (pentest.md). A secondary that
# carries them would try to dispatch its own siblings.
ORCH_ONLY = [
    "SIGNAL DETECTION MATRIX",
    "CASCADE DEPTH LIMIT",
    "REACTIVE MULTI-DISPATCH",
    "SUBAGENT SPAWN PROTOCOL",
    "PHASE 2 — SIGNAL DETECTION",
]


def validate(path, banner):
    errs = []
    text = read(path)
    name = os.path.basename(path)

    if "\r" in text:
        errs.append("contains CR (must be LF-only)")

    data = {}
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        errs.append("missing valid YAML frontmatter fences")
    else:
        try:
            data = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            errs.append(f"invalid YAML frontmatter: {exc}")
        if not isinstance(data, dict):
            errs.append("frontmatter must be an object")
            data = {}

    legacy = sorted(set(data) & {"id", "name", "primary", "secondary", "prompt_file", "mcp", "tools", "maxSteps"})
    if legacy:
        errs.append(f"legacy OpenCode fields present: {', '.join(legacy)}")
    if not isinstance(data.get("description"), str) or not data["description"].strip():
        errs.append("missing frontmatter description")
    if data.get("mode") != "subagent":
        errs.append("mode must be subagent")
    permission = data.get("permission")
    if not isinstance(permission, dict):
        errs.append("permission must be an object")
    elif list(permission)[:2] != ["*", "darkmoon_*"] or permission.get("*") != "deny" or permission.get("darkmoon_*") != "allow":
        errs.append("permissions must deny '*' then allow 'darkmoon_*'")

    if banner not in text:
        errs.append("STATUS QUALIFICATION banner not byte-identical to graphql.md")

    if "SUB-AGENT REPORTING RULE — DO NOT FINALIZE THE CAMPAIGN" not in text:
        errs.append("missing SUB-AGENT REPORTING RULE (do-not-finalize) block")
    if "YOU MUST NOT call dashboard_finalize_campaign()" not in text:
        errs.append("missing 'MUST NOT call dashboard_finalize_campaign()'")

    if "DASHBOARD REAL-TIME PUSH (MANDATORY)" not in text:
        errs.append("missing DASHBOARD REAL-TIME PUSH block")

    if "{{TARGET}}" not in text:
        errs.append("missing {{TARGET}} placeholder")

    if "END OF PROMPT" not in text and "END OF INSTRUCTIONS" not in text:
        errs.append("missing END marker")

    for bad in ORCH_ONLY:
        if bad in text:
            errs.append(f"orchestrator-only block leaked in: '{bad}'")

    return errs


def main():
    banner = canonical_banner()
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        out = os.path.join(HERE, "out")
        files = [os.path.join(out, f) for f in sorted(os.listdir(out))] if os.path.isdir(out) else []
    if not files:
        print("no files to validate")
        return 0
    failed = 0
    for f in files:
        if not f.endswith(".md"):
            continue
        errs = validate(f, banner)
        if errs:
            failed += 1
            print(f"[FAIL] {os.path.basename(f)}")
            for e in errs:
                print(f"        - {e}")
        else:
            print(f"[OK]   {os.path.basename(f)}")
    print(f"\n{'PASS' if not failed else 'FAIL'}: {failed} file(s) with problems")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
