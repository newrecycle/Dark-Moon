#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ROOT="${PLUGIN_ROOT:?Hermes did not provide PLUGIN_ROOT}"
HERMES_BIN="$(command -v hermes || true)"

if [ -n "$HERMES_BIN" ]; then
    HERMES_REAL="$(readlink -f "$HERMES_BIN" 2>/dev/null || realpath "$HERMES_BIN" 2>/dev/null || echo "$HERMES_BIN")"
    HERMES_PYTHON="$(dirname "$HERMES_REAL")/python"
    if [ -x "$HERMES_PYTHON" ]; then
        "$HERMES_PYTHON" "${PLUGIN_ROOT}/hermes_registration.py" \
            --plugin-root "${PLUGIN_ROOT}" --quiet || \
            echo "Warning: DarkMoon could not register its Hermes slash skills." >&2
        exec "$HERMES_PYTHON" "${PLUGIN_ROOT}/session_server.py"
    fi
fi

if python3 -c 'from mcp.server.fastmcp import FastMCP' >/dev/null 2>&1; then
    python3 "${PLUGIN_ROOT}/hermes_registration.py" \
        --plugin-root "${PLUGIN_ROOT}" --quiet || \
        echo "Warning: DarkMoon could not register its Hermes slash skills." >&2
    exec python3 "${PLUGIN_ROOT}/session_server.py"
fi

echo "DarkMoon session launcher could not locate the Hermes Python runtime." >&2
exit 1
