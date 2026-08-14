#!/usr/bin/env python3
"""Protocol-level readiness check for the Dark-Moon Streamable HTTP MCP server."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastmcp import Client


def verify_local_server_process() -> None:
    """Prove the MCP process belongs to this container before probing its port."""

    if os.getenv("DARKMOON_MCP_AUTOSTART", "0") != "1":
        return
    pid_file = Path(
        os.getenv("DARKMOON_MCP_PID_FILE", "/run/darkmoon-mcp.pid")
    )
    try:
        pid = int(pid_file.read_text(encoding="ascii").strip())
        os.kill(pid, 0)
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
    except (OSError, ValueError) as exc:
        raise RuntimeError("this container's MCP process is not running") from exc
    if b"src.http_server" not in command:
        raise RuntimeError("MCP PID file does not identify this container's server")


async def check() -> None:
    verify_local_server_process()
    host = os.getenv("DARKMOON_MCP_HEALTH_HOST", "127.0.0.1")
    port = int(os.getenv("DARKMOON_MCP_PORT", "8000"))
    path = os.getenv("DARKMOON_MCP_PATH", "/mcp")
    url = f"http://{host}:{port}{path}"
    client = Client(url)
    async with client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    required = {
        "get_session",
        "health_check",
        "execute_command",
        "list_workflows",
        "run_workflow",
    }
    missing = sorted(required - names)
    if missing:
        raise RuntimeError(f"MCP tool registry is incomplete: {', '.join(missing)}")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(check(), timeout=8))
