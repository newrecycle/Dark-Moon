#!/usr/bin/env bash
#
# check-no-regression.sh — invariant gate for the Darkmoon agents-expansion work.
#
# Run BEFORE and AFTER any change touching agents / pentest.md / apply-settings.sh /
# the MCP allow-list / live_push.py. It locks the regressions we already paid for
# last week and proves the new credential-gated agents are wired the way the
# working agents are (the INC-010a lesson: a SIGNAL block alone is not enough).
#
# Usage: tools/check-no-regression.sh [repo_dir]     (default: the repo this lives in)
# Exit 0 = all invariants hold; 1 = at least one regression.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${1:-$(cd "$HERE/.." && pwd)}"
PENTEST="$REPO/conf/agents/pentest.md"
APPLY="$REPO/conf/apply-settings.sh"
LIVEPUSH="$REPO/mcp/api/live_push.py"
AGENTS_DIR="$REPO/conf/agents"

fail=0
ok()   { printf "  [OK]   %s\n" "$1"; }
bad()  { printf "  [FAIL] %s\n" "$1"; fail=$((fail+1)); }

NEW_AGENTS="aws azure entra-id gcp github gitlab jenkins terraform ansible docker container-registry hashicorp-vault sql-databases messaging-cache"

echo "== no-regression gate for: $REPO =="

# ---- INC-010: golang dispatch requires POSITIVE evidence, never absence-of-markers
if [ -f "$PENTEST" ]; then
  echo "[INC-010] golang false-positive dispatch"
  if [ "$(grep -c 'most often Go' "$PENTEST")" -eq 0 ]; then ok "no 'most often Go' fallback text"; else bad "'most often Go' fallback text is BACK — golang will false-dispatch"; fi
  if [ "$(grep -c 'POSITIVE Go' "$PENTEST")" -ge 1 ]; then ok "'POSITIVE Go' requirement present"; else bad "'POSITIVE Go' requirement missing"; fi
  # our new planes must carry the same doctrine
  if grep -q 'POSITIVE ARTIFACT' "$PENTEST"; then ok "credential-gated planes use POSITIVE ARTIFACT doctrine"; else bad "new planes missing POSITIVE ARTIFACT doctrine"; fi
else
  bad "pentest.md not found"
fi

# ---- INC-009: report body is regenerated server-side, deterministically
if [ -f "$LIVEPUSH" ]; then
  echo "[INC-009] deterministic report generation"
  if [ "$(grep -c '_is_reference = True' "$LIVEPUSH")" -ge 1 ]; then ok "finalize regenerates report from DB (_is_reference = True)"; else bad "_is_reference no longer forced True — report can be non-deterministic"; fi
fi

# ---- INC-010a: every new agent has a routing signal; OpenCode discovers its file
if [ -f "$PENTEST" ]; then
  echo "[wiring] filename discovery + signal-matrix presence"
  for a in $NEW_AGENTS; do
    in_signal=0; grep -qE "^SIGNAL: $a plane present" "$PENTEST" && in_signal=1
    if [ -f "$AGENTS_DIR/$a.md" ] && [ "$in_signal" -eq 1 ]; then ok "$a: file + signal"; else bad "$a: file/signal missing"; fi
  done
  # new planes must NOT be added to the headless-browser web-agent list
  if grep -A4 'Web agents that ALWAYS trigger headless-browser' "$PENTEST" | grep -qE '\baws\b|\bazure\b|\bterraform\b'; then
    bad "a cloud/infra agent leaked into the headless-browser trigger list (they are NOT web agents)"
  else ok "no cloud/infra agent in the headless-browser trigger list"; fi
fi

# ---- filename registration + the .md file exists + is LF
echo "[files] agent .md present and LF"
for a in $NEW_AGENTS; do
  md="$AGENTS_DIR/$a.md"
  [ -f "$md" ] && ok "$a.md present" || bad "$a.md MISSING"
  [ -f "$md" ] && { [ "$(grep -c $'\r' "$md")" -eq 0 ] && ok "$a.md is LF" || bad "$a.md has CRLF"; }
done

# ---- pentest.md newline style unchanged for this edition
if [ -f "$PENTEST" ]; then
  cr="$(grep -c $'\r' "$PENTEST")"
  case "$REPO" in
    *Front-API*) [ "$cr" -gt 100 ] && ok "Front-API pentest.md kept CRLF ($cr)" || bad "Front-API pentest.md lost CRLF ($cr)";;
    *)           [ "$cr" -eq 0 ]   && ok "pentest.md kept LF" || bad "pentest.md gained CRLF ($cr)";;
  esac
fi

# ---- apply-settings.sh renders valid JSON and validates all Markdown agents
if [ -f "$APPLY" ]; then
  echo "[config] apply-settings.sh renders valid darkmoon.json"
  sb="$(mktemp -d)"
  mkdir -p "$sb/config" "$sb/share"
  cp -a "$AGENTS_DIR" "$sb/agents"
  if OPENCODE_CONFIG_DIR="$sb/config" \
     OPENCODE_AUTH_DIR="$sb/share" \
     OPENCODE_AGENTS_DIR="$sb/agents" \
     OPENCODE_DEFAULT_AGENTS_DIR="$AGENTS_DIR" \
     OPENCODE_CONFIG_TOOL="$REPO/conf/opencode-config.py" \
     OPENROUTER_PROVIDER=anthropic OPENROUTER_API_KEY=x OPENCODE_MODEL=anthropic/x \
     bash "$APPLY" >/dev/null 2>&1; then
    if python3 - "$sb/config/darkmoon.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
bad={"primary","secondary","prompt_file","id","mcp"}
def leaks(value, path=()):
    out=[]
    if isinstance(value,dict):
        for key,nested in value.items():
            if key in bad and path != ():
                out.append(".".join(path+(key,)))
            out.extend(leaks(nested,path+(key,)))
    elif isinstance(value,list):
        for i,nested in enumerate(value): out.extend(leaks(nested,path+(str(i),)))
    return out
found=leaks(d)
assert d.get("default_agent") == "pentest"
assert d.get("mcp",{}).get("darkmoon",{}).get("enabled") is True
assert not found, found
print("VALID: no legacy agent metadata; global darkmoon MCP enabled")
PY
    then ok "darkmoon.json valid and free of legacy agent metadata"; else bad "darkmoon.json failed compatibility checks"; fi
  else bad "apply-settings.sh failed to render darkmoon.json"; fi
  rm -rf "$sb"
fi

echo
if [ "$fail" -eq 0 ]; then echo "RESULT: PASS — no regression in $(basename "$REPO")."; exit 0
else echo "RESULT: FAIL — $fail invariant(s) broken in $(basename "$REPO")."; exit 1; fi
