#!/usr/bin/env bash
# Synthetic fixture engine. The packaged darkmoon-ci invokes this on the agent.
# This does not contact the target, perform a scan, or emit real evidence.
set -euo pipefail
D='/opt/synthetic data'
R='/opt/synthetic reports'
# The Pipeline passes a unique program/scenario over the real CLI launch
# grammar, avoiding assumptions about Jenkins withEnv propagation to the
# plugin's EnvVars. Reject a missing or unknown case rather than defaulting.
S=""
PROMPT="${1:-}"
if [[ "$PROMPT" == *PROGRAM=* ]]; then
  S="${PROMPT##*PROGRAM=}"
  S="${S%% *}"
fi
case "$S" in
  high|empty|nonempty_pass|medium|missing_findings|malformed_findings|wrong_findings_type|foreign_findings|failed|stopped|timed_out|running) ;;
  *) echo "Synthetic fixture scenario unavailable" >&2; exit 2;;
esac
ID="camp_native_$(date +%s)_$"
STATUS=completed
case "$S" in
  failed|stopped|timed_out|running) STATUS="$S";;
esac
mkdir -p "$D/campaigns" "$D/vulnerabilities" "$R"
cat > "$D/campaigns/$ID.json" <<EOF
{"id":"$ID","status":"$STATUS","target_id":"target_native","project_id":"proj_native","date":"2026-10-28T00:00:00Z","stats":{"total_findings":2,"critical":0,"high":1,"medium":1},"report_path":"/reports/native-report.md"}
EOF
case "$S" in
  missing_findings) rm -f "$D/vulnerabilities/$ID.json";;
  malformed_findings) printf 'not json\n' > "$D/vulnerabilities/$ID.json";;
  wrong_findings_type) printf '{}\n' > "$D/vulnerabilities/$ID.json";;
  empty) printf '[]\n' > "$D/vulnerabilities/$ID.json";;
  *)
    FINDING_CAMPAIGN="$ID"
    [ "$S" = "foreign_findings" ] && FINDING_CAMPAIGN=camp_foreign
    SEVERITY=high
    [ "$S" = "medium" ] && SEVERITY=medium
    cat > "$D/vulnerabilities/$ID.json" <<EOF
[{"id":"finding_native_one","campaign_id":"$FINDING_CAMPAIGN","target_id":"target_native","title":"Synthetic test issue","category":"test","status":"confirmed","severity":"$SEVERITY","endpoint":"GET /synthetic","evidence":{"raw_request":"SYNTHETIC_EVIDENCE_SECRET_a1b2c3","raw_response":"SYNTHETIC_RESPONSE_SECRET_x7y8z9"},"description":"SYNTHETIC_EVIDENCE_SECRET_a1b2c3"}]
EOF
    ;;
esac
printf 'Synthetic report with redacted-only metadata.\n' > "$R/native-report.md"
