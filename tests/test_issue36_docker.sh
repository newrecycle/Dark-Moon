#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT/tests/docker-compose.issue-36.yml"
PROJECT="darkmoon-issue36"

command -v docker >/dev/null 2>&1 || {
  echo "SKIP: docker is not installed" >&2
  exit 77
}
docker compose version >/dev/null

ISSUE36_CAPTURE_DIR="$(mktemp -d)"
export ISSUE36_CAPTURE_DIR

cleanup() {
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
  case "$ISSUE36_CAPTURE_DIR" in
    /tmp/tmp.*) rm -rf -- "$ISSUE36_CAPTURE_DIR" ;;
    *) echo "refusing to remove unexpected capture path: $ISSUE36_CAPTURE_DIR" >&2 ;;
  esac
}
trap cleanup EXIT

wait_for_opencode() {
  local attempt
  for attempt in $(seq 1 60); do
    if docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T opencode \
      bash -lc 'test -f /root/.config/opencode/opencode.json && pgrep -x sleep >/dev/null' >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" logs opencode >&2
  return 1
}

docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down -v --remove-orphans
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" build --no-cache opencode
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d
wait_for_opencode

docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T opencode \
  python3 /root/conf/opencode-config.py validate \
  --agents-dir /root/.config/opencode/agents \
  --config-file /root/.config/opencode/opencode.json

test "$(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T opencode pwd | tr -d '\r')" = "/workspace"

agents="$(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T opencode opencode agent list)"
grep -q 'pentest (primary)' <<<"$agents"
grep -q 'aws (subagent)' <<<"$agents"

mcp="$(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T opencode opencode mcp list)"
grep -qi 'darkmoon.*connected' <<<"$mcp"

docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T opencode \
  opencode run --agent pentest --model mock/darkmoon-test-model \
  --title issue-36-before-restart --format json \
  'Call darkmoon_get_session exactly once, then report its session id.'

python3 "$ROOT/tests/assert_issue36_capture.py" "$ISSUE36_CAPTURE_DIR/requests.jsonl"

docker compose -p "$PROJECT" -f "$COMPOSE_FILE" restart opencode
wait_for_opencode

agents_after="$(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T opencode opencode agent list)"
grep -q 'pentest (primary)' <<<"$agents_after"
grep -q 'aws (subagent)' <<<"$agents_after"

docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T opencode \
  opencode run --agent pentest --model mock/darkmoon-test-model \
  --title issue-36-after-restart --format json \
  'Call darkmoon_get_session exactly once, then report its session id.'

python3 "$ROOT/tests/assert_issue36_capture.py" \
  "$ISSUE36_CAPTURE_DIR/requests.jsonl" --minimum-requests 4

logs="$(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" logs opencode)"
if grep -Eqi 'No matching version found for @opencode-ai/plugin|failed to parse YAML frontmatter|unsupported agent field|configuration failed' <<<"$logs"; then
  echo "$logs" >&2
  exit 1
fi

echo "PASS: clean image, generated config, MCP tools, provider request, and restart regression"
