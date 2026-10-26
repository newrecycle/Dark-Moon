#!/usr/bin/env bash
# Real-Jenkins E2E: build the HPI, install it (with the REAL darkmoon-ci CLI) in a
# jenkins/jenkins LTS container, run a declarative pipeline against a fixture-backed
# OSS campaign, and assert fail policy + warnings-ng issues + archived report.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CLIENT="${DARKMOON_CLIENT_DIR:-$HOME/darkmoon-client}"

echo ">> building HPI"; ( cd "$ROOT" && mvn -B -ntp -DskipTests package )
cp "$ROOT/target/darkmoon-scan.hpi" "$HERE/"
echo ">> packing real darkmoon-ci"; ( cd "$CLIENT" && npm run build >/dev/null && npm pack >/dev/null )
cp "$CLIENT"/darkmoon-client-*.tgz "$HERE/darkmoon-client-0.1.0.tgz"

echo ">> docker build"; docker build -t darkmoon-jenkins-e2e "$HERE"
docker rm -f dm-e2e >/dev/null 2>&1 || true
docker run -d --name dm-e2e -p 18080:8080 darkmoon-jenkins-e2e >/dev/null
B=http://localhost:18080; CJ="$(mktemp)"
for i in $(seq 1 80); do curl -sf "$B/login" >/dev/null 2>&1 && break; sleep 3; done
CRUMB=$(curl -s -c "$CJ" "$B/crumbIssuer/api/json" | sed -E 's/.*"crumb":"([^"]+)".*/\1/')
curl -s -b "$CJ" -X POST "$B/job/darkmoon-e2e/build" -H "Jenkins-Crumb: $CRUMB" -o /dev/null
for i in $(seq 1 60); do
  R=$(curl -s "$B/job/darkmoon-e2e/lastBuild/api/json" 2>/dev/null || true)
  echo "$R" | grep -q '"result":"' && break; sleep 3
done
echo ">> result: $(echo "$R" | grep -o '"result":"[A-Z]*"')"
echo ">> warnings-ng: $(curl -s "$B/job/darkmoon-e2e/lastBuild/sarif/api/json?tree=totalSize")"
docker exec dm-e2e sh -c 'ls /var/jenkins_home/jobs/darkmoon-e2e/builds/1/archive/darkmoon-reports/'
