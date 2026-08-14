#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_BIN="$(command -v hermes || true)"

if [ -n "$HERMES_BIN" ]; then
    HERMES_REAL="$(readlink -f "$HERMES_BIN" 2>/dev/null || realpath "$HERMES_BIN" 2>/dev/null || echo "$HERMES_BIN")"
    HERMES_PYTHON="$(dirname "$HERMES_REAL")/python"
    if [ -x "$HERMES_PYTHON" ]; then
        exec "$HERMES_PYTHON" "${PLUGIN_ROOT}/hermes_registration.py" \
            --plugin-root "${PLUGIN_ROOT}" "$@"
    fi
fi

if python3 -c 'import yaml' >/dev/null 2>&1; then
    exec python3 "${PLUGIN_ROOT}/hermes_registration.py" \
        --plugin-root "${PLUGIN_ROOT}" "$@"
fi

echo "DarkMoon could not locate a Hermes Python runtime with PyYAML." >&2
exit 1
