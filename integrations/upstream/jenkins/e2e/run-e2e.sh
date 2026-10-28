#!/usr/bin/env bash
# Real native Jenkins controller + separate inbound agent, HPI built by Maven.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
if [ ! -f "$ROOT/target/darkmoon-scan.hpi" ]; then
  (cd "$ROOT" && mvn -B -ntp clean verify)
fi
python3 "$HERE/verify_native.py"
