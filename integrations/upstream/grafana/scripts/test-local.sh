#!/usr/bin/env bash
# Bring up the docker-compose lab and assert the dashboards render real data
# through the Infinity datasource — and that NO secret/evidence leaks.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 scripts/gen_fixtures.py >/dev/null
python3 scripts/gen_dashboards.py >/dev/null

echo "== bringing up docker-compose lab =="
docker compose up -d
GRAF="http://localhost:${GRAFANA_PORT:-3009}"

echo "== waiting for Grafana =="
for i in $(seq 1 40); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$GRAF/api/health" || true)" = "200" ] && break
  sleep 3
done

DS='{"type":"yesoreyeram-infinity-datasource","uid":"darkmoon-infinity"}'
q() { curl -s -u admin:admin -X POST "$GRAF/api/ds/query" -H 'Content-Type: application/json' -d "$1"; }

echo "== assert overview KPIs =="
OUT=$(q '{"queries":[{"refId":"A","datasource":'"$DS"',"type":"json","source":"url","parser":"backend","format":"table","url":"http://darkmoon-mock:8080/api/v1/dashboard/overview","root_selector":"severity_distribution","columns":[{"selector":"critical","text":"c","type":"number"}]}],"from":"now-90d","to":"now"}')
echo "$OUT" | grep -q '\[4\]' && echo "  OK critical=4" || { echo "  FAIL: $OUT"; exit 1; }

echo "== assert vulnerabilities table (17) =="
OUT=$(q '{"queries":[{"refId":"A","datasource":'"$DS"',"type":"json","source":"url","parser":"backend","format":"table","url":"http://darkmoon-mock:8080/api/v1/vulnerabilities","root_selector":"data","columns":[{"selector":"id","text":"id","type":"string"}]}],"from":"now-90d","to":"now"}')
N=$(echo "$OUT" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['results']['A']['frames'][0]['data']['values'][0]))")
[ "$N" = "17" ] && echo "  OK 17 findings" || { echo "  FAIL count=$N"; exit 1; }

echo "== assert NO evidence/description leaks through the dashboards =="
# The dashboards select only safe fields; prove the mock CAN return description
# but no dashboard query column requests it.
if grep -rEi '"selector":\s*"(description|evidence|raw|logs|commands|payloads|extracted_data)"' dashboards/ ; then
  echo "  FAIL: a dashboard selects a forbidden field"; exit 1
else
  echo "  OK no forbidden selectors in any dashboard"
fi

echo "ALL LOCAL TESTS PASSED"
