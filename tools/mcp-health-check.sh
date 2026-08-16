#!/usr/bin/env bash
#
# mcp-health-check.sh — fast health probe for the Darkmoon MCP server.
#
# Exit codes:
#   0 = healthy (server up, tools accessible)
#   1 = down (no server / no tools)
#
# Usage:
#   tools/mcp-health-check.sh              # human-readable
#   tools/mcp-health-check.sh --json       # machine-readable JSON
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---human}"

# Spawn the server exactly as opencode does (StdioTransport) and call health_check.
# This is authoritative: proves the server boots AND the toolbox is live.
output="$(cd /opt/darkmoon/mcp/server 2>/dev/null && . .venv/bin/activate 2>/dev/null && python3 -c "
import asyncio, json, sys
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

async def main():
    try:
        t = StdioTransport(command='python3', args=['-m', 'src.server'])
        c = Client(transport=t)
        async with c:
            tools = await c.list_tools()
            r = await c.call_tool('health_check', {})
            healthy = any('Healthy' in str(v) for v in (r if isinstance(r, (list,tuple)) else [r]))
            print(json.dumps({'ok': True, 'tools': len(tools), 'healthy': healthy}))
    except Exception as e:
        print(json.dumps({'ok': False, 'error': str(e)[:200]}))
asyncio.run(main())
" 2>/dev/null)"

if [ -z "$output" ] || ! echo "$output" | grep -q '"ok": true'; then
    if [ "$MODE" = "--json" ]; then echo "${output:-{\"ok\":false,\"error\":\"no output\"}}"; else echo "MCP DOWN: $(echo "$output" | grep -oE '"error":"[^"]*"' | head -1)"; fi
    exit 1
fi

if [ "$MODE" = "--json" ]; then echo "$output"; else echo "MCP HEALTHY ($(echo "$output" | grep -oE '"tools":[0-9]+' | head -1 | cut -d: -f2) tools)"; fi
exit 0
