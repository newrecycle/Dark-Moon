#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR"

SERVICE="opencode"
APP_BIN="opencode"
ENV_FILE="${OPENCODE_ENV_FILE:-$SCRIPT_DIR/.opencode.env}"

if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  echo "Neither Docker Compose v2 nor docker-compose is available." >&2
  exit 1
fi

# Tests, parallel installations, and operators using `docker compose -p` must
# address the same project when this wrapper later performs `exec`. Compose file
# selection alone is insufficient because `-p` changes container discovery.
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

preflight_provider_check() {
  local url mode result
  url="$(read_env_value ANTHROPIC_BASE_URL)"
  mode="Anthropic-compatible"
  if [[ -z "$url" ]]; then
    url="$(read_env_value OPENCODE_LOCAL_BASE_URL)"
    mode="Local OpenAI-compatible"
  fi
  [[ -z "$url" ]] && return 0

  set +e
  result="$("${DC[@]}" exec -T darkmoon-mcp python - "$url" <<'PY'
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
  local status=$?
  set -e
  if (( status == 0 )); then
    return 0
  fi

  case "$result" in
    LOOPBACK\|*)
      cat >&2 <<EOF
LLM endpoint uses a container-local loopback address:
  ${result#LOOPBACK|}
Inside Docker, localhost points to the MCP/OpenCode container, not the host.
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

is_direct_opencode_command() {
  case "${1:-}" in
    -h|--help|-v|--version|--mini|completion|acp|mcp|attach|debug|providers|auth|agent|upgrade|uninstall|serve|web|models|stats|export|import|github|pr|session|plugin|plug|db|run)
      return 0
      ;;
    *) return 1 ;;
  esac
}

if [[ "${1:-}" == "--log" ]]; then
  [[ $# -ge 2 ]] || { echo "Usage: $0 --log <session_id>" >&2; exit 1; }
  debug_command "${DC[@]}" exec "${EXEC_TTY[@]}" darkmoon-mcp python -m src.mcp_monitoring "$2"
  exec "${DC[@]}" exec "${EXEC_TTY[@]}" darkmoon-mcp \
    python -m src.mcp_monitoring "$2"
fi

preflight_provider_check

# OpenCode global logging/plugin flags must precede the selected command. Pull
# them off before deciding whether the remaining arguments are an explicit
# top-level command or an implicit `opencode run` invocation.
GLOBAL_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --print-logs|--pure)
      GLOBAL_ARGS+=("$1")
      shift
      ;;
    --log-level)
      [[ $# -ge 2 ]] || { echo "--log-level requires a value" >&2; exit 2; }
      GLOBAL_ARGS+=("$1" "$2")
      shift 2
      ;;
    --log-level=*)
      GLOBAL_ARGS+=("$1")
      shift
      ;;
    *) break ;;
  esac
done

if [[ $# -eq 0 ]]; then
  debug_command "${DC[@]}" exec "${EXEC_TTY[@]}" "$SERVICE" "$APP_BIN" "${GLOBAL_ARGS[@]}"
  exec "${DC[@]}" exec "${EXEC_TTY[@]}" "$SERVICE" "$APP_BIN" "${GLOBAL_ARGS[@]}"
elif is_direct_opencode_command "$1"; then
  debug_command "${DC[@]}" exec "${EXEC_TTY[@]}" "$SERVICE" "$APP_BIN" "${GLOBAL_ARGS[@]}" "$@"
  exec "${DC[@]}" exec "${EXEC_TTY[@]}" "$SERVICE" "$APP_BIN" "${GLOBAL_ARGS[@]}" "$@"
else
  debug_command "${DC[@]}" exec "${EXEC_TTY[@]}" "$SERVICE" "$APP_BIN" "${GLOBAL_ARGS[@]}" run "$@"
  exec "${DC[@]}" exec "${EXEC_TTY[@]}" "$SERVICE" "$APP_BIN" "${GLOBAL_ARGS[@]}" run "$@"
fi
