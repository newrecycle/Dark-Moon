#!/usr/bin/env bash
# Real E2E: run the BUNDLED action (dist/index.js) exactly as a GitHub runner
# would (INPUT_* env, GITHUB_OUTPUT, GITHUB_STEP_SUMMARY), against a real
# Darkmoon OSS container. Prints outputs + step summary and asserts no leak.
#
# Usage: e2e-run.sh <scenario-name> <env-file>
#   env-file: one KEY=VALUE per line (INPUT_* names may contain hyphens).
# Optional probes (from current env): SECRET_PROBE, EVIDENCE_PROBE.
set -uo pipefail
cd "$(dirname "$0")/.."

SCENARIO="${1:-unnamed}"
ENVFILE="${2:?env-file required}"

WORK="$(mktemp -d)"
export GITHUB_OUTPUT="$WORK/output"
export GITHUB_STEP_SUMMARY="$WORK/summary.md"
export RUNNER_TEMP="$WORK"
: > "$GITHUB_OUTPUT"
: > "$GITHUB_STEP_SUMMARY"
LOG="$WORK/run.log"

# Read KEY=VALUE lines (hyphens allowed) into an env-assignment array.
ASSIGN=()
while IFS= read -r line; do
  [ -z "$line" ] && continue
  case "$line" in \#*) continue;; esac
  ASSIGN+=("$line")
done < "$ENVFILE"

echo "### E2E scenario: $SCENARIO"
echo "workdir: $WORK"

env "${ASSIGN[@]}" node dist/index.js > "$LOG" 2>&1
CODE=$?

echo "--- action stdout/stderr (as the action emitted it) ---"
cat "$LOG"
echo "--- exit code: $CODE ---"
echo "--- GITHUB_OUTPUT ---"
cat "$GITHUB_OUTPUT"
echo "--- GITHUB_STEP_SUMMARY ---"
cat "$GITHUB_STEP_SUMMARY"

FAILLEAK=0
if [ -n "${SECRET_PROBE:-}" ]; then
  # A real runner consumes ::add-mask:: lines (that IS the mask registration) and
  # never displays them. A genuine leak is the secret appearing on any OTHER line.
  if grep -F "$SECRET_PROBE" "$LOG" "$GITHUB_STEP_SUMMARY" 2>/dev/null | grep -v '::add-mask::' | grep -q .; then
    echo "!!! SECRET (api-token) LEAK DETECTED (outside ::add-mask::)"; FAILLEAK=1
  else
    echo ">>> OK: api-token appears only on the ::add-mask:: registration line (masked by runner)"
  fi
fi
if [ -n "${EVIDENCE_PROBE:-}" ]; then
  if grep -qF "$EVIDENCE_PROBE" "$GITHUB_STEP_SUMMARY"; then
    echo "!!! EVIDENCE LEAK DETECTED in step summary"; FAILLEAK=1
  else
    echo ">>> OK: finding-evidence probe not found in step summary"
  fi
fi

echo "RESULT scenario='$SCENARIO' exit=$CODE leak=$FAILLEAK WORKDIR=$WORK"
