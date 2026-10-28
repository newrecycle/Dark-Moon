#!/bin/sh
# Owned test-only engine: completed fixture campaign with genuinely empty findings.
set -eu
FIX=${DARKMOON_CLIENT_FIXTURES:-$(CDPATH= cd -- "$(dirname -- "$0")/../../../client/fixtures/dataroot" && pwd)}
CID=camp_20260924_70602bf9
mkdir -p "$DM_E2E_DATADIR/campaigns" "$DM_E2E_DATADIR/vulnerabilities" "$DM_E2E_REPORTS"
cp "$FIX/campaigns/$CID.json" "$DM_E2E_DATADIR/campaigns/$CID.json"
printf '[]\n' > "$DM_E2E_DATADIR/vulnerabilities/$CID.json"
python3 - "$DM_E2E_DATADIR/campaigns/$CID.json" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as stream:
    campaign = json.load(stream)
campaign["overall_risk"] = "info"
campaign["stats"] = {key: 0 for key in ("total_findings", "critical", "high", "medium", "low", "info")}
with open(path, "w", encoding="utf-8") as stream:
    json.dump(campaign, stream)
PY
touch "$DM_E2E_DATADIR/campaigns/$CID.json"
