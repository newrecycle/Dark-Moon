#!/usr/bin/env bash
#
# End-to-end test against REAL Splunk in Docker.
# Assumes: docker compose up -d splunk   (and the container is healthy)
#
# Installs the app, pushes synthetic SAFE events via the forwarder to HEC, then
# queries them back through the search REST API and asserts:
#   * all four sourcetypes parse and are searchable
#   * JSON fields and CIM aliases (dest/signature) extract
#   * NO secret/evidence leaks into the index
#
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
C=darkmoon-splunk-test
PW="Changed-Me-123!"
HEC_TOKEN="test-hec-token"
FAILS=0

pass(){ echo "PASS $*"; }
fail(){ echo "FAIL $*"; FAILS=$((FAILS+1)); }

echo "== 1. Install app into container =="
docker cp "$ROOT/darkmoon" "$C:/opt/splunk/etc/apps/darkmoon"
docker exec -u root "$C" chown -R splunk:splunk /opt/splunk/etc/apps/darkmoon
# Restart via the REST control endpoint (the `splunk restart` CLI can hit an
# interactive port prompt in a non-TTY exec and never complete).
docker exec "$C" curl -sk -u "admin:$PW" -X POST \
  "https://localhost:8089/services/server/control/restart" >/dev/null 2>&1
sleep 20
for i in $(seq 1 40); do
  if docker exec "$C" curl -sk "https://localhost:8089/services/server/info" -u "admin:$PW" >/dev/null 2>&1; then break; fi
  sleep 5
done

echo "== 2. Verify app + alert action loaded =="
APPS=$(docker exec "$C" curl -sk "https://localhost:8089/servicesNS/-/-/apps/local/darkmoon?output_mode=json" -u "admin:$PW")
echo "$APPS" | grep -q 'Darkmoon Pentest' && pass "app installed" || fail "app not installed"
AA=$(docker exec "$C" curl -sk "https://localhost:8089/services/admin/alert_actions/darkmoon_campaign?output_mode=json" -u "admin:$PW")
echo "$AA" | grep -q 'darkmoon_campaign' && pass "alert action registered" || fail "alert action missing"

echo "== 3. Push synthetic SAFE events via forwarder to HEC =="
python3 "$HERE/gen_synthetic.py" "$HERE/fixtures/darkmoon-export.json" >/dev/null
N=$(python3 "$ROOT/forwarder/darkmoon-to-hec.py" \
      --export "$HERE/fixtures/darkmoon-export.json" \
      --hec-url "https://localhost:8088/services/collector/event" \
      --hec-token "$HEC_TOKEN" --insecure 2>&1 | grep -oE 'sent [0-9]+' | grep -oE '[0-9]+')
[ "${N:-0}" -gt 0 ] && pass "forwarder sent $N events to HEC" || fail "forwarder sent nothing"
sleep 8

run_search(){ # $1 = spl ; prints json
  docker exec "$C" curl -sk -u "admin:$PW" \
    "https://localhost:8089/services/search/jobs/export?output_mode=json&earliest_time=-60d&latest_time=now" \
    --data-urlencode "search=$1" 2>/dev/null
}

echo "== 4. Assert sourcetypes parsed =="
for st in campaign finding retest pr; do
  R=$(run_search "search index=* sourcetype=darkmoon:$st | stats count")
  CNT=$(echo "$R" | grep -oE '"count":"[0-9]+"' | head -1 | grep -oE '[0-9]+')
  if [ "${CNT:-0}" -gt 0 ]; then pass "darkmoon:$st parsed ($CNT events)"; else fail "darkmoon:$st has no events"; fi
done

echo "== 5. Assert JSON field extraction =="
R=$(run_search "search index=* sourcetype=darkmoon:finding | stats dc(severity) as s dc(mitre_attack_id) as m dc(finding_id) as f")
echo "$R" | grep -oE '"f":"[0-9]+"' | grep -qE '"f":"([1-9][0-9]*)"' && pass "finding_id extracted" || fail "finding_id not extracted"
echo "$R" | grep -oE '"m":"[0-9]+"' | grep -qE '"m":"([1-9][0-9]*)"' && pass "mitre_attack_id extracted" || fail "mitre not extracted"

echo "== 6. Assert CIM field aliases (dest, signature) =="
R=$(run_search "search index=* sourcetype=darkmoon:finding | stats dc(dest) as d dc(signature) as s")
echo "$R" | grep -oE '"d":"[0-9]+"' | grep -qE '"d":"([1-9][0-9]*)"' && pass "CIM dest alias present" || fail "CIM dest missing"
echo "$R" | grep -oE '"s":"[0-9]+"' | grep -qE '"s":"([1-9][0-9]*)"' && pass "CIM signature alias present" || fail "CIM signature missing"

echo "== 7. Assert severity CIM normalization (info -> informational) =="
R=$(run_search "search index=* sourcetype=darkmoon:finding severity=informational | stats count")
echo "$R" | grep -q '"count"' && pass "severity CIM vocabulary applied" || fail "severity not normalized"

echo "== 8. LEAK CHECK: no secret/evidence in the index =="
for term in SECRETLEAK "OR 1=1" root:x:0:0 clear_password api_key; do
  R=$(run_search "search index=* \"$term\" | stats count")
  CNT=$(echo "$R" | grep -oE '"count":"[0-9]+"' | head -1 | grep -oE '[0-9]+')
  if [ "${CNT:-0}" -eq 0 ]; then pass "no leak of '$term'"; else fail "LEAK: '$term' found $CNT times"; fi
done

echo
if [ "$FAILS" -eq 0 ]; then echo "E2E: ALL PASS"; else echo "E2E: $FAILS FAILURE(S)"; fi
exit $([ "$FAILS" -eq 0 ] && echo 0 || echo 1)
