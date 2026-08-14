"""Host-side MCP facade for explicit DarkMoon pentest session launches."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import FastMCP

from session_launcher import (
    PentestSessionError,
    consume_capability_token,
    darkmoon_mcp_url,
    prepare_pentest_profile,
    run_pentest_turn,
    validate_session_id,
)


mcp = FastMCP("DarkMoon Pentest Session Launcher")
EXPLICIT_INVOCATION = "/darkmoon-pentest"


def _structured_result(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", ()) or ():
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return decoded
    return {}


async def _fetch_pentest_persona() -> str:
    try:
        async with streamablehttp_client(
            darkmoon_mcp_url(),
            timeout=30,
            sse_read_timeout=60,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_agent",
                    {"name": "pentest"},
                    read_timeout_seconds=timedelta(seconds=30),
                )
    except Exception as exc:
        raise PentestSessionError(
            "DarkMoon MCP is unavailable; start the plugin-owned darkmoon-plugin backend first."
        ) from exc

    payload = _structured_result(result)
    persona = payload.get("markdown")
    if payload.get("found") is not True or not isinstance(persona, str) or not persona.strip():
        raise PentestSessionError("DarkMoon MCP did not return the pentest identity.")
    return persona


def _require_explicit_skill(value: str) -> None:
    if str(value or "").strip() != EXPLICIT_INVOCATION:
        raise PentestSessionError(
            "A pentest session may be created only by an explicit /darkmoon-pentest invocation."
        )


def _require_capability(token: str | None) -> None:
    # The capability token is the trusted proof that the user (via the slash
    # dispatcher, outside the model's context) authorized this session. The
    # model cannot forge a valid token, so a forged invocation string alone is
    # never enough to create a session.
    if not consume_capability_token(token):
        raise PentestSessionError(
            "The explicit /darkmoon-pentest authorization was missing or invalid."
        )


def _error(exc: Exception) -> dict[str, Any]:
    return {"ok": False, "error": str(exc)}


@mcp.tool()
async def start_pentest_session(
    task: str,
    skill_invocation: str,
    capability_token: str,
    working_directory: str | None = None,
) -> dict[str, Any]:
    """Create a separate isolated Hermes pentest session after an explicit invocation.

    This never changes the invoking agent. It requires both the explicit
    `/darkmoon-pentest` invocation string and a one-use capability token minted
    by the trusted slash dispatcher. A forged invocation string is never enough.
    """

    try:
        _require_explicit_skill(skill_invocation)
        _require_capability(capability_token)
        persona = await _fetch_pentest_persona()
        profile = await asyncio.to_thread(prepare_pentest_profile, persona)
        result = await asyncio.to_thread(
            run_pentest_turn,
            task,
            working_directory=working_directory,
            capability_token=capability_token,
        )
        result["identity"] = profile["identity"]
        return result
    except Exception as exc:
        return _error(exc)


@mcp.tool()
async def resume_pentest_session(
    session_id: str,
    message: str,
    skill_invocation: str,
    capability_token: str,
    working_directory: str | None = None,
) -> dict[str, Any]:
    """Resume an isolated DarkMoon pentest session after an explicit invocation."""

    try:
        _require_explicit_skill(skill_invocation)
        _require_capability(capability_token)
        validated_id = validate_session_id(session_id)
        persona = await _fetch_pentest_persona()
        profile = await asyncio.to_thread(prepare_pentest_profile, persona)
        result = await asyncio.to_thread(
            run_pentest_turn,
            message,
            working_directory=working_directory,
            session_id=validated_id,
            capability_token=capability_token,
        )
        result["identity"] = profile["identity"]
        return result
    except Exception as exc:
        return _error(exc)


if __name__ == "__main__":
    mcp.run(transport="stdio")
