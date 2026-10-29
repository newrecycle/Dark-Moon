#!/usr/bin/env bash
# Synthetic fixture engine. The packaged darkmoon-ci invokes this on the agent.
# This does not contact the target, perform a scan, or emit real evidence.
set -euo pipefail
D='/opt/synthetic data'
R='/opt/synthetic reports'
# The real Pipeline writes its synthetic case to the agent-local fixture
# directory. The CLI still launches this script with its ordinary prompt and
# correlation nonce. Never default a missing fixture to a success-shaped scan.
S=""
if [ -f "$D/scenario-native.txt" ]; then
  S="$(cat "$D/scenario-native.txt")"
fi
case "$S" in
  high|empty|nonempty_pass|medium|missing_report|malformed_campaign|missing_findings|malformed_findings|wrong_findings_type|foreign_findings|failed|stopped|timed_out|running|ambiguous_campaigns|unrelated_campaign|missing_identity|wrong_root|producer_failed|conflicting_roots) ;;
  *) echo "Synthetic fixture scenario unavailable" >&2; exit 2;;
esac
ID="camp_native_$(date +%s)_${BASHPID}"
ROOT="ses_native_${BASHPID}"
[ "${2:-}" = '--format' ] && [ "${3:-}" = 'json' ] || exit 2
if [ "$S" != 'missing_identity' ]; then
  printf '{"type":"step_start","sessionID":"%s","part":{"type":"step-start","sessionID":"%s"}}\n' "$ROOT" "$ROOT"
fi
BOUND_ROOT="$ROOT"
[ "$S" = 'wrong_root' ] && BOUND_ROOT=ses_foreign
STATUS=completed
case "$S" in
  failed|stopped|timed_out|running) STATUS="$S";;
esac
mkdir -p "$D/campaigns" "$D/vulnerabilities" "$R"
REPORT_PATH="/reports/native-report.md"
[ "$S" = "missing_report" ] && REPORT_PATH="/reports/missing-native-$ID.md"
cat > "$D/campaigns/$ID.json" <<EOF
{"id":"$ID","opencode_session_id":"$BOUND_ROOT","status":"$STATUS","target_id":"target_native","project_id":"proj_native","date":"2026-10-28T00:00:00Z","stats":{"total_findings":2,"critical":0,"high":1,"medium":1},"report_path":"$REPORT_PATH"}
EOF
if [ "$S" = "malformed_campaign" ]; then
  printf '{malformed-campaign\n' > "$D/campaigns/$ID.json"
fi
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
    [ "$S" = "unrelated_campaign" ] && SEVERITY=info
    cat > "$D/vulnerabilities/$ID.json" <<EOF
[{"id":"finding_native_one","campaign_id":"$FINDING_CAMPAIGN","target_id":"target_native","title":"Synthetic test issue","category":"test","status":"confirmed","severity":"$SEVERITY","endpoint":"GET /synthetic","evidence":{"raw_request":"SYNTHETIC_EVIDENCE_SECRET_a1b2c3","raw_response":"SYNTHETIC_RESPONSE_SECRET_x7y8z9"},"description":"SYNTHETIC_EVIDENCE_SECRET_a1b2c3"}]
EOF
    ;;
esac
if [ "$S" = "ambiguous_campaigns" ] || [ "$S" = "unrelated_campaign" ]; then
  OTHER_ROOT="$ROOT"
  [ "$S" = "unrelated_campaign" ] && OTHER_ROOT=ses_foreign
  printf '{"id":"%s_second","opencode_session_id":"%s","status":"completed"}\n' "$ID" "$OTHER_ROOT" > "$D/campaigns/${ID}_second.json"
fi
printf 'Synthetic report with redacted-only metadata.\n' > "$R/native-report.md"
[ "$S" != 'producer_failed' ] || exit 1
if [ "$S" = 'conflicting_roots' ]; then
  printf '{"type":"step_start","sessionID":"ses_foreign","part":{"type":"step-start","sessionID":"ses_foreign"}}\n'
fi
