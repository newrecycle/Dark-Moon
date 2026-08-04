#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT/tests/docker-compose.mcp.yml"
PROJECT="darkmoon-mcp-${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
PROJECT="$(printf '%s' "$PROJECT" | tr '[:upper:]_' '[:lower:]-' | tr -cd 'a-z0-9-')"

command -v docker >/dev/null 2>&1 || {
  echo "SKIP: docker is not installed" >&2
  exit 77
}
docker compose version >/dev/null

TEST_ROOT="$(mktemp -d -p "${TMPDIR:-/tmp}" darkmoon-mcp.XXXXXX)"
export DARKMOON_TEST_CONFIG_DIR="$TEST_ROOT/config"
export DARKMOON_TEST_CAPTURE_DIR="$TEST_ROOT/capture"
export DARKMOON_TEST_DATA_DIR="$TEST_ROOT/data"
export DARKMOON_TEST_WORKSPACE_DIR="$TEST_ROOT/workspace"
mkdir -p \
  "$DARKMOON_TEST_CONFIG_DIR" \
  "$DARKMOON_TEST_CAPTURE_DIR" \
  "$DARKMOON_TEST_DATA_DIR" \
  "$DARKMOON_TEST_WORKSPACE_DIR"

cp "$ROOT/tests/opencode.docker-test.json" "$DARKMOON_TEST_CONFIG_DIR/opencode.json"
cp -R "$ROOT/conf/agents" "$DARKMOON_TEST_CONFIG_DIR/agents"
cp -R "$ROOT/conf/plugins" "$DARKMOON_TEST_CONFIG_DIR/plugins"

compose() {
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

cleanup() {
  local status=$?
  if (( status != 0 )); then
    echo "--- docker compose ps ---" >&2
    compose ps >&2 || true
    echo "--- docker compose logs ---" >&2
    compose logs --no-color >&2 || true
  fi
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  case "$TEST_ROOT" in
    "${TMPDIR:-/tmp}"/darkmoon-mcp.*)
      # OpenCode runs as root and creates root-owned logs in the bind mount.
      # Remove test artifacts through a disposable root container, then remove
      # the now-empty directory as the runner user.
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
  local attempt
  for attempt in $(seq 1 60); do
    if compose exec -T opencode opencode --version >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_for_mcp() {
  local attempt output
  for attempt in $(seq 1 60); do
    if output="$(timeout 30 compose exec -T opencode opencode mcp list 2>&1)" \
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

# Exercise the real FastMCP HTTP transport and verify that it can execute a
# Docker-backed command against the test toolbox container.
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

        execution = await client.call_tool(
            "execute_command",
            {"command": "cat /etc/alpine-release", "timeout": 10},
        )
        assert isinstance(execution.data, str)
        assert "3.22" in execution.data


asyncio.run(main())
PY

agents="$(timeout 60 compose exec -T opencode opencode agent list)"
grep -q 'pentest (primary)' <<<"$agents"
grep -q 'aws (subagent)' <<<"$agents"
wait_for_mcp

run_opencode() {
  local title=$1
  timeout 180 compose exec -T opencode \
    opencode run --agent pentest --model mock/darkmoon-test-model \
    --title "$title" --format json \
    'Call darkmoon_get_session exactly once, then report its session id.'
}

run_opencode darkmoon-mcp-before-restart
python3 "$ROOT/tests/assert_issue36_capture.py" "$DARKMOON_TEST_CAPTURE_DIR/requests.jsonl"

compose restart opencode
wait_for_opencode
wait_for_mcp
run_opencode darkmoon-mcp-after-restart
python3 "$ROOT/tests/assert_issue36_capture.py" \
  "$DARKMOON_TEST_CAPTURE_DIR/requests.jsonl" --minimum-requests 4

logs="$(compose logs --no-color opencode darkmoon-mcp)"
if grep -Eqi 'failed to load plugin|failed to connect.*darkmoon|unsupported top-level parameters|configuration failed' <<<"$logs"; then
  echo "$logs" >&2
  exit 1
fi

echo "PASS: stock OpenCode, compatibility plugin, HTTP MCP sidecar, Docker execution, provider boundary, and restart"
