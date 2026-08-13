#!/usr/bin/env bash
#
# darkmoon-up.sh — idempotent bring-up of the Dark-Moon Docker backend.
#
# Selects the correct compose file for the host architecture, requires a prior
# ./install.sh run (writes .opencode.env), brings the stack up, and waits for
# readiness by TCP-probing the MCP port. There is NO /health HTTP route, so we
# probe http://localhost:${PORT}/mcp and accept ANY HTTP response as "up".
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
docker compose -f "$CF" up -d

# Wait for readiness by TCP-probing the MCP port (NOT /health).
# curl returns 0 for any HTTP response; a 4xx/406 from /mcp still proves the
# server is listening.
for _ in $(seq 1 30); do
    if curl -s -o /dev/null --max-time 2 "http://localhost:${PORT}/mcp"; then
        break
    fi
    sleep 2
done

echo "Dark-Moon MCP ready at http://localhost:${PORT}/mcp"
