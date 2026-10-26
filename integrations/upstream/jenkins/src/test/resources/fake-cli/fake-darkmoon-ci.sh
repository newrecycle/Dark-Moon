#!/usr/bin/env bash
# Fake darkmoon-ci implementing the frozen CLI contract from captured fixtures.
# Used by JenkinsRule integration tests to exercise the plugin end-to-end without
# the Darkmoon engine. Fixtures live in $DARKMOON_FAKE_DIR (findings.json,
# summary.json, status.json, report.md).
set -euo pipefail

DIR="${DARKMOON_FAKE_DIR:-$(cd "$(dirname "$0")" && pwd)}"

cmd="${1:-}"; shift || true
failon=""; out=""; full=0
while [ $# -gt 0 ]; do
  case "$1" in
    --fail-on) failon="${2:-}"; shift 2;;
    --out) out="${2:-}"; shift 2;;
    --full) full=1; shift;;
    --private) shift;;
    --json|--wait|--verbose) shift;;
    --mode|--pro-url|--oss-data-dir|--oss-reports-dir|--oss-script|--target|--timeout|--poll|--severity)
      shift 2;;
    *) shift;;
  esac
done

# Record that secrets arrived via environment (value written so the test can both
# confirm env passing AND assert the value never reached the console log).
if [ -n "${DARKMOON_PRO_TOKEN:-}" ]; then printf '%s' "$DARKMOON_PRO_TOKEN" > "$DIR/received_token.txt"; fi
if [ -n "${DARKMOON_LICENSE:-}" ]; then printf '%s' "$DARKMOON_LICENSE" > "$DIR/received_license.txt"; fi
# A CLI that leaks would print secrets; this fake never does (contract compliance).

case "$cmd" in
  run)
    cid="camp_20260924_70602bf9"
    verdict="pass"; code=0; reason="no findings at or above fail-on"
    case ",$failon," in
      *,critical,*|*,high,*|*,medium,*|*,low,*|*,info,*)
        verdict="fail"; code=2; reason="findings at or above fail-on";;
    esac
    printf '{"campaignId":"%s","verdict":"%s","failOn":["%s"],"offending":{},"total":5,"reason":"%s"}\n' \
      "$cid" "$verdict" "$failon" "$reason"
    exit $code;;
  findings) cat "$DIR/findings.json"; exit 0;;
  summary)  cat "$DIR/summary.json"; exit 0;;
  status)   cat "$DIR/status.json"; exit 0;;
  report)
    cp "$DIR/report.md" "$out"
    if [ "$full" -eq 1 ]; then redacted=false; else redacted=true; fi
    echo "report written to $out (redacted=$redacted)"
    exit 0;;
  *) echo "unknown command: $cmd" >&2; exit 1;;
esac
