#!/usr/bin/env bash
# Stand-in for the Darkmoon engine: materialize a fresh campaign from fixtures so
# the REAL darkmoon-ci can launch->correlate->wait->read against it.
set -e
NEWID="camp_ci_$(date +%s)_$$"
D="/var/darkmoon/data"; FIX="/opt/darkmoon-fixtures"
sed "s/camp_20260924_70602bf9/$NEWID/g" "$FIX/campaign.raw.json" > "$D/campaigns/$NEWID.json"
sed "s/camp_20260924_70602bf9/$NEWID/g" "$FIX/vulns.raw.json"    > "$D/vulnerabilities/$NEWID.json"
cp "$FIX/report.md" "$D/reports/pentest_report_127.0.0.1_3000_ci.md" 2>/dev/null || true
exit 0
