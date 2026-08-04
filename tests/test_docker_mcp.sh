#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
COMPOSE_FILE="$ROOT/tests/docker-compose.mcp.yml"
PROJECT="darkmoon-mcp-${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
PROJECT="$(printf '%s' "$PROJECT" | tr '[:upper:]_' '[:lower:]-' | tr -cd 'a-z0-9-')"

command -v docker >/dev/null 2>&1 || { echo "SKIP: docker is not installed" >&2; exit 77; }
docker compose version >/dev/null

TEST_ROOT="$(mktemp -d -p "${TMPDIR:-/tmp}" darkmoon-mcp.XXXXXX)"
export DARKMOON_TEST_CONFIG_DIR="$TEST_ROOT/config"
export DARKMOON_TEST_CAPTURE_DIR="$TEST_ROOT/capture"
export DARKMOON_TEST_DATA_DIR="$TEST_ROOT/data"
export DARKMOON_TEST_WORKSPACE_DIR="$TEST_ROOT/workspace"
mkdir -p "$DARKMOON_TEST_CONFIG_DIR" "$DARKMOON_TEST_CAPTURE_DIR" "$DARKMOON_TEST_DATA_DIR" "$DARKMOON_TEST_WORKSPACE_DIR"

cp "$ROOT/tests/opencode.docker-test.json" "$DARKMOON_TEST_CONFIG_DIR/opencode.json"
cp -R "$ROOT/conf/agents" "$DARKMOON_TEST_CONFIG_DIR/agents"
cp -R "$ROOT/conf/plugins" "$DARKMOON_TEST_CONFIG_DIR/plugins"

COMPOSE=(docker compose -p "$PROJECT" -f "$COMPOSE_FILE")
compose() { "${COMPOSE[@]}" "$@"; }

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
    echo "--- docker compose ps ---" >&2
    compose ps >&2 || true
    echo "--- docker compose logs ---" >&2
    compose logs --no-color >&2 || true
  fi
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  case "$TEST_ROOT" in
    "${TMPDIR:-/tmp}"/darkmoon-mcp.*)
      docker run --rm -v "$TEST_ROOT:/cleanup" alpine:3.22 \
        sh -c 'rm -rf /cleanup/* /cleanup/.[!.]* /cleanup/..?*' >/dev/null 2>&1 || true
      rmdir "$TEST_ROOT" >/dev/null 2>&1 || true
      ;;
    *) echo "refusing to remove unexpected test path: $TEST_ROOT" >&2 ;;
  esac
  exit "$status"
}
trap cleanup EXIT

wait_for_opencode() {
  for _ in $(seq 1 60); do
    if compose exec -T opencode opencode --version >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  return 1
}

wait_for_mcp() {
  local output
  for _ in $(seq 1 60); do
    if output="$(timeout 30 "${COMPOSE[@]}" exec -T opencode opencode mcp list 2>&1)" \
      && grep -Eqi 'darkmoon.*connected' <<<"$output"; then
      printf '%s\n' "$output"
      return 0
    fi
    sleep 2
  done
  return 1
}

compose config >/dev/null
compose down -v --remove-orphans >/dev/null 2>&1 || true
compose pull darkmoon mock-provider opencode
compose build --pull darkmoon-mcp
compose up -d
wait_for_opencode

compose exec -T darkmoon-mcp python - <<'PY'
import asyncio
from fastmcp import Client

async def main() -> None:
    client = Client("http://127.0.0.1:8000/mcp")
    async with client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools}
        assert "get_session" in names
        assert "execute_command" in names
        session = await client.call_tool("get_session", {})
        assert isinstance(session.data, dict)
        assert session.data.get("session_id")
        execution = await client.call_tool("execute_command", {"command": "cat /etc/os-release", "timeout": 10})
        assert isinstance(execution.data, str), repr(execution.data)
        assert "EXIT CODE: 0" in execution.data, execution.data
        assert "STDOUT:" in execution.data, execution.data
        assert "Ubuntu" in execution.data, execution.data

asyncio.run(main())
PY

agents="$(timeout 60 "${COMPOSE[@]}" exec -T opencode opencode agent list)"
grep -q 'pentest (primary)' <<<"$agents"
grep -q 'aws (subagent)' <<<"$agents"
wait_for_mcp

# Prove reasoning/variant options survive configuration normalization and the
# compatibility plugin. The generic OpenAI-compatible adapter serializes only
# provider-supported fields, so raw HTTP assertions cover model/temperature/top_p.
debug_agent="$(timeout 60 "${COMPOSE[@]}" exec -T opencode opencode debug agent pentest)"
grep -Eq '"variant"[[:space:]]*:[[:space:]]*"medium"' <<<"$debug_agent"
grep -Eq '"reasoning_effort"[[:space:]]*:[[:space:]]*"medium"' <<<"$debug_agent"

run_opencode() {
  local title=$1
  timeout 180 "${COMPOSE[@]}" exec -T opencode \
    opencode run --agent pentest --model mock/darkmoon-test-model \
    --title "$title" --format json \
    'Call darkmoon_get_session exactly once, then report its session id.'
}

assert_capture() {
  python3 "$ROOT/tests/assert_issue36_capture.py" \
    "$DARKMOON_TEST_CAPTURE_DIR/requests.jsonl" "$@" \
    --expect-model darkmoon-test-model \
    --expect-temperature 0.2 \
    --expect-top-p 0.9
}

run_opencode darkmoon-mcp-before-restart
assert_capture

compose restart darkmoon-mcp
wait_for_mcp
compose restart opencode
wait_for_opencode
wait_for_mcp
run_opencode darkmoon-mcp-after-restart
assert_capture --minimum-requests 4

logs="$(compose logs --no-color opencode darkmoon-mcp)"
if grep -Eqi 'failed to load plugin|failed to connect.*darkmoon|unsupported top-level parameters|generation parameter mismatch|configuration failed' <<<"$logs"; then
  echo "$logs" >&2
  exit 1
fi

echo "PASS: stock OpenCode, compatibility plugin, protocol MCP, Docker execution, provider boundary, and fresh CLI startup after restarts"
