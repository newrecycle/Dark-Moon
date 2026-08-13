#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
COMPOSE_FILE="$ROOT/tests/docker-compose.mcp.yml"
PROJECT="darkmoon-mcp-${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
PROJECT="$(printf '%s' "$PROJECT" | tr '[:upper:]_' '[:lower:]-' | tr -cd 'a-z0-9-')"

command -v docker >/dev/null 2>&1 || { echo "SKIP: docker is not installed" >&2; exit 77; }
docker compose version >/dev/null

TEST_ROOT="$(mktemp -d -p "${TMPDIR:-/tmp}" darkmoon-mcp.XXXXXX)"
export DARKMOON_TEST_CAPTURE_DIR="$TEST_ROOT/capture"
mkdir -p "$DARKMOON_TEST_CAPTURE_DIR"

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

wait_for_mcp() {
  local _i
  for _i in $(seq 1 60); do
    if compose exec -T darkmoon python -c "import socket; socket.create_connection(('127.0.0.1', 8000), timeout=1)" 2>/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

compose config >/dev/null
compose up -d
wait_for_mcp

compose exec -T darkmoon python - <<'PY'
import asyncio
from fastmcp import Client

async def main() -> None:
    client = Client("http://127.0.0.1:8000/mcp")
    async with client:
        tools = {tool.name for tool in await client.list_tools()}
        assert "darkmoon_get_session" in tools
        assert "darkmoon_execute_command" in tools
        assert "darkmoon_list_workflows" in tools
        session = await client.call_tool("darkmoon_get_session", {})
        assert isinstance(session.data, dict)
        assert session.data.get("session_id")
        execution = await client.call_tool("darkmoon_execute_command", {"command": "cat /etc/os-release", "timeout": 10})
        assert isinstance(execution.data, str), repr(execution.data)
        assert "EXIT CODE: 0" in execution.data, execution.data
        assert "STDOUT:" in execution.data, execution.data

asyncio.run(main())
PY

logs="$(compose logs --no-color darkmoon)"
if grep -Eqi 'failed to (start|load|connect)|configuration failed|unhandled exception' <<<"$logs"; then
  echo "$logs" >&2
  exit 1
fi

echo "PASS: single darkmoon container, local-exec toolbox, and darkmoon_* MCP round-trip"
