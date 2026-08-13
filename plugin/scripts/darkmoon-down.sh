#!/usr/bin/env bash
#
# darkmoon-down.sh — stop the Dark-Moon Docker backend.
#
# Selects the correct compose file for the host architecture and tears the
# stack down. Mirror of darkmoon-up.sh (same shebang / set / path resolution).
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

# Tear down the Docker stack.
docker compose -f "$CF" down

echo "Dark-Moon backend stopped."
