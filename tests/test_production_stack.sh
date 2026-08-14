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

  "${COMPOSE[@]}" exec -T darkmoon sh -c 'cd /opt/darkmoon/mcp/server && python -m src.healthcheck' \
    > "$ARTIFACT_DIR/mcp-healthcheck.txt" 2>&1 || true

  printf '\n[production-test] FAILURE\n' >&2
  cat "$ARTIFACT_DIR/failure.txt" >&2
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

wait_for_health() {
  local _i
  for _i in $(seq 1 120); do
    if "${COMPOSE[@]}" exec -T darkmoon sh -c 'cd /opt/darkmoon/mcp/server && python -m src.healthcheck' >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for darkmoon health" >&2
  return 1
}

stage "Render production Compose topology"
"${COMPOSE[@]}" config >/dev/null

stage "Start production stack"
"${COMPOSE[@]}" up -d

stage "Wait for the darkmoon container to become healthy"
wait_for_health

stage "Exercise real toolbox commands through MCP"
"${COMPOSE[@]}" exec -T darkmoon python - <<'PY'
import asyncio
from fastmcp import Client

async def main():
    # The MCP server registers tools with BARE names on the wire
    # (check_tool, execute_command, list_workflows, ...). The `darkmoon_` prefix
    # is applied by the Hermes MCP server key (server-side of the
    # Hermes<->MCP integration), so a raw MCP client sees bare names. These are
    # the same tools the privacy gateway + local executor path exposes for the
    # real toolbox round-trip; nuclei is a real binary baked into the image.
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

stage "Verify wrapper version dispatch"
DARKMOON_DEBUG=1 "$ROOT/darkmoon.sh" --version \
  > >(tee "$TEST_ROOT/wrapper-version.stdout") \
  2> >(tee "$TEST_ROOT/wrapper-version.stderr" >&2)
grep -q 'darkmoon.sh' "$TEST_ROOT/wrapper-version.stdout"

stage "Verify wrapper status probe"
"$ROOT/darkmoon.sh" status > "$TEST_ROOT/wrapper-status.stdout" 2>&1
grep -q 'MCP: reachable' "$TEST_ROOT/wrapper-status.stdout"

stage "Production integration complete"
echo "PASS: single darkmoon container, baked-in MCP, and real darkmoon_* toolbox MCP round-trip"
