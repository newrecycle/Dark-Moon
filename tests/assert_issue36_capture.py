#!/usr/bin/env python3
"""Assert mock-provider captures are sanitized and preserve valid generation settings."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

FORBIDDEN = {"primary", "secondary", "prompt_file", "id", "name", "mcp", "maxSteps"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--minimum-requests", type=int, default=2)
    parser.add_argument("--expect-model")
    parser.add_argument("--expect-temperature", type=float)
    parser.add_argument("--expect-top-p", type=float)
    parser.add_argument("--expect-reasoning-effort")
    args = parser.parse_args()

    requests = [json.loads(line) for line in args.capture.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(requests) >= args.minimum_requests, f"expected >= {args.minimum_requests} requests, got {len(requests)}"
    for index, body in enumerate(requests):
        leaked = FORBIDDEN & set(body)
        assert not leaked, f"request {index} leaked top-level fields: {sorted(leaked)}"
        if args.expect_model:
            assert body.get("model") == args.expect_model, (index, body.get("model"))
        if args.expect_temperature is not None:
            assert math.isclose(float(body.get("temperature")), args.expect_temperature), (index, body.get("temperature"))
        if args.expect_top_p is not None:
            assert math.isclose(float(body.get("top_p")), args.expect_top_p), (index, body.get("top_p"))
        if args.expect_reasoning_effort:
            assert body.get("reasoning_effort") == args.expect_reasoning_effort, (index, body.get("reasoning_effort"))

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
    print(f"PASS: {len(requests)} clean requests preserve expected generation parameters and include the MCP round trip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
