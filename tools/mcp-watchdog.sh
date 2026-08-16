#!/usr/bin/env bash
#
# mcp-watchdog.sh — monitor the Darkmoon MCP server and recover it.
#
# Modes:
#   --once               single probe, exit 0 (healthy) or 1 (down)
#   --loop               detect-only: write status/incident files forever
#   --restart-container  loop + restart the opencode container on persistent failure
#
# --restart-container is the recommended mode for the container. The watchdog
# runs inside the opencode container, probes the MCP server, and if the server
# stays down for THRESHOLD consecutive checks (after an initial WARMUP period),
# it runs `docker restart <container>`. The container has the Docker CLI and
# socket mounted, so it can restart itself. The watchdog dies with the container
# and is re-launched fresh by the entrypoint on boot — the WARMUP on the new
# instance prevents a restart loop.
#
# Environment (all optional):
#   DARKMOON_MCP_STATE_DIR        status dir (default /run/darkmoon-mcp)
#   DARKMOON_MCP_WATCHDOG_INTERVAL    probe interval seconds (default 15)
#   DARKMOON_MCP_RESTART_THRESHOLD    consecutive failures before restart (default 3)
#   DARKMOON_MCP_RESTART_WARMUP       seconds after watchdog start before a
#                                     restart is allowed (default 30)
#   DARKMOON_MCP_CONTAINER_NAME       container to restart (default opencode)
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROBE="$HERE/mcp-health-check.sh"
STATE_DIR="${DARKMOON_MCP_STATE_DIR:-/run/darkmoon-mcp}"
INTERVAL="${DARKMOON_MCP_WATCHDOG_INTERVAL:-15}"
THRESHOLD="${DARKMOON_MCP_RESTART_THRESHOLD:-3}"
WARMUP="${DARKMOON_MCP_RESTART_WARMUP:-30}"
CONTAINER="${DARKMOON_MCP_CONTAINER_NAME:-opencode}"
MODE="${1:---once}"

mkdir -p "$STATE_DIR"
incident_file="$STATE_DIR/incident.json"
status_file="$STATE_DIR/status.json"

probe() {
  if bash "$PROBE" >/dev/null 2>&1; then
    printf '{"ts":%d,"status":"healthy","consecutive_failures":0}\n' "$(date +%s)" > "$status_file"
    rm -f "$incident_file"
    return 0
  fi
  return 1
}

handle_failure() {
  local count
  count="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('consecutive_failures',0)+1)" "$status_file" 2>/dev/null || echo 1)"
  printf '{"ts":%d,"status":"down","consecutive_failures":%s}\n' "$(date +%s)" "$count" > "$status_file"
  if [ "$count" -eq 1 ] || [ "$((count % 5))" -eq 0 ]; then
    printf '{"since":%d,"consecutive_failures":%s,"detail":"MCP server not responding to health probe"}\n' "$(date +%s)" "$count" > "$incident_file"
    echo "[mcp-watchdog] MCP DOWN (failure #$count at $(date -Is))" >&2
  fi
}

# State for --restart-container
consecutive=0
watchdog_start=0

case "$MODE" in
  --restart-container)
    watchdog_start="$(date +%s)"
    echo "[mcp-watchdog] container-restart mode (interval=${INTERVAL}s threshold=${THRESHOLD} warmup=${WARMUP}s container=${CONTAINER})"
    while true; do
      now="$(date +%s)"
      uptime=$((now - watchdog_start))
      if probe; then
        consecutive=0
      else
        consecutive=$((consecutive + 1))
        if [ "$uptime" -ge "$WARMUP" ] && [ "$consecutive" -ge "$THRESHOLD" ]; then
          printf '{"since":%d,"consecutive_failures":%s,"action":"restart","container":"%s","ts":%d}\n' \
            "$watchdog_start" "$consecutive" "$CONTAINER" "$now" > "$incident_file"
          echo "[mcp-watchdog] MCP DOWN for ${consecutive} consecutive checks — restarting ${CONTAINER}" >&2
          # docker restart blocks until the container stops; we die with it and
          # are reborn via the entrypoint. If it returns an error we keep monitoring.
          if docker restart -t 30 "$CONTAINER" >/dev/null 2>&1; then
            echo "[mcp-watchdog] restart issued" >&2
          else
            echo "[mcp-watchdog] docker restart failed — will retry on next check" >&2
          fi
          # Reset so a failed restart does not immediately re-trigger.
          consecutive=0
        fi
      fi
      sleep "$INTERVAL"
    done
    ;;
  --loop)
    echo "[mcp-watchdog] detect-only loop (interval=${INTERVAL}s)"
    while true; do
      probe || handle_failure
      sleep "$INTERVAL"
    done
    ;;
  *)
    if probe; then
      exit 0
    else
      handle_failure
      exit 1
    fi
    ;;
esac
