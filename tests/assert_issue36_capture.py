#!/usr/bin/env python3
"""Assert that mock-provider captures are clean and include an MCP round trip."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FORBIDDEN = {"primary", "secondary", "prompt_file", "id", "name", "mcp", "maxSteps"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--minimum-requests", type=int, default=2)
    args = parser.parse_args()
    requests = [json.loads(line) for line in args.capture.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(requests) >= args.minimum_requests, f"expected >= {args.minimum_requests} requests, got {len(requests)}"
    for index, body in enumerate(requests):
        leaked = FORBIDDEN & set(body)
        assert not leaked, f"request {index} leaked top-level fields: {sorted(leaked)}"
    tools = {
        tool.get("function", {}).get("name")
        for body in requests
        for tool in body.get("tools", [])
        if isinstance(tool, dict)
    }
    assert "darkmoon_get_session" in tools, "Dark-Moon MCP tool was not exposed to the model"
    assert "task" in tools, "pentest lost subagent task access"
    assert "bash" not in tools and "read" not in tools, "pentest received broader local tool access than intended"
    assert any(
        any(message.get("role") == "tool" for message in body.get("messages", []) if isinstance(message, dict))
        for body in requests
    ), "no provider request contained the executed MCP tool result"
    print(f"PASS: {len(requests)} captured requests are clean and include the Dark-Moon MCP round trip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
