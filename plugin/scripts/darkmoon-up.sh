#!/usr/bin/env bash
#
# darkmoon-up.sh — idempotent bring-up of the Dark-Moon Docker backend.
#
# Selects the correct compose file for the host architecture, requires a prior
# ./install.sh run (writes .opencode.env), brings the stack up, and waits for
# readiness through the protocol-level health check inside the plugin-owned
# container. This cannot mistake an unrelated service on the same host port for
# the Dark-Moon plugin backend.
set -euo pipefail

# Resolve repository root from this script's location:
#   plugin/scripts/<this>  ->  .. = plugin  ->  ../.. = repo root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO"

# Select compose file by host architecture. DO NOT swap the two:
#   x86_64        -> docker-compose.yml (prebuilt image)
#   aarch64/arm64 -> docker-compose-dev.yml (local build)
case "$(uname -m)" in
    aarch64|arm64) CF="docker-compose-dev.yml" ;;
    *) CF="docker-compose.yml" ;;
esac

# First run requires ./install.sh (writes .opencode.env, chmod 600).
if [ ! -f "${REPO}/.opencode.env" ]; then
    echo "Error: .opencode.env not found in ${REPO}." >&2
    echo "Run ./install.sh once from the repo root before starting the backend:" >&2
    echo "    cd ${REPO} && ./install.sh" >&2
    exit 1
fi

# MCP port (matches DARKMOON_MCP_PORT; default 8000, path /mcp).
PORT="${DARKMOON_MCP_PORT:-8000}"

# Bring up the Docker stack (idempotent: re-running is safe).
COMPOSE=(docker compose -f "$CF")
"${COMPOSE[@]}" up -d

# Wait for this container's MCP process and protocol registry, not merely any
# listener on the host-network port.
READY=0
for _ in $(seq 1 60); do
    if "${COMPOSE[@]}" exec -T darkmoon sh -c \
        'cd /opt/darkmoon/mcp/server && python -m src.healthcheck' \
        >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 2
done

if [ "$READY" != "1" ]; then
    echo "Error: darkmoon-plugin MCP did not become ready on port ${PORT}." >&2
    exit 1
fi

echo "Dark-Moon MCP ready at http://localhost:${PORT}/mcp"
