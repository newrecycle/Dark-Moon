#!/usr/bin/env python3
"""Initialize stock OpenCode for Dark-Moon without modifying the OpenCode image."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import urlparse

TOOL_PATH = Path(os.getenv("OPENCODE_CONFIG_TOOL", "/opt/darkmoon/opencode-config.py"))
CONFIG_DIR = Path(os.getenv("OPENCODE_CONFIG_DIR", "/root/.config/opencode"))
CONFIG_FILE = Path(os.getenv("OPENCODE_CONFIG_FILE", str(CONFIG_DIR / "opencode.json")))
DATA_DIR = Path(os.getenv("OPENCODE_DATA_DIR", "/root/.local/share/opencode"))
AUTH_FILE = Path(os.getenv("OPENCODE_AUTH_FILE", str(DATA_DIR / "auth.json")))
AGENTS_DIR = Path(os.getenv("OPENCODE_AGENTS_DIR", str(CONFIG_DIR / "agents")))
CANONICAL_AGENTS_DIR = Path(os.getenv("OPENCODE_DEFAULT_AGENTS_DIR", "/opt/darkmoon/default-agents"))
WORKFLOWS_DIR = Path(os.getenv("DARKMOON_WORKFLOWS_DIR", "/var/lib/darkmoon/workflows"))
CANONICAL_WORKFLOWS_DIR = Path(os.getenv("DARKMOON_DEFAULT_WORKFLOWS_DIR", "/opt/darkmoon/default-workflows"))
STATE_FILE = CONFIG_DIR / ".darkmoon-bootstrap.json"


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"darkmoon-bootstrap: {message}")


def load_config_tool():
    if not TOOL_PATH.is_file():
        fail(f"configuration normalizer is missing: {TOOL_PATH}")
    spec = importlib.util.spec_from_file_location("darkmoon_opencode_config", TOOL_PATH)
    if spec is None or spec.loader is None:
        fail(f"cannot import configuration normalizer: {TOOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_agents() -> bool:
    if not CANONICAL_AGENTS_DIR.is_dir():
        fail(f"canonical agents directory is missing: {CANONICAL_AGENTS_DIR}")
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    if any(AGENTS_DIR.iterdir()):
        return False
    shutil.copytree(CANONICAL_AGENTS_DIR, AGENTS_DIR, dirs_exist_ok=True)
    return True


def seed_workflows() -> bool:
    if not CANONICAL_WORKFLOWS_DIR.is_dir():
        fail(f"canonical workflows directory is missing: {CANONICAL_WORKFLOWS_DIR}")
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    if any(WORKFLOWS_DIR.iterdir()):
        return False
    shutil.copytree(CANONICAL_WORKFLOWS_DIR, WORKFLOWS_DIR, dirs_exist_ok=True)
    return True


def mcp_config() -> dict[str, object]:
    transport = os.getenv("DARKMOON_MCP_TRANSPORT", "remote").strip().lower()
    timeout = int(os.getenv("DARKMOON_MCP_TIMEOUT_MS", "36000000"))
    if timeout <= 0:
        fail("DARKMOON_MCP_TIMEOUT_MS must be positive")

    if transport == "remote":
        url = os.getenv("DARKMOON_MCP_URL", "http://darkmoon-mcp:8000/mcp").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            fail(f"invalid DARKMOON_MCP_URL: {url!r}")
        return {
            "type": "remote",
            "url": url,
            "oauth": False,
            "timeout": timeout,
            "enabled": True,
        }

    if transport == "local":
        raw = os.getenv("DARKMOON_MCP_COMMAND", '["/usr/local/bin/darkmoon-mcp"]')
        try:
            command = json.loads(raw)
        except json.JSONDecodeError as exc:
            fail(f"DARKMOON_MCP_COMMAND must be a JSON array: {exc}")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            fail("DARKMOON_MCP_COMMAND must be a non-empty JSON string array")
        return {
            "type": "local",
            "command": command,
            "timeout": timeout,
            "enabled": True,
        }

    fail(f"unsupported DARKMOON_MCP_TRANSPORT: {transport!r}")


def validate_runtime_config(tool, config: dict[str, object]) -> None:
    leaked = tool._walk_forbidden(config)
    if leaked:
        fail(f"legacy metadata remains at: {', '.join(leaked)}")
    if config.get("default_agent") != "pentest":
        fail("default_agent must be pentest")
    if config.get("subagent_depth") != 1:
        fail("subagent_depth must be 1")

    mcp = config.get("mcp")
    if not isinstance(mcp, dict) or not isinstance(mcp.get("darkmoon"), dict):
        fail("global darkmoon MCP configuration is missing")
    darkmoon = mcp["darkmoon"]
    if darkmoon.get("enabled") is not True:
        fail("global darkmoon MCP configuration is disabled")
    if darkmoon.get("type") == "remote":
        url = darkmoon.get("url")
        if not isinstance(url, str) or urlparse(url).scheme not in {"http", "https"}:
            fail("remote darkmoon MCP URL is invalid")
    elif darkmoon.get("type") == "local":
        command = darkmoon.get("command")
        if not isinstance(command, list) or not command:
            fail("local darkmoon MCP command is invalid")
    else:
        fail("darkmoon MCP transport must be remote or local")

    model = config.get("model")
    if not isinstance(model, str) or "/" not in model:
        fail("model was not rendered from provider settings")
    tool.validate_agents(AGENTS_DIR)


def main() -> int:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    agents_seeded = seed_agents()
    workflows_seeded = seed_workflows()
    tool = load_config_tool()

    tool.migrate_agents(AGENTS_DIR)
    tool.migrate_required_prompt_sections(AGENTS_DIR, CANONICAL_AGENTS_DIR)
    tool.validate_agents(AGENTS_DIR)
    strategy = tool.render_config(CONFIG_FILE, AUTH_FILE)

    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    config["default_agent"] = "pentest"
    config["subagent_depth"] = 1
    config["mcp"] = {"darkmoon": mcp_config()}
    tool._atomic_json(CONFIG_FILE, config, mode=0o600)
    if AUTH_FILE.exists():
        AUTH_FILE.chmod(0o600)
    validate_runtime_config(tool, config)

    state = {
        "schema": 1,
        "opencode": "1.18.12",
        "strategy": strategy,
        "model": config["model"],
        "mcp_transport": config["mcp"]["darkmoon"]["type"],
        "agents_seeded": agents_seeded,
        "agents": len(list(AGENTS_DIR.glob("*.md"))),
        "workflows_seeded": workflows_seeded,
        "workflows": len(list(WORKFLOWS_DIR.glob("*.py"))),
    }
    tool._atomic_json(STATE_FILE, state, mode=0o600)
    print(
        f"[darkmoon-bootstrap] {strategy}; {state['agents']} agents; "
        f"{state['workflows']} workflows; MCP={state['mcp_transport']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
