"""Privacy-gateway coverage for structured browser workflow calls."""

from __future__ import annotations

import json
import os
import sys

os.environ["DARKMOON_EXEC_MODE"] = "local"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import server  # noqa: E402


class StubRegistry:
    def __init__(self):
        self.calls = []

    def run_workflow(self, workflow, method, params):
        self.calls.append((workflow, method, params))
        return {
            "workflow": workflow,
            "ok": True,
            "target": params.get("url"),
            "pages": [{"url": params.get("url"), "text": "host 10.42.1.5"}],
        }


def _install_stub(monkeypatch):
    stub = StubRegistry()
    monkeypatch.setattr(server, "workflow_registry", stub)
    monkeypatch.setattr(server, "PRIVACY_ENABLED", True)
    server._vaults.clear()
    return stub


def test_browser_target_placeholder_rehydrates_and_output_retokens(monkeypatch):
    stub = _install_stub(monkeypatch)
    session_id = "browser-privacy"
    vault = server._get_vault(session_id)
    placeholder = vault.tokenize("10.42.1.5")

    result = server.run_workflow(
        "headless_browser",
        "analyze",
        {"url": f"http://{placeholder}/app?mode=test", "mode": "snapshot"},
        session_id=session_id,
    )

    executed_url = stub.calls[0][2]["url"]
    assert executed_url == "http://10.42.1.5/app?mode=test"
    serialized = json.dumps(result)
    assert "10.42.1.5" not in serialized
    assert placeholder in serialized


def test_browser_placeholder_in_query_is_blocked(monkeypatch):
    stub = _install_stub(monkeypatch)
    session_id = "browser-query-block"
    vault = server._get_vault(session_id)
    placeholder = vault.tokenize("10.42.1.5")

    result = server.run_workflow(
        "headless_browser",
        "analyze",
        {"url": f"https://public.example.test/?target={placeholder}"},
        session_id=session_id,
    )

    assert result["error"]["code"] == "privacy_block"
    assert stub.calls == []


def test_browser_placeholder_in_non_url_field_is_blocked(monkeypatch):
    stub = _install_stub(monkeypatch)
    session_id = "browser-field-block"
    vault = server._get_vault(session_id)
    placeholder = vault.tokenize("10.42.1.5")

    result = server.run_workflow(
        "headless_browser",
        "analyze",
        {"url": "https://public.example.test/", "mode": placeholder},
        session_id=session_id,
    )

    assert result["error"]["code"] == "privacy_block"
    assert stub.calls == []
