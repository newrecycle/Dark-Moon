#!/usr/bin/env python3
"""Run issue #36 through the exact OpenCode source against local mocks."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

from mock_openai_compatible import CaptureState, FORBIDDEN_TOP_LEVEL, make_handler
from http.server import ThreadingHTTPServer


REPO = Path(__file__).resolve().parents[1]


def load_config_tool():
    path = REPO / "conf" / "opencode-config.py"
    spec = importlib.util.spec_from_file_location("darkmoon_opencode_config_integration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opencode-source", type=Path, required=True)
    parser.add_argument("--bun", type=Path, required=True)
    args = parser.parse_args()
    source = args.opencode_source.resolve()
    bun = args.bun.resolve()
    if not (source / "packages" / "opencode" / "src" / "index.ts").is_file():
        parser.error("--opencode-source is not an installed OpenCode checkout")
    if not bun.is_file():
        parser.error("--bun does not exist")

    state = CaptureState()
    provider = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()

    tool = load_config_tool()
    try:
        with tempfile.TemporaryDirectory(prefix="darkmoon-issue36-") as raw:
            root = Path(raw)
            config_dir = root / "config"
            agents_dir = config_dir / "agents"
            shutil.copytree(REPO / "conf" / "agents", agents_dir)
            config_file = config_dir / "opencode.json"
            auth_file = root / "data" / "opencode" / "auth.json"
            workspace = root / "workspace"
            workspace.mkdir()
            mcp_called = root / "mcp-called.log"

            render_env = {
                "OPENCODE_LOCAL_MODE": "true",
                "OPENCODE_LOCAL_PROVIDER_ID": "mock",
                "OPENCODE_LOCAL_PROVIDER_NAME": "Issue 36 mock",
                "OPENCODE_LOCAL_BASE_URL": f"http://127.0.0.1:{provider.server_port}/v1",
                "OPENCODE_LOCAL_MODEL": "darkmoon-test-model",
                "OPENCODE_LOCAL_API_KEY": "not-a-real-key",
            }
            original = os.environ.copy()
            try:
                os.environ.clear()
                os.environ.update(render_env)
                tool.apply_configuration(config_file, auth_file, agents_dir)
            finally:
                os.environ.clear()
                os.environ.update(original)

            config = json.loads(config_file.read_text(encoding="utf-8"))
            config["mcp"]["darkmoon"]["command"] = [str(bun), str(REPO / "tests" / "mock_mcp_server.mjs")]
            config_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

            env = os.environ.copy()
            env.update(
                {
                    "OPENCODE_CONFIG_DIR": str(config_dir),
                    "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
                    "OPENCODE_DISABLE_MODELS_FETCH": "true",
                    "OPENCODE_DISABLE_AUTOUPDATE": "true",
                    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
                    "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
                    "OPENCODE_SOURCE_DIR": str(source),
                    "MOCK_MCP_CALLED_FILE": str(mcp_called),
                    "XDG_CACHE_HOME": str(root / "cache"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                    "XDG_DATA_HOME": str(root / "data"),
                    "XDG_STATE_HOME": str(root / "state"),
                }
            )
            cli = [str(bun), str(source / "packages" / "opencode" / "src" / "index.ts")]

            agent_list = run(cli + ["agent", "list"], cwd=workspace, env=env).stdout
            assert "pentest (primary)" in agent_list, agent_list
            assert "aws (subagent)" in agent_list, agent_list
            mcp_list = run(cli + ["mcp", "list"], cwd=workspace, env=env).stdout
            assert "darkmoon" in mcp_list and "connected" in mcp_list.lower(), mcp_list
            assert mcp_called.is_file() and "list_tools" in mcp_called.read_text(encoding="utf-8"), (
                mcp_list,
                mcp_called.read_text(encoding="utf-8") if mcp_called.exists() else "no MCP trace",
            )

            # The debug JSON is intentionally very large because it includes the
            # full prompt; inspect only its stable prefix for normalized options.
            # MCP tools are attached later by SessionTools, so the debug-agent
            # command itself does not enumerate them; the captured model request
            # and returned tool call below exercise that real path.
            pentest_debug = run(cli + ["debug", "agent", "pentest"], cwd=workspace, env=env).stdout
            assert '"mode": "primary"' in pentest_debug[:1000]
            assert '"options": {}' in pentest_debug[:5000]

            specialist_debug = run(cli + ["debug", "agent", "aws"], cwd=workspace, env=env).stdout
            assert '"mode": "subagent"' in specialist_debug[:1000]
            assert '"options": {}' in specialist_debug[:5000]

            result = run(
                cli
                + [
                    "run",
                    "--agent",
                    "pentest",
                    "--model",
                    "mock/darkmoon-test-model",
                    "--title",
                    "issue-36-regression",
                    "--format",
                    "json",
                    "Call darkmoon_get_session exactly once, then report its session id.",
                ],
                cwd=workspace,
                env=env,
            )
            assert "Dark-Moon MCP regression completed" in result.stdout, result.stdout
            assert mcp_called.is_file() and "darkmoon_get_session" in mcp_called.read_text(encoding="utf-8")

            with state.lock:
                requests = list(state.requests)
            assert len(requests) >= 2, requests
            for index, body in enumerate(requests):
                leaked = FORBIDDEN_TOP_LEVEL & set(body)
                assert not leaked, f"request {index} leaked metadata: {sorted(leaked)}"
            assert any("darkmoon_get_session" in {t.get("function", {}).get("name") for t in body.get("tools", [])} for body in requests)
            request_tools = {
                tool.get("function", {}).get("name")
                for body in requests
                for tool in body.get("tools", [])
            }
            assert "task" in request_tools
            assert "bash" not in request_tools and "read" not in request_tools
            assert any(any(message.get("role") == "tool" for message in body.get("messages", [])) for body in requests)
            print(f"PASS: exact OpenCode source captured {len(requests)} clean requests and executed darkmoon_get_session")
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
