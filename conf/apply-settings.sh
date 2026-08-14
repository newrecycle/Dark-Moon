#!/usr/bin/env bash
set -euo pipefail

OPENCODE_CONFIG_DIR="${OPENCODE_CONFIG_DIR:-/root/.config/opencode}"
DARKMOON_CONFIG_FILE="${DARKMOON_CONFIG_FILE:-$OPENCODE_CONFIG_DIR/darkmoon.json}"
OPENCODE_AUTH_DIR="${OPENCODE_AUTH_DIR:-/root/.local/share/opencode}"
OPENCODE_AUTH_FILE="${OPENCODE_AUTH_FILE:-$OPENCODE_AUTH_DIR/auth.json}"
OPENCODE_AGENTS_DIR="${OPENCODE_AGENTS_DIR:-/root/.config/opencode/agents}"
OPENCODE_DEFAULT_AGENTS_DIR="${OPENCODE_DEFAULT_AGENTS_DIR:-/opt/darkmoon/default-agents}"
OPENCODE_CONFIG_TOOL="${OPENCODE_CONFIG_TOOL:-/root/conf/opencode-config.py}"

fail() { printf 'opencode config: %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || fail "python3 is required"
[ -f "$OPENCODE_CONFIG_TOOL" ] || fail "normalizer missing: $OPENCODE_CONFIG_TOOL"

mkdir -p "$OPENCODE_CONFIG_DIR" "$OPENCODE_AUTH_DIR" "$OPENCODE_AGENTS_DIR"

exec python3 "$OPENCODE_CONFIG_TOOL" apply \
  --agents-dir "$OPENCODE_AGENTS_DIR" \
  --canonical-agents-dir "$OPENCODE_DEFAULT_AGENTS_DIR" \
  --config-file "$DARKMOON_CONFIG_FILE" \
  --auth-file "$OPENCODE_AUTH_FILE"
