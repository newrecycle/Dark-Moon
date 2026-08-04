#!/usr/bin/env python3
"""Run the Dark-Moon MCP server over Streamable HTTP for OpenCode."""

from __future__ import annotations

import os

from src.server import mcp


def main() -> None:
    mcp.run(
        transport="http",
        host=os.getenv("DARKMOON_MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("DARKMOON_MCP_PORT", "8000")),
        path=os.getenv("DARKMOON_MCP_PATH", "/mcp"),
    )


if __name__ == "__main__":
    main()
