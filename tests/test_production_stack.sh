#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
PROJECT="darkmoon-production-${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
PROJECT="$(printf '%s' "$PROJECT" | tr '[:upper:]_' '[:lower:]-' | tr -cd 'a-z0-9-')"
TEST_ROOT="$(mktemp -d -p "${TMPDIR:-/tmp}" darkmoon-production.XXXXXX)"

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

cleanup() {
  local status=$?
  if [[ -n "${DARKMOON_TEST_ARTIFACT_DIR:-}" ]]; then
    mkdir -p "$DARKMOON_TEST_ARTIFACT_DIR"
    "${COMPOSE[@]}" ps > "$DARKMOON_TEST_ARTIFACT_DIR/compose-ps.txt" 2>&1 || true
    "${COMPOSE[@]}" logs --no-color > "$DARKMOON_TEST_ARTIFACT_DIR/compose.log" 2>&1 || true
    if [[ -d "${DARKMOON_TEST_CAPTURE_DIR:-}" ]]; then
      cp -a "${DARKMOON_TEST_CAPTURE_DIR}/." "$DARKMOON_TEST_ARTIFACT_DIR/" 2>/dev/null || true
    fi
  fi
  if (( status != 0 )); then
    "${COMPOSE[@]}" ps >&2 || true
    "${COMPOSE[@]}" logs --no-color >&2 || true
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

"${COMPOSE[@]}" config >/dev/null
"${COMPOSE[@]}" pull darkmoon docker-proxy opencode mock-provider
"${COMPOSE[@]}" build --pull opencode-bootstrap darkmoon-mcp
"${COMPOSE[@]}" up -d

wait_for_opencode
wait_for_mcp

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
agents="$("${COMPOSE[@]}" exec -T opencode opencode agent list)"
grep -q 'pentest (primary)' <<<"$agents"
grep -q 'aws (subagent)' <<<"$agents"

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

# Confirm reasoning/variant controls survive normalized agent configuration. The
# generic adapter only serializes provider-supported HTTP fields.
debug_agent="$("${COMPOSE[@]}" exec -T opencode opencode debug agent pentest)"
grep -Eq '"variant"[[:space:]]*:[[:space:]]*"medium"' <<<"$debug_agent"
grep -Eq '"reasoning_effort"[[:space:]]*:[[:space:]]*"medium"' <<<"$debug_agent"

export DARKMOON_COMPOSE_PROJECT="$PROJECT"
export DARKMOON_COMPOSE_FILES="$ROOT/docker-compose.yml:$ROOT/tests/docker-compose.production.yml"
version="$("$ROOT/darkmoon.sh" --version)"
grep -q '1.18.12' <<<"$version"

"$ROOT/darkmoon.sh" \
  --agent pentest --model mock/darkmoon-test-model \
  --title production-wrapper --format json \
  'Call darkmoon_get_session exactly once, then report its session id.'
python3 "$ROOT/tests/assert_issue36_capture.py" \
  "$DARKMOON_TEST_CAPTURE_DIR/requests.jsonl" \
  --expect-model darkmoon-test-model \
  --expect-temperature 0.2 \
  --expect-top-p 0.9

set +e
monitor_output="$(timeout 3 "$ROOT/darkmoon.sh" --log test-session 2>&1)"
monitor_status=$?
set -e
[[ $monitor_status -eq 124 || $monitor_status -eq 143 ]]
grep -q 'streaming MCP output session=test-session' <<<"$monitor_output"

for dir in "$DARKMOON_REPORTS_DIR" "$DARKMOON_SESSIONS_DIR" "$DARKMOON_WORKSPACE_DIR"; do
  mkdir -p "$dir"
  printf 'persistent\n' > "$dir/persistence-marker"
done
config_before="$(sha256sum "$DARKMOON_SETTINGS_DIR/opencode.json" | cut -d' ' -f1)"

"${COMPOSE[@]}" restart darkmoon-mcp
wait_for_mcp
"${COMPOSE[@]}" restart opencode
wait_for_pentest_agent

for dir in "$DARKMOON_REPORTS_DIR" "$DARKMOON_SESSIONS_DIR" "$DARKMOON_WORKSPACE_DIR"; do
  grep -q persistent "$dir/persistence-marker"
done
test "$config_before" = "$(sha256sum "$DARKMOON_SETTINGS_DIR/opencode.json" | cut -d' ' -f1)"

"$ROOT/darkmoon.sh" \
  --agent pentest --model mock/darkmoon-test-model \
  --title production-after-restart --format json \
  'Call darkmoon_get_session exactly once, then report its session id.'
python3 "$ROOT/tests/assert_issue36_capture.py" \
  "$DARKMOON_TEST_CAPTURE_DIR/requests.jsonl" --minimum-requests 4 \
  --expect-model darkmoon-test-model \
  --expect-temperature 0.2 \
  --expect-top-p 0.9

echo "PASS: clean production bootstrap, provider rendering, wrapper, real toolbox MCP, user-owned persistence, and fresh CLI startup after service restarts"
