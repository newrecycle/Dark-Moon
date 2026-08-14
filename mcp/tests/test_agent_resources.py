"""Tests for the agent-persona MCP tools/resources (darkmoon_list_agents / darkmoon_read_agent)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.server import list_agents, read_agent, agent_persona  # noqa: E402


def test_list_agents_returns_pentest_and_specialists():
    result = list_agents()
    assert result["count"] >= 50
    assert "pentest" in result["agents"]
    # A known specialist should be present.
    assert any(name in result["agents"] for name in ("aws", "azure", "kubernetes"))


def test_read_agent_pentest_returns_markdown():
    result = read_agent("pentest")
    assert result["found"] is True
    assert "<role>" in result["markdown"]
    assert "Strategic pentest Assessment Orchestrator" in result["markdown"]


def test_read_agent_unknown_reports_available():
    result = read_agent("does-not-exist-xyz")
    assert result["found"] is False
    assert isinstance(result["available"], list) and result["available"]


def test_agent_resource_resolves_pentest():
    body = agent_persona("pentest")
    assert "Strategic pentest Assessment Orchestrator" in body
