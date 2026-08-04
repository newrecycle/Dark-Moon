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
printf '%s\n' "$@" > "$DARKMOON_WRAPPER_CAPTURE"
EOF
chmod +x "$FAKE_BIN/docker"

export PATH="$FAKE_BIN:$PATH"
export DARKMOON_WRAPPER_CAPTURE="$CAPTURE"
export DARKMOON_COMPOSE_FILE="$ROOT/docker-compose.yml"
export OPENCODE_ENV_FILE="$ENV_FILE"

assert_args() {
  local label=$1
  shift
  local -a actual expected
  mapfile -t actual < "$CAPTURE"
  expected=("$@")
  if [[ "${actual[*]}" != "${expected[*]}" ]]; then
    printf 'FAIL: %s\nexpected:' "$label" >&2
    printf ' <%s>' "${expected[@]}" >&2
    printf '\nactual:' >&2
    printf ' <%s>' "${actual[@]}" >&2
    printf '\n' >&2
    return 1
  fi
  printf 'PASS: %s\n' "$label"
}

run_case() {
  : > "$CAPTURE"
  "$ROOT/darkmoon.sh" "$@" </dev/null >"$TEMP_ROOT/stdout" 2>"$TEMP_ROOT/stderr"
}

prefix=(compose -f "$ROOT/docker-compose.yml" exec -T opencode opencode)

run_case
assert_args "no arguments opens the TUI" "${prefix[@]}"

run_case --version
assert_args "version remains a top-level flag" "${prefix[@]}" --version

run_case mcp list
assert_args "explicit subcommands remain top-level" "${prefix[@]}" mcp list

run_case --mini
assert_args "mini mode remains top-level" "${prefix[@]}" --mini

run_case "TARGET: example.com"
assert_args "plain prompt uses opencode run" "${prefix[@]}" run "TARGET: example.com"

run_case --agent pentest --model mock/test --title wrapper-test --format json "Call one tool"
assert_args "run options are routed through opencode run" \
  "${prefix[@]}" run --agent pentest --model mock/test --title wrapper-test --format json "Call one tool"

run_case --print-logs --log-level DEBUG --agent pentest "Trace this request"
assert_args "global flags precede implicit run" \
  "${prefix[@]}" --print-logs --log-level DEBUG run --agent pentest "Trace this request"

echo "PASS: darkmoon.sh wrapper routing"
