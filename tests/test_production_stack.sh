#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
PROJECT="darkmoon-production-${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
PROJECT="$(printf '%s' "$PROJECT" | tr '[:upper:]_' '[:lower:]-' | tr -cd 'a-z0-9-')"
TEST_ROOT="$(mktemp -d -p "${TMPDIR:-/tmp}" darkmoon-production.XXXXXX)"
ARTIFACT_DIR="${DARKMOON_TEST_ARTIFACT_DIR:-$TEST_ROOT/diagnostics}"
TRACE_FILE="$TEST_ROOT/test-trace.log"
CURRENT_STAGE="initialization"
mkdir -p "$ARTIFACT_DIR"

exec 9>>"$TRACE_FILE"
export BASH_XTRACEFD=9
PS4='+ ${BASH_SOURCE##*/}:${LINENO}:${FUNCNAME[0]:-main}: '
if [[ "${DARKMOON_TEST_XTRACE:-1}" == "1" ]]; then
  set -x
fi

DARKMOON_UID="$(id -u)"
DARKMOON_GID="$(id -g)"
export DARKMOON_UID DARKMOON_GID
export DARKMOON_SETTINGS_DIR="$TEST_ROOT/darkmoon-settings"
export DARKMOON_REPORTS_DIR="$TEST_ROOT/reports"
export DARKMOON_SESSIONS_DIR="$TEST_ROOT/sessions"
export DARKMOON_WORKFLOWS_DIR="$TEST_ROOT/workflows"
export DARKMOON_WORKSPACE_DIR="$TEST_ROOT/workspace"
export DARKMOON_TEST_CAPTURE_DIR="$TEST_ROOT/capture"
export OPENCODE_ENV_FILE="$TEST_ROOT/opencode.env"
mkdir -p "$DARKMOON_TEST_CAPTURE_DIR"
cat > "$OPENCODE_ENV_FILE" <<'EOF'
OPENCODE_LOCAL_MODE=true
OPENCODE_LOCAL_PROVIDER_ID=mock
OPENCODE_LOCAL_PROVIDER_NAME=Production stack mock
OPENCODE_LOCAL_BASE_URL=http://mock-provider:8000/v1
OPENCODE_LOCAL_MODEL=darkmoon-test-model
OPENCODE_LOCAL_API_KEY=not-a-real-key
EOF
chmod 600 "$OPENCODE_ENV_FILE"

COMPOSE=(
  docker compose -p "$PROJECT"
  -f "$ROOT/docker-compose.yml"
  -f "$ROOT/tests/docker-compose.production.yml"
)

stage() {
  CURRENT_STAGE="$*"
  printf '%s\n' "$CURRENT_STAGE" > "$TEST_ROOT/current-stage.txt"
  printf '\n[production-test] >>> %s\n' "$CURRENT_STAGE"
}

provider_capture_summary() {
  local capture=$1 output=$2
  if [[ ! -s "$capture" ]]; then
    printf 'No provider requests were captured.\n' > "$output"
    return 0
  fi
  python3 - "$capture" > "$output" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
        continue
    try:
        body = json.loads(line)
    except json.JSONDecodeError as exc:
        print(f"request {index}: invalid JSON: {exc}")
        continue
    tools = []
    for item in body.get("tools", []):
        if isinstance(item, dict):
            function = item.get("function")
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                tools.append(function["name"])
    roles = [
        item.get("role")
        for item in body.get("messages", [])
        if isinstance(item, dict) and isinstance(item.get("role"), str)
    ]
    print(
        f"request {index}: model={body.get('model')!r} "
        f"temperature={body.get('temperature')!r} top_p={body.get('top_p')!r} "
        f"reasoning_effort={body.get('reasoning_effort')!r} "
        f"roles={roles} tools={tools}"
    )
PY
}

collect_diagnostics() {
  local status=$1 line=$2 command=$3
  trap - ERR
  set +e +x
  mkdir -p "$ARTIFACT_DIR"

  {
    printf 'status=%s\n' "$status"
    printf 'stage=%s\n' "$CURRENT_STAGE"
    printf 'line=%s\n' "$line"
    printf 'command=%s\n' "$command"
    printf 'project=%s\n' "$PROJECT"
    printf 'test_root=%s\n' "$TEST_ROOT"
    printf 'head=%s\n' "${GITHUB_SHA:-unknown}"
  } > "$ARTIFACT_DIR/failure.txt"

  cp -f "$TRACE_FILE" "$ARTIFACT_DIR/test-trace.log" 2>/dev/null || true
  cp -f "$TEST_ROOT/current-stage.txt" "$ARTIFACT_DIR/current-stage.txt" 2>/dev/null || true
  cp -f "$TEST_ROOT"/wrapper-*.stdout "$ARTIFACT_DIR/" 2>/dev/null || true
  cp -f "$TEST_ROOT"/wrapper-*.stderr "$ARTIFACT_DIR/" 2>/dev/null || true
  cp -a "$DARKMOON_TEST_CAPTURE_DIR/." "$ARTIFACT_DIR/" 2>/dev/null || true

  "${COMPOSE[@]}" config > "$ARTIFACT_DIR/compose-config.yml" 2>&1 || true
  "${COMPOSE[@]}" ps -a > "$ARTIFACT_DIR/compose-ps.txt" 2>&1 || true
  "${COMPOSE[@]}" logs --no-color --timestamps > "$ARTIFACT_DIR/compose.log" 2>&1 || true
  docker ps -a > "$ARTIFACT_DIR/docker-ps.txt" 2>&1 || true
  mapfile -t container_ids < <("${COMPOSE[@]}" ps -aq 2>/dev/null)
  if [[ ${#container_ids[@]} -gt 0 ]]; then
    docker inspect "${container_ids[@]}" > "$ARTIFACT_DIR/docker-inspect.json" 2>&1 || true
  fi

  find "$TEST_ROOT" -maxdepth 5 -printf '%M %u:%g %s %p\n' \
    > "$ARTIFACT_DIR/test-root-files.txt" 2>&1 || true

  if [[ -f "$DARKMOON_SETTINGS_DIR/opencode.json" ]]; then
    python3 - "$DARKMOON_SETTINGS_DIR/opencode.json" > "$ARTIFACT_DIR/opencode-config-summary.json" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
summary = {
    "model": config.get("model"),
    "small_model": config.get("small_model"),
    "default_agent": config.get("default_agent"),
    "subagent_depth": config.get("subagent_depth"),
    "mcp": config.get("mcp"),
    "providers": sorted((config.get("provider") or {}).keys()),
}
print(json.dumps(summary, indent=2, sort_keys=True))
PY
  fi
  cp -f "$DARKMOON_SETTINGS_DIR/.darkmoon-bootstrap.json" \
    "$ARTIFACT_DIR/bootstrap-state.json" 2>/dev/null || true

  "${COMPOSE[@]}" exec -T opencode opencode --version \
    > "$ARTIFACT_DIR/opencode-version.txt" 2>&1 || true
  "${COMPOSE[@]}" exec -T opencode opencode mcp list \
    > "$ARTIFACT_DIR/opencode-mcp-list.txt" 2>&1 || true
  "${COMPOSE[@]}" exec -T opencode opencode agent list \
    > "$ARTIFACT_DIR/opencode-agent-list.txt" 2>&1 || true
  "${COMPOSE[@]}" exec -T opencode opencode run --help \
    > "$ARTIFACT_DIR/opencode-run-help.txt" 2>&1 || true
  "${COMPOSE[@]}" exec -T darkmoon-mcp python -m src.healthcheck \
    > "$ARTIFACT_DIR/mcp-healthcheck.txt" 2>&1 || true

  provider_capture_summary "$DARKMOON_TEST_CAPTURE_DIR/requests.jsonl" \
    "$ARTIFACT_DIR/provider-capture-summary.txt"

  printf '\n[production-test] FAILURE\n' >&2
  cat "$ARTIFACT_DIR/failure.txt" >&2
  printf '\n[production-test] wrapper stderr\n' >&2
  cat "$ARTIFACT_DIR"/wrapper-*.stderr >&2 2>/dev/null || true
  printf '\n[production-test] provider capture summary\n' >&2
  cat "$ARTIFACT_DIR/provider-capture-summary.txt" >&2 2>/dev/null || true
  printf '\n[production-test] compose state\n' >&2
  cat "$ARTIFACT_DIR/compose-ps.txt" >&2 2>/dev/null || true
  printf '\n[production-test] final service logs\n' >&2
  tail -n 250 "$ARTIFACT_DIR/compose.log" >&2 2>/dev/null || true
  printf '\n[production-test] final command trace\n' >&2
  tail -n 200 "$ARTIFACT_DIR/test-trace.log" >&2 2>/dev/null || true
}

on_error() {
  local status=$1 line=$2 command=$3
  collect_diagnostics "$status" "$line" "$command"
  exit "$status"
}
trap 'on_error "$?" "$LINENO" "$BASH_COMMAND"' ERR

cleanup() {
  local status=$?
  trap - ERR EXIT
  set +e +x
  if (( status != 0 )) && [[ ! -f "$ARTIFACT_DIR/failure.txt" ]]; then
    collect_diagnostics "$status" "EXIT" "unexpected shell exit"
  fi
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  docker run --rm -v "$TEST_ROOT:/cleanup" alpine:3.22 \
    sh -c 'rm -rf /cleanup/* /cleanup/.[!.]* /cleanup/..?*' >/dev/null 2>&1 || true
  rmdir "$TEST_ROOT" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

wait_for_opencode() {
  for _ in $(seq 1 120); do
    if "${COMPOSE[@]}" exec -T opencode opencode --version >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for OpenCode" >&2
  return 1
}

wait_for_mcp() {
  local output
  for _ in $(seq 1 120); do
    if output="$("${COMPOSE[@]}" exec -T opencode opencode mcp list 2>&1)" \
      && grep -Eqi 'darkmoon.*connected' <<<"$output"; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for Dark-Moon MCP" >&2
  return 1
}

wait_for_pentest_agent() {
  local output
  for _ in $(seq 1 120); do
    if output="$("${COMPOSE[@]}" exec -T opencode opencode agent list 2>&1)" \
      && grep -q 'pentest (primary)' <<<"$output"; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for pentest agent" >&2
  return 1
}

stage "Render production Compose topology"
"${COMPOSE[@]}" config >/dev/null

stage "Pull production images"
"${COMPOSE[@]}" pull darkmoon docker-proxy opencode mock-provider

stage "Build bootstrap and MCP support images"
"${COMPOSE[@]}" build --pull opencode-bootstrap darkmoon-mcp

stage "Start production stack"
"${COMPOSE[@]}" up -d

stage "Wait for OpenCode and MCP readiness"
wait_for_opencode
wait_for_mcp

stage "Validate generated configuration ownership and contents"
python3 - "$DARKMOON_SETTINGS_DIR/opencode.json" "$DARKMOON_SETTINGS_DIR/.darkmoon-bootstrap.json" "$DARKMOON_UID" "$DARKMOON_GID" <<'PY'
import json
import stat
import sys
from pathlib import Path

config_path, state_path = map(Path, sys.argv[1:3])
expected_uid, expected_gid = map(int, sys.argv[3:5])
config = json.loads(config_path.read_text())
state = json.loads(state_path.read_text())
assert config["model"] == "mock/darkmoon-test-model", config
assert config["small_model"] == config["model"], config
assert config["default_agent"] == "pentest", config
assert config["subagent_depth"] == 1, config
assert config["mcp"]["darkmoon"]["type"] == "remote", config
assert config["mcp"]["darkmoon"]["url"] == "http://darkmoon-mcp:8000/mcp", config
assert state["model"] == config["model"], state
assert state["mcp_transport"] == "remote", state
assert state["agents"] >= 50, state
assert state["workflows"] > 0, state
for path in (config_path, state_path):
    info = path.stat()
    assert stat.S_IMODE(info.st_mode) == 0o600, (path, oct(info.st_mode))
    assert info.st_uid == expected_uid, (path, info.st_uid, expected_uid)
    assert info.st_gid == expected_gid, (path, info.st_gid, expected_gid)
PY

test -r "$DARKMOON_SETTINGS_DIR/opencode.json"
test -f "$DARKMOON_SETTINGS_DIR/agents/pentest.md"
test -f "$DARKMOON_SETTINGS_DIR/agents/aws.md"

stage "Validate loaded agent inventory"
agents="$("${COMPOSE[@]}" exec -T opencode opencode agent list)"
grep -q 'pentest (primary)' <<<"$agents"
grep -q 'aws (subagent)' <<<"$agents"

stage "Exercise real toolbox commands through MCP"
"${COMPOSE[@]}" exec -T darkmoon-mcp python - <<'PY'
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:8000/mcp") as client:
        tools = {tool.name for tool in await client.list_tools()}
        assert {"check_tool", "execute_command", "list_workflows"} <= tools
        checked = await client.call_tool("check_tool", {"tool_name": "nuclei"})
        assert isinstance(checked.data, dict) and checked.data.get("available") is True, checked.data
        workflows = await client.call_tool("list_workflows", {})
        assert isinstance(workflows.data, dict) and workflows.data.get("count", 0) > 0, workflows.data
        execution = await client.call_tool("execute_command", {"command": "nuclei -version", "timeout": 20})
        assert isinstance(execution.data, str) and "EXIT CODE: 0" in execution.data, execution.data

asyncio.run(main())
PY

export DARKMOON_COMPOSE_PROJECT="$PROJECT"
export DARKMOON_COMPOSE_FILES="$ROOT/docker-compose.yml:$ROOT/tests/docker-compose.production.yml"

stage "Verify wrapper version dispatch"
DARKMOON_DEBUG=1 "$ROOT/darkmoon.sh" --version \
  > >(tee "$TEST_ROOT/wrapper-version.stdout") \
  2> >(tee "$TEST_ROOT/wrapper-version.stderr" >&2)
grep -q '1.18.12' "$TEST_ROOT/wrapper-version.stdout"

stage "Run wrapper-driven model and MCP round trip"
DARKMOON_DEBUG=1 "$ROOT/darkmoon.sh" \
  --agent pentest --model mock/darkmoon-test-model \
  --title production-wrapper --format json \
  'Call darkmoon_get_session exactly once, then report its session id.' \
  > >(tee "$TEST_ROOT/wrapper-first-run.stdout") \
  2> >(tee "$TEST_ROOT/wrapper-first-run.stderr" >&2)

stage "Validate first provider capture"
python3 "$ROOT/tests/assert_issue36_capture.py" \
  "$DARKMOON_TEST_CAPTURE_DIR/requests.jsonl" \
  --expect-model darkmoon-test-model \
  --expect-temperature 0.2 \
  --expect-top-p 0.9 \
  --expect-reasoning-effort medium

stage "Verify session monitor startup"
set +e
monitor_output="$(DARKMOON_DEBUG=1 timeout 3 "$ROOT/darkmoon.sh" --log test-session 2>&1)"
monitor_status=$?
set -e
printf '%s\n' "$monitor_output" | tee "$TEST_ROOT/wrapper-monitor.stdout"
[[ $monitor_status -eq 124 || $monitor_status -eq 143 ]]
grep -q 'streaming MCP output session=test-session' <<<"$monitor_output"

stage "Create persistence markers"
for dir in "$DARKMOON_REPORTS_DIR" "$DARKMOON_SESSIONS_DIR" "$DARKMOON_WORKSPACE_DIR"; do
  mkdir -p "$dir"
  printf 'persistent\n' > "$dir/persistence-marker"
done
config_before="$(sha256sum "$DARKMOON_SETTINGS_DIR/opencode.json" | cut -d' ' -f1)"

stage "Restart MCP sidecar and verify reconnect"
"${COMPOSE[@]}" restart darkmoon-mcp
wait_for_mcp

stage "Restart OpenCode and verify agents reload"
"${COMPOSE[@]}" restart opencode
wait_for_pentest_agent

stage "Verify persisted files after service restarts"
for dir in "$DARKMOON_REPORTS_DIR" "$DARKMOON_SESSIONS_DIR" "$DARKMOON_WORKSPACE_DIR"; do
  grep -q persistent "$dir/persistence-marker"
done
test "$config_before" = "$(sha256sum "$DARKMOON_SETTINGS_DIR/opencode.json" | cut -d' ' -f1)"

stage "Run second wrapper round trip after restarts"
DARKMOON_DEBUG=1 "$ROOT/darkmoon.sh" \
  --agent pentest --model mock/darkmoon-test-model \
  --title production-after-restart --format json \
  'Call darkmoon_get_session exactly once, then report its session id.' \
  > >(tee "$TEST_ROOT/wrapper-second-run.stdout") \
  2> >(tee "$TEST_ROOT/wrapper-second-run.stderr" >&2)

stage "Validate accumulated provider captures"
python3 "$ROOT/tests/assert_issue36_capture.py" \
  "$DARKMOON_TEST_CAPTURE_DIR/requests.jsonl" --minimum-requests 4 \
  --expect-model darkmoon-test-model \
  --expect-temperature 0.2 \
  --expect-top-p 0.9 \
  --expect-reasoning-effort medium

stage "Production integration complete"
echo "PASS: clean production bootstrap, provider rendering, wrapper, real toolbox MCP, user-owned persistence, and fresh CLI startup after service restarts"
