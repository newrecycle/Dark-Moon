#!/usr/bin/env python3
"""Tiny keyless OpenAI-compatible server for issue #36 regression tests."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from typing import Any


FORBIDDEN_TOP_LEVEL = {"primary", "secondary", "prompt_file", "id", "mcp"}


class CaptureState:
    def __init__(self, capture_file: Path | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self.capture_file = capture_file
        self.lock = threading.Lock()

    def append(self, body: dict[str, Any]) -> None:
        with self.lock:
            self.requests.append(body)
            if self.capture_file:
                self.capture_file.parent.mkdir(parents=True, exist_ok=True)
                with self.capture_file.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(body, separators=(",", ":")) + "\n")


def _chunk(delta: dict[str, Any], finish_reason: str | None = None) -> dict[str, Any]:
    return {
        "id": "chatcmpl-darkmoon-regression",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "darkmoon-test-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _tool_names(body: dict[str, Any]) -> set[str]:
    return {
        tool.get("function", {}).get("name", "")
        for tool in body.get("tools", [])
        if isinstance(tool, dict) and tool.get("type") == "function"
    }


def make_handler(state: CaptureState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "DarkMoonMockOpenAI/1.0"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _json(self, status: int, payload: Any) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path == "/health":
                self._json(200, {"ok": True})
            elif self.path == "/requests":
                with state.lock:
                    self._json(200, state.requests)
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            length = int(self.headers.get("Content-Length", "0"))
            try:
                body = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json(400, {"error": "invalid JSON"})
                return
            if not isinstance(body, dict):
                self._json(400, {"error": "body must be an object"})
                return
            state.append(body)

            leaked = sorted(FORBIDDEN_TOP_LEVEL & set(body))
            if leaked:
                self._json(400, {"error": f"unsupported top-level parameters: {', '.join(leaked)}"})
                return
            if not self.path.endswith("/chat/completions"):
                self._json(404, {"error": "not found"})
                return

            messages = body.get("messages", [])
            has_tool_result = any(message.get("role") == "tool" for message in messages if isinstance(message, dict))
            tool_available = "darkmoon_get_session" in _tool_names(body)
            if not has_tool_result and tool_available:
                chunks = [
                    _chunk(
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_darkmoon_get_session",
                                    "type": "function",
                                    "function": {"name": "darkmoon_get_session", "arguments": "{}"},
                                }
                            ],
                        }
                    ),
                    _chunk({}, "tool_calls"),
                ]
            else:
                chunks = [_chunk({"role": "assistant", "content": "Dark-Moon MCP regression completed."}), _chunk({}, "stop")]

            if body.get("stream") is False:
                if not has_tool_result and tool_available:
                    message = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": chunks[0]["choices"][0]["delta"]["tool_calls"],
                    }
                    reason = "tool_calls"
                else:
                    message = {"role": "assistant", "content": "Dark-Moon MCP regression completed."}
                    reason = "stop"
                self._json(
                    200,
                    {
                        "id": "chatcmpl-darkmoon-regression",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": "darkmoon-test-model",
                        "choices": [{"index": 0, "message": message, "finish_reason": reason}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    },
                )
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            for chunk in chunks:
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000, capture_file: Path | None = None) -> None:
    state = CaptureState(capture_file)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"mock OpenAI-compatible server listening on {host}:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    serve(
        host=os.getenv("MOCK_PROVIDER_HOST", "0.0.0.0"),
        port=int(os.getenv("MOCK_PROVIDER_PORT", "8000")),
        capture_file=Path(os.environ["MOCK_PROVIDER_CAPTURE"]) if os.getenv("MOCK_PROVIDER_CAPTURE") else None,
    )
