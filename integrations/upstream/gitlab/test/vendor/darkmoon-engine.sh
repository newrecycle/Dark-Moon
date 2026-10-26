#!/bin/sh
# E2E "engine" stand-in: the real darkmoon-ci `run` launches this (as --oss-script)
# and then correlates/waits against the OSS data dir. Instead of running an LLM
# pentest, it plants the REAL Juice Shop campaign fixtures that @darkmoon/client
# ships (a genuine completed campaign) into the live data dir, so the REAL CLI's
# launch -> wait -> correlate -> fail-policy -> findings path runs end to end.
# The prompt is $1 (ignored). Paths come from the environment.
set -eu
FIX=/home/mehdi/darkmoon-client/fixtures/dataroot
CID=camp_20260924_70602bf9
mkdir -p "$DM_E2E_DATADIR/campaigns" "$DM_E2E_DATADIR/vulnerabilities" "$DM_E2E_REPORTS"
cp "$FIX/campaigns/$CID.json"        "$DM_E2E_DATADIR/campaigns/$CID.json"
cp "$FIX/vulnerabilities/$CID.json"  "$DM_E2E_DATADIR/vulnerabilities/$CID.json"
cp "$FIX/reports/"pentest_report_*.md "$DM_E2E_REPORTS/" 2>/dev/null || true
# fresh mtime so the correlator counts it as the new campaign
touch "$DM_E2E_DATADIR/campaigns/$CID.json"
