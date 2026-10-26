#!/usr/bin/env bash
# Real GitLab Runner + REAL darkmoon-ci CLI end-to-end for the scan component.
#
# Uses `gitlab-runner exec shell` (serverless single-job run) on a flattened copy
# of the component job, so the EXACT job body a user gets runs on a real runner.
# The job invokes the REAL @darkmoon/client CLI (dist/cli/darkmoon-ci.cjs) via a
# PATH launcher. The CLI's real `run` path (launch -> wait -> correlate ->
# fail-policy) executes against a genuine completed OWASP Juice Shop campaign
# (the fixtures @darkmoon/client ships); a scripted `--oss-script` plants those
# fixtures in place of a live LLM pentest (which needs a running engine).
#
# Asserts: reports emitted + validate vs LIVE schemas; blocking vs non-blocking
# via the CLI's exit codes (0 pass / 2 findings-gate / 1 error); no secret leak;
# full report withheld by default (§4).
set -u

REPO=/home/mehdi/darkmoon-gitlab
VENDOR=$REPO/test/vendor
RUNNER=$VENDOR/gitlab-runner
CLIENT=/home/mehdi/darkmoon-client
WORK=$(mktemp -d /tmp/dm-runner-XXXXXX)

# ensure the real CLI is built
if [ ! -f "$CLIENT/dist/cli/darkmoon-ci.cjs" ]; then
  echo "building @darkmoon/client ..."; ( cd "$CLIENT" && npm ci --silent && npm run build --silent ); fi

export PATH="$VENDOR:$PATH"
export DARKMOON_LICENSE_KEY="dm_live_TESTKEY_should_never_appear_in_logs"

pass=0; fail=0
ok(){ echo "  PASS: $1"; pass=$((pass+1)); }
ko(){ echo "  FAIL: $1"; fail=$((fail+1)); }

echo "== workspace: $WORK =="
cd "$WORK" || exit 1
git init -q; git config user.email t@t; git config user.name t; git config commit.gpgsign false

run_case(){
  local label=$1 failon=$2 afec=$3 expect_gate=$4 expect_rc_nonzero=$5
  echo; echo "== CASE: $label (fail-on='$failon', allow_failure_exit_codes=$afec) =="
  # fresh OSS data dir seeded with the OTHER fixture campaigns so the target is 'new'
  local DATA="$WORK/$label/data" REPORTS="$WORK/$label/reports"
  rm -rf "$WORK/$label"; mkdir -p "$DATA/campaigns" "$DATA/vulnerabilities" "$REPORTS"
  for cid in camp_20260728_9018be77 camp_noreport camp_stuck camp_sub; do
    cp "$CLIENT/fixtures/dataroot/campaigns/$cid.json" "$DATA/campaigns/" 2>/dev/null || true
  done

  python3 "$REPO/test/render_flat.py" .gitlab-ci.yml \
    "target=http://juice-shop.local:3000" "mode=oss" "fail-on=$failon" \
    "oss-data-dir=$DATA" "oss-reports-dir=$REPORTS" "oss-script=$VENDOR/darkmoon-engine.sh" \
    "timeout=60" "allow_failure_exit_codes=$afec" >/dev/null
  git add -A; git commit -q -m "$label" >/dev/null

  set +e
  "$RUNNER" exec shell \
    --env "PATH=$VENDOR:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    --env "DARKMOON_LICENSE_KEY=$DARKMOON_LICENSE_KEY" \
    --env "DM_E2E_DATADIR=$DATA" --env "DM_E2E_REPORTS=$REPORTS" \
    darkmoon_scan >"$WORK/$label.log" 2>&1
  local rc=$?
  set -e
  echo "  runner exit code: $rc"

  local bdir
  bdir=$(find "$WORK/builds" -maxdepth 3 -name gl-code-quality-report.json 2>/dev/null | head -1)
  bdir=$(dirname "$bdir" 2>/dev/null)
  if [ -n "$bdir" ] && [ -f "$bdir/gl-code-quality-report.json" ]; then
    ok "$label: emitted gl-code-quality-report.json"
  else
    ko "$label: no code-quality report"; sed -n '1,60p' "$WORK/$label.log"; return
  fi
  [ -f "$bdir/gl-sast-report.json" ] && ok "$label: emitted gl-sast-report.json" || ko "$label: no SAST report"
  if python3 "$REPO/test/validate_schemas.py" "$bdir/gl-code-quality-report.json" "$bdir/gl-sast-report.json"; then
    ok "$label: reports validate against LIVE schemas"
  else
    ko "$label: schema validation failed"
  fi
  # count of code-quality entries (proves genuine findings flowed through)
  local n; n=$(python3 -c "import json;print(len(json.load(open('$bdir/gl-code-quality-report.json'))))")
  echo "  ($n findings mapped)"
  if [ "$expect_gate" = 2 ]; then
    [ "$n" -ge 1 ] && ok "$label: genuine findings mapped into reports ($n)" || ko "$label: expected findings to be mapped, got $n"
  fi

  if grep -q "darkmoon-ci run exit code: $expect_gate" "$WORK/$label.log"; then
    ok "$label: CLI run exit code == $expect_gate"
  else
    ko "$label: expected CLI run exit code $expect_gate"; grep "run exit code" "$WORK/$label.log"
  fi
  if [ "$expect_rc_nonzero" = yes ]; then
    [ "$rc" -ne 0 ] && ok "$label: runner reports FAILURE (blocking)" || ko "$label: expected non-zero runner rc"
  else
    [ "$rc" -eq 0 ] && ok "$label: runner reports SUCCESS (pass case)" || ko "$label: expected zero runner rc"
  fi
  grep -q "TESTKEY_should_never_appear" "$WORK/$label.log" && ko "$label: SECRET LEAKED" || ok "$label: no secret leaked"
  [ -f "$bdir/darkmoon/findings.json" ] && ko "$label: raw findings exposed (§4)" || ok "$label: full report withheld by default (§4)"
}

# 1) BLOCKING gate: fail-on critical,high -> fixture has 2 crit+1 high -> CLI exit 2 -> runner fails
run_case blocking "critical,high" "[250]" 2 yes
# 2) NON-BLOCKING gate: same gate (exit 2) tolerated via allow_failure:exit_codes [2]
#    (gitlab-runner exec does not itself evaluate allow_failure; we assert the gate
#     exit code 2 that drives it, and that the component YAML sets exit_codes:[2])
run_case nonblocking "critical,high" "[2]" 2 yes
# 3) PASS case: fail-on 'low' -> 0 low findings -> CLI exit 0 -> runner passes
run_case passing "low" "[250]" 0 no

echo; echo "== allow_failure YAML check =="
python3 "$REPO/test/render_flat.py" /tmp/_nb.yml "target=x" "allow_failure_exit_codes=[2]" >/dev/null
python3 -c "import yaml;j=yaml.safe_load(open('/tmp/_nb.yml'));k=[x for x in j if x not in ('stages',)][0];af=j[k]['allow_failure'];assert af=={'exit_codes':[2]},af;print('  PASS: non-blocking sets allow_failure.exit_codes=[2]')" && pass=$((pass+1)) || fail=$((fail+1))

echo; echo "== SUMMARY: $pass passed, $fail failed =="
echo "logs + build dirs under: $WORK"
[ "$fail" -eq 0 ]
