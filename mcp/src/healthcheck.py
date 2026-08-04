#!/usr/bin/env python3
"""Protocol-level readiness check for the Dark-Moon Streamable HTTP MCP server."""

from __future__ import annotations

import asyncio
import os

from fastmcp import Client


async def check() -> None:
    host = os.getenv("DARKMOON_MCP_HEALTH_HOST", "127.0.0.1")
    port = int(os.getenv("DARKMOON_MCP_PORT", "8000"))
    path = os.getenv("DARKMOON_MCP_PATH", "/mcp")
    url = f"http://{host}:{port}{path}"
    client = Client(url)
    async with client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    required = {"get_session", "health_check", "execute_command", "list_workflows"}
    missing = sorted(required - names)
    if missing:
        raise RuntimeError(f"MCP tool registry is incomplete: {', '.join(missing)}")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(check(), timeout=8))
