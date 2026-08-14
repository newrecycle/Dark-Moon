#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
TEMP_ROOT="$(mktemp -d -p "${TMPDIR:-/tmp}" darkmoon-wrapper.XXXXXX)"
trap 'rm -rf "$TEMP_ROOT"' EXIT

FAKE_BIN="$TEMP_ROOT/bin"
CAPTURE="$TEMP_ROOT/docker-args.txt"
ENV_FILE="$TEMP_ROOT/empty.env"
mkdir -p "$FAKE_BIN"
: > "$ENV_FILE"

cat > "$FAKE_BIN/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "compose" && "${2:-}" == "version" ]]; then
  exit 0
fi
: "${DARKMOON_WRAPPER_CAPTURE:?set DARKMOON_WRAPPER_CAPTURE}"
printf '<%s>' "$@" >> "$DARKMOON_WRAPPER_CAPTURE"
printf '\n' >> "$DARKMOON_WRAPPER_CAPTURE"
EOF
chmod +x "$FAKE_BIN/docker"

export PATH="$FAKE_BIN:$PATH"
export DARKMOON_WRAPPER_CAPTURE="$CAPTURE"
export DARKMOON_COMPOSE_FILE="$ROOT/docker-compose.yml"
export OPENCODE_ENV_FILE="$ENV_FILE"

run_case() {
  : > "$CAPTURE"
  "$ROOT/darkmoon.sh" "$@" </dev/null \
    >"$TEMP_ROOT/stdout" 2>"$TEMP_ROOT/stderr"
}

assert_line() {
  local expected=$1
  grep -Fx -- "$expected" "$CAPTURE" >/dev/null || {
    printf 'FAIL: expected Docker call %s\nactual:\n' "$expected" >&2
    cat "$CAPTURE" >&2
    return 1
  }
}

run_case --version
grep -q '^darkmoon.sh ' "$TEMP_ROOT/stdout"
[[ ! -s "$CAPTURE" ]]
echo "PASS: version does not launch a container"

run_case down
assert_line "<compose><-f><$ROOT/docker-compose.yml><down>"
echo "PASS: down targets only the plugin Compose project"

run_case mcp healthcheck
assert_line "<compose><-f><$ROOT/docker-compose.yml><exec><-T><darkmoon><sh><-c><cd /opt/darkmoon/mcp/server && exec python -m src.healthcheck '' >"
echo "PASS: MCP helper executes in the plugin service"

run_case status
assert_line "<compose><-f><$ROOT/docker-compose.yml><ps><darkmoon>"
assert_line "<compose><-f><$ROOT/docker-compose.yml><exec><-T><darkmoon><sh><-c><cd /opt/darkmoon/mcp/server && python -m src.healthcheck>"
grep -q 'MCP: reachable' "$TEMP_ROOT/stdout"
echo "PASS: status verifies the plugin-owned MCP process"

if run_case; then
  echo "FAIL: missing command should be rejected" >&2
  exit 1
elif [[ $? -ne 2 ]]; then
  echo "FAIL: missing command returned the wrong status" >&2
  exit 1
fi
[[ ! -s "$CAPTURE" ]]
echo "PASS: missing command cannot fall back to an in-container LLM"
