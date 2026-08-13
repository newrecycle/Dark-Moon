#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR"

SERVICE="darkmoon"
ENV_FILE="${OPENCODE_ENV_FILE:-$SCRIPT_DIR/.opencode.env}"

if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  echo "Neither Docker Compose v2 nor docker-compose is available." >&2
  exit 1
fi

if [[ -n "${DARKMOON_COMPOSE_PROJECT:-}" ]]; then
  DC+=(-p "$DARKMOON_COMPOSE_PROJECT")
fi

compose_files=()
if [[ -n "${DARKMOON_COMPOSE_FILES:-}" ]]; then
  IFS=: read -r -a compose_files <<<"$DARKMOON_COMPOSE_FILES"
elif [[ -n "${DARKMOON_COMPOSE_FILE:-}" ]]; then
  compose_files=("$DARKMOON_COMPOSE_FILE")
else
  case "$(uname -m)" in
    aarch64|arm64) compose_files=("$SCRIPT_DIR/docker-compose-dev.yml") ;;
    *) compose_files=("$SCRIPT_DIR/docker-compose.yml") ;;
  esac
fi
for file in "${compose_files[@]}"; do
  [[ -f "$file" ]] || { echo "Compose file not found: $file" >&2; exit 1; }
  DC+=(-f "$file")
done

if [[ -t 0 && -t 1 ]]; then
  EXEC_TTY=()
else
  EXEC_TTY=(-T)
fi

debug_command() {
  [[ "${DARKMOON_DEBUG:-0}" == "1" ]] || return 0
  printf '[darkmoon] exec:' >&2
  printf ' %q' "$@" >&2
  printf '\n' >&2
}

read_env_value() {
  local key=$1 line
  [[ -f "$ENV_FILE" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line=${line%$'\r'}
    [[ "$line" == "$key="* ]] || continue
    printf '%s' "${line#*=}"
    return 0
  done < "$ENV_FILE"
}

MCP_HOST="${DARKMOON_MCP_HOST:-127.0.0.1}"
MCP_PORT="${DARKMOON_MCP_PORT:-8000}"

wait_for_mcp_port() {
  local timeout=${1:-60}
  for _ in $(seq 1 "$timeout"); do
    if python3 - "$MCP_HOST" "$MCP_PORT" <<'PY' 2>/dev/null
import socket
import sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    with socket.create_connection((host, port), timeout=1):
        raise SystemExit(0)
except OSError:
    raise SystemExit(1)
PY
    then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for the Dark-Moon MCP on ${MCP_HOST}:${MCP_PORT}" >&2
  return 1
}

probe_mcp_port() {
  python3 - "$MCP_HOST" "$MCP_PORT" <<'PY' 2>/dev/null
import socket
import sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    with socket.create_connection((host, port), timeout=1):
        print("reachable")
except OSError:
    print("unreachable")
PY
}

preflight_provider_check() {
  # The Dark-Moon LLM brain (Hermes) runs outside the container. This preflight
  # validates any provider base URL the external brain is configured to use by
  # reaching it from inside the darkmoon container, so a loopback-only or
  # unreachable endpoint fails fast instead of hanging at request time.
  local url mode result status
  url="$(read_env_value DARKMOON_PROVIDER_BASE_URL)"
  mode="Dark-Moon provider"
  [[ -z "$url" ]] && return 0

  set +e
  result="$("${DC[@]}" exec -T darkmoon python - "$url" <<'PY'
import socket
import sys
from urllib.parse import urlparse

url = sys.argv[1]
parsed = urlparse(url)
if parsed.scheme not in {"http", "https"} or not parsed.hostname:
    print("INVALID|" + url)
    raise SystemExit(3)
if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
    print("LOOPBACK|" + url)
    raise SystemExit(3)
port = parsed.port or (443 if parsed.scheme == "https" else 80)
try:
    with socket.create_connection((parsed.hostname, port), timeout=5):
        pass
except OSError as exc:
    print(f"UNREACHABLE|{url}|{exc}")
    raise SystemExit(3)
print("OK")
PY
)"
  status=$?
  set -e
  if (( status == 0 )); then
    return 0
  fi

  case "$result" in
    LOOPBACK\|*)
      cat >&2 <<EOF
LLM provider endpoint uses a container-local loopback address:
  ${result#LOOPBACK|}
Inside Docker, localhost points to the darkmoon container, not the host.
Use host.docker.internal, the host LAN address, or a reachable service name.
EOF
      ;;
    INVALID\|*)
      echo "Invalid ${mode} URL: ${result#INVALID|}" >&2
      ;;
    UNREACHABLE\|*)
      local rest=${result#UNREACHABLE|}
      echo "${mode} endpoint is not reachable from the Dark-Moon stack: ${rest%%|*}" >&2
      echo "Reason: ${rest#*|}" >&2
      ;;
    *)
      echo "Unable to validate ${mode} endpoint: $url" >&2
      ;;
  esac
  exit 3
}

usage() {
  cat <<'EOF'
darkmoon.sh - lifecycle + MCP helper for the single darkmoon container.

The Dark-Moon LLM brain is Hermes and runs outside the container. This script
manages the merged darkmoon container and its baked-in MCP server.

Usage:
  ./darkmoon.sh up            Bring the darkmoon container up and wait for the MCP (127.0.0.1:8000).
  ./darkmoon.sh down          Stop and remove the darkmoon container.
  ./darkmoon.sh status        Show compose status and probe the MCP port.
  ./darkmoon.sh mcp <module>  Exec `python -m src.<module>` inside the container (e.g. `mcp healthcheck`).
  ./darkmoon.sh --log <id>    Tail the MCP monitoring stream for a session id.
  ./darkmoon.sh --version     Print the wrapper version.
  ./darkmoon.sh --help        Show this help.
EOF
}

if [[ "${1:-}" == "--version" || "${1:-}" == "-v" ]]; then
  echo "darkmoon.sh 1.0.0"
  exit 0
fi

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

run_in_container() {
  local script=$1
  shift
  local packed
  packed=$(printf '%q ' "$@")
  debug_command "${DC[@]}" exec "${EXEC_TTY[@]}" darkmoon sh -c "${script} ${packed}"
  exec "${DC[@]}" exec "${EXEC_TTY[@]}" darkmoon sh -c "${script} ${packed}"
}

if [[ "${1:-}" == "--log" ]]; then
  shift
  if [[ $# -lt 1 ]]; then
    echo "Usage: $0 --log <session_id>" >&2
    exit 1
  fi
  run_in_container 'cd /opt/darkmoon/mcp/server && exec python -m src.mcp_monitoring' "$1"
fi

if [[ "${1:-}" == "mcp" ]]; then
  shift
  if [[ $# -lt 1 ]]; then
    echo "Usage: $0 mcp <src-module> [args...]" >&2
    exit 1
  fi
  module="$1"
  shift
  run_in_container "cd /opt/darkmoon/mcp/server && exec python -m src.${module}" "$@"
fi

if [[ "${1:-}" == "up" ]]; then
  debug_command "${DC[@]}" up -d
  "${DC[@]}" up -d
  wait_for_mcp_port 60
  preflight_provider_check
  echo "darkmoon container is up; MCP reachable on ${MCP_HOST}:${MCP_PORT}"
  exit 0
fi

if [[ "${1:-}" == "down" ]]; then
  debug_command "${DC[@]}" down
  "${DC[@]}" down
  exit 0
fi

if [[ "${1:-}" == "status" ]]; then
  "${DC[@]}" ps "$SERVICE"
  if [[ "$(probe_mcp_port)" == "reachable" ]]; then
    echo "MCP: reachable on ${MCP_HOST}:${MCP_PORT}"
  else
    echo "MCP: NOT reachable on ${MCP_HOST}:${MCP_PORT}" >&2
    exit 1
  fi
  exit 0
fi

echo "Unknown or missing command: ${1:-<none>}" >&2
usage >&2
exit 2
