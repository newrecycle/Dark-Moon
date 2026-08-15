#!/usr/bin/env python3
"""
lint_agents.py — structural lint for the 50 default Darkmoon agent definitions.

Validates, per agent in conf/agents/*.md:
  * front matter (--- / id / name / description) and id == filename stem
  * required spine sections (the canonical generator spine)
  * every dashboard_* tool reference resolves to a real MCP tool
    (init_campaign, push_finding, push_infra_node, finalize_campaign)
    using the configured server prefix ("darkmoon", from mcp/opencode.json)

Purely static: no agent Markdown is executed. Exit code 0 = clean, 1 = issues.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
AGENTS_DIR = os.path.join(REPO, "conf", "agents")

# Configured MCP server key -> the prefix OpenCode prepends to tool names.
SERVER_NAME = "darkmoon"

# Canonical dashboard tool base names (mcp/src/server.py @mcp.tool defs).
DASHBOARD_BASES = {
    "dashboard_init_campaign",
    "dashboard_push_finding",
    "dashboard_push_infra_node",
    "dashboard_finalize_campaign",
}

# (label, substring) markers that must appear in every well-formed agent.
REQUIRED_SECTIONS = [
    ("front-matter", "id:"),  # front matter is also parsed explicitly below
    ("STATUS QUALIFICATION", "STATUS QUALIFICATION"),
    ("SUB-AGENT REPORTING RULE", "SUB-AGENT REPORTING RULE"),
    ("ANTI-BRUTEFORCE", "ANTI-BRUTEFORCE"),
    ("SCANNER CONTROL", "SCANNER CONTROL"),
    ("BLACKBOX MODE", "BLACKBOX MODE"),
    ("DASHBOARD REAL-TIME PUSH", "DASHBOARD REAL-TIME PUSH"),
    ("EXECUTION SAFETY", "EXECUTION SAFETY"),
    ("END OF PROMPT", "END OF PROMPT"),
]

# Only the four real dashboard tool bases count as Darkmoon tool references;
# e.g. Moodle's core_block_get_dashboard_blocks is NOT one.
_REF_RE = re.compile(
    r"\b((?:[A-Za-z_]+_)?dashboard_"
    r"(?:init_campaign|push_finding|push_infra_node|finalize_campaign))\b"
)


def parse_front_matter(text: str):
    """Return (ok, {id,name,description}, detail)."""
    if not text.startswith("---"):
        return False, {}, "missing opening '---' front matter"
    end = text.find("\n---", 3)
    if end == -1:
        return False, {}, "missing closing '---' front matter"
    block = text[3:end]
    data = {}
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    missing = [k for k in ("id", "name", "description") if not data.get(k)]
    if missing:
        return False, data, f"front matter missing: {', '.join(missing)}"
    return True, data, ""


def lint_agent(path: str):
    stem = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    errors = []
    warnings = []

    # --- front matter ---
    ok, fm, detail = parse_front_matter(text)
    if not ok:
        errors.append(f"front-matter: {detail}")
    else:
        if fm.get("id") != stem:
            errors.append(f"front-matter: id '{fm.get('id')}' != filename '{stem}'")

    # --- required sections ---
    for label, marker in REQUIRED_SECTIONS:
        if label == "front-matter":
            continue
        if marker not in text:
            errors.append(f"missing section: {label}")

    # --- dashboard tool references ---
    refs = set()
    for m in _REF_RE.finditer(text):
        ref = m.group(1)
        if ref.startswith(SERVER_NAME + "_"):
            refs.add(ref)
            continue
        if ref in DASHBOARD_BASES:  # valid base, but missing the server prefix
            refs.add(ref)
            warnings.append(
                f"dashboard ref without '{SERVER_NAME}_' prefix "
                f"(OpenCode namespaces MCP tools as {SERVER_NAME}_<tool>; "
                f"bare form may not be callable): {ref}"
            )
            continue
        # some other prefix (e.g. dm_dashboard_push_finding)
        cand = ref.split("_", 1)[1] if "_" in ref else ref
        if cand in DASHBOARD_BASES:
            errors.append(f"dashboard ref with wrong prefix: {ref}")
            continue
        errors.append(f"unknown dashboard tool reference: {ref}")

    # soft warning: agents that push but reference no dashboard tool at all
    if "DASHBOARD REAL-TIME PUSH" in text and not refs:
        warnings.append("has DASHBOARD section but references no dashboard_* tool")

    return errors, warnings


def main():
    files = sorted(
        os.path.join(AGENTS_DIR, f)
        for f in os.listdir(AGENTS_DIR)
        if f.endswith(".md")
    )
    if not files:
        print(f"no agent .md files found in {AGENTS_DIR}")
        return 1

    clean = 0
    warned = 0
    failed = 0
    print(f"== Darkmoon default-agent structural lint ({len(files)} agents) ==\n")
    for path in files:
        stem = os.path.splitext(os.path.basename(path))[0]
        errors, warnings = lint_agent(path)
        if errors:
            failed += 1
            print(f"[FAIL] {stem}")
            for e in errors:
                print(f"        - {e}")
            for w in warnings:
                print(f"        ~ {w}")
        elif warnings:
            warned += 1
            print(f"[WARN] {stem}")
            for w in warnings:
                print(f"        ~ {w}")
        else:
            clean += 1
            print(f"[PASS] {stem}")

    print(f"\n== summary ==")
    print(f"  agents : {clean} clean, {warned} warnings-only, "
          f"{failed} with errors, {len(files)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
