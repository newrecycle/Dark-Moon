#!/usr/bin/env python3
"""Render and validate Dark-Moon's OpenCode configuration.

OpenCode 1.17.13 intentionally moves unknown agent keys into provider options.
This module keeps legacy Dark-Moon metadata out of that escape hatch, migrates
persisted agent volumes, and validates the Markdown agents before OpenCode starts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

try:
    import yaml
    from yaml.constructor import ConstructorError
    from yaml.resolver import BaseResolver
except ImportError as exc:  # pragma: no cover - exercised by the container build
    raise SystemExit("PyYAML is required (Debian package: python3-yaml)") from exc


SUPPORTED_AGENT_FIELDS = {
    "model",
    "variant",
    "temperature",
    "top_p",
    "description",
    "mode",
    "hidden",
    "options",
    "color",
    "steps",
    "permission",
    "disable",
}
LEGACY_AGENT_FIELDS = {
    "id",
    "name",
    "primary",
    "secondary",
    "prompt_file",
    "mcp",
    "tools",
    "maxSteps",
}
REQUEST_LEAK_FIELDS = {"primary", "secondary", "prompt_file", "id", "mcp"}
VALID_MODES = {"primary", "subagent"}
NAME_ALIASES = {
    "ad": "active-directory",
    "flask": "python-flask",
    "nodejs-express-angular": "nodejs",
    "ruby": "ruby-on-rails",
}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FILE_REFERENCE = re.compile(r"\{file:([^}]+)\}")


class ConfigError(ValueError):
    pass


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError("while constructing a mapping", node.start_mark, "unhashable mapping key", key_node.start_mark) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def _yaml_object(raw: str) -> Any:
    return yaml.load(raw, Loader=_UniqueKeyLoader)


def _scalar(value: str) -> Any:
    """Parse a legacy one-line YAML scalar without parsing malformed prompt text."""
    try:
        return yaml.safe_load(value)
    except yaml.YAMLError:
        return value


def _legacy_frontmatter(lines: list[str]) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {}
    prompt_prefix: list[str] = []
    simple_keys = SUPPORTED_AGENT_FIELDS | LEGACY_AGENT_FIELDS
    for line in lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if match and match.group(1) in simple_keys:
            key, raw = match.groups()
            if key in data:
                raise ConfigError(f"duplicate frontmatter key: {key}")
            if key in {"id", "name", "description"}:
                parsed = _scalar(raw)
                data[key] = parsed if isinstance(parsed, str) else raw.strip()
            else:
                data[key] = _scalar(raw)
        else:
            prompt_prefix.append(line)
    return data, prompt_prefix


def _sanitize_legacy_yaml(lines: list[str]) -> str:
    """Mirror OpenCode's permissive retry for unquoted colons in scalar values."""
    sanitized: list[str] = []
    for line in lines:
        if not line or line.lstrip().startswith("#") or line[0].isspace():
            sanitized.append(line)
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if not match:
            sanitized.append(line)
            continue
        key, value = match.groups()
        value = value.strip()
        if ":" not in value or not value or value in {">", "|"} or value.startswith(("'", '"')):
            sanitized.append(line)
            continue
        sanitized.extend((f"{key}: |-", f"  {value}"))
    return "\n".join(sanitized)


def read_agent(path: Path, *, allow_legacy: bool) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[0] == "---":
        try:
            end = lines.index("---", 1)
        except ValueError as exc:
            raise ConfigError(f"{path}: missing closing YAML frontmatter fence") from exc
        raw = "\n".join(lines[1:end])
        prefix: list[str] = []
        try:
            parsed = _yaml_object(raw) or {}
            if not isinstance(parsed, dict):
                raise ConfigError(f"{path}: frontmatter must be a YAML object")
            data = dict(parsed)
        except yaml.YAMLError as exc:
            if not allow_legacy:
                raise ConfigError(f"{path}: invalid YAML frontmatter: {exc}") from exc
            try:
                sanitized = _yaml_object(_sanitize_legacy_yaml(lines[1:end])) or {}
            except yaml.YAMLError:
                data, prefix = _legacy_frontmatter(lines[1:end])
            else:
                if not isinstance(sanitized, dict):
                    raise ConfigError(f"{path}: frontmatter must be a YAML object")
                data = dict(sanitized)
        if any(not isinstance(key, str) for key in data):
            raise ConfigError(f"{path}: frontmatter keys must be strings")
        body_lines = prefix + lines[end + 1 :]
        body = "\n".join(body_lines).strip("\n")
        return data, body

    if allow_legacy and len(lines) >= 5:
        legacy = {}
        for line in lines[1:4]:
            match = re.match(r"^(ID|NAME|DESCRIPTION):\s*(.*)$", line, re.IGNORECASE)
            if match:
                legacy[match.group(1).lower()] = match.group(2)
        if {"id", "name", "description"} <= legacy.keys():
            return legacy, "\n".join(lines[5:]).strip("\n")

    raise ConfigError(f"{path}: Markdown agent must begin with valid YAML frontmatter")


def _validate_permission(permission: Any, path: Path) -> dict[str, Any]:
    if permission is None:
        return {}
    if not isinstance(permission, dict):
        raise ConfigError(f"{path}: permission must be an object")
    for tool, rule in permission.items():
        if not isinstance(tool, str):
            raise ConfigError(f"{path}: permission keys must be strings")
        if isinstance(rule, str):
            if rule not in {"allow", "ask", "deny"}:
                raise ConfigError(f"{path}: invalid permission action for {tool}: {rule}")
            continue
        if not isinstance(rule, dict) or not rule:
            raise ConfigError(f"{path}: permission rule for {tool} must be an action or non-empty object")
        if any(not isinstance(pattern, str) for pattern in rule):
            raise ConfigError(f"{path}: nested permission patterns for {tool} must be strings")
        if any(not isinstance(action, str) or action not in {"allow", "ask", "deny"} for action in rule.values()):
            raise ConfigError(f"{path}: invalid nested permission action for {tool}")
    return dict(permission)


def _validate_options(options: Any, path: Path) -> dict[str, Any] | None:
    if options is None:
        return None
    if not isinstance(options, dict):
        raise ConfigError(f"{path}: options must be an object of explicit provider options")
    if any(not isinstance(key, str) for key in options):
        raise ConfigError(f"{path}: provider option keys must be strings")
    leaked = REQUEST_LEAK_FIELDS & set(options)
    if leaked:
        raise ConfigError(f"{path}: options contains legacy agent metadata: {', '.join(sorted(leaked))}")
    return dict(options)


def _validate_supported_field_types(data: dict[str, Any], path: Path) -> None:
    for key in ("model", "variant", "description"):
        if key in data and not isinstance(data[key], str):
            raise ConfigError(f"{path}: {key} must be a string")
    for key in ("temperature", "top_p"):
        value = data.get(key)
        if key in data and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ConfigError(f"{path}: {key} must be a finite number")
    for key in ("hidden", "disable"):
        if key in data and not isinstance(data[key], bool):
            raise ConfigError(f"{path}: {key} must be a boolean")
    if "steps" in data:
        steps = data["steps"]
        if isinstance(steps, bool) or not isinstance(steps, int) or steps <= 0:
            raise ConfigError(f"{path}: steps must be a positive integer")
    if "color" in data:
        color = data["color"]
        colors = {"primary", "secondary", "accent", "success", "warning", "error", "info"}
        if not isinstance(color, str) or (color not in colors and not re.fullmatch(r"#[0-9a-fA-F]{6}", color)):
            raise ConfigError(f"{path}: color must be a supported theme color or #RRGGBB")
    if "mode" in data:
        mode = data["mode"]
        if not isinstance(mode, str) or mode not in VALID_MODES | {"all"}:
            raise ConfigError(f"{path}: invalid mode {mode!r}")
    if "options" in data:
        if data["options"] is None:
            raise ConfigError(f"{path}: options must be an object of explicit provider options")
        _validate_options(data["options"], path)
    if "permission" in data:
        _validate_permission(data["permission"], path)


def _canonical_name(path: Path, data: dict[str, Any]) -> str:
    stem = NAME_ALIASES.get(path.stem, path.stem)
    legacy_id = data.get("id")
    legacy_name = data.get("name")
    if legacy_id and legacy_name and legacy_id != legacy_name:
        raise ConfigError(f"{path}: legacy id and name disagree ({legacy_id!r} != {legacy_name!r})")
    declared = legacy_id or legacy_name
    if declared and declared != stem:
        if path.stem in NAME_ALIASES and declared == NAME_ALIASES[path.stem]:
            return declared
        raise ConfigError(f"{path}: identifier {declared!r} conflicts with filename-derived name {stem!r}")
    if not SLUG.fullmatch(stem):
        raise ConfigError(f"{path}: invalid agent filename/identifier {stem!r}")
    return stem


def _migrate_metadata(path: Path, data: dict[str, Any], name: str, body: str) -> tuple[dict[str, Any], str, list[str]]:
    unknown = set(data) - SUPPORTED_AGENT_FIELDS - LEGACY_AGENT_FIELDS
    if "prompt" in data:
        unknown.add("prompt")
    if unknown:
        raise ConfigError(f"{path}: unsupported agent field(s): {', '.join(sorted(unknown))}")

    changes: list[str] = []
    result = {key: value for key, value in data.items() if key in SUPPORTED_AGENT_FIELDS}
    if "options" in result:
        if result["options"] is None:
            raise ConfigError(f"{path}: options must be an object of explicit provider options")
        result["options"] = _validate_options(result["options"], path)
    for key in ("id", "name"):
        if key in data:
            changes.append(f"removed {key}")

    explicit_mode = result.get("mode")
    primary = data.get("primary")
    secondary = data.get("secondary")
    if "primary" in data and not isinstance(primary, bool):
        raise ConfigError(f"{path}: primary must be a boolean")
    if "secondary" in data and not isinstance(secondary, bool):
        raise ConfigError(f"{path}: secondary must be a boolean")
    if primary and secondary:
        raise ConfigError(f"{path}: primary and secondary cannot both be true")
    migrated_mode = "primary" if primary else "subagent" if secondary else None
    if migrated_mode:
        if explicit_mode and explicit_mode != migrated_mode:
            raise ConfigError(f"{path}: mode conflicts with legacy primary/secondary flags")
        explicit_mode = migrated_mode
        changes.append(f"migrated {'primary' if primary else 'secondary'} to mode={migrated_mode}")
    expected_mode = "primary" if name == "pentest" else "subagent"
    if explicit_mode is None:
        explicit_mode = expected_mode
        changes.append(f"set mode={expected_mode}")
    if explicit_mode not in VALID_MODES:
        raise ConfigError(f"{path}: mode must be primary or subagent, got {explicit_mode!r}")
    if explicit_mode != expected_mode:
        changes.append(f"corrected mode from {explicit_mode} to {expected_mode}")
        explicit_mode = expected_mode
    result["mode"] = explicit_mode

    if "maxSteps" in data:
        if "steps" in result and result["steps"] != data["maxSteps"]:
            raise ConfigError(f"{path}: steps conflicts with maxSteps")
        result["steps"] = data["maxSteps"]
        changes.append("migrated maxSteps to steps")

    if "prompt_file" in data:
        prompt_path = Path(str(data["prompt_file"])).expanduser()
        if not prompt_path.is_absolute():
            prompt_path = path.parent / prompt_path
        if not prompt_path.exists():
            raise ConfigError(f"{path}: prompt_file does not exist: {prompt_path}")
        if not body.strip():
            body = prompt_path.read_text(encoding="utf-8")
        changes.append("migrated prompt_file to Markdown body")

    permission = _validate_permission(result.get("permission"), path)
    legacy_tools = data.get("tools")
    if legacy_tools is not None:
        if not isinstance(legacy_tools, dict) or any(not isinstance(v, bool) for v in legacy_tools.values()):
            raise ConfigError(f"{path}: legacy tools must be a boolean map")
        for tool, enabled in legacy_tools.items():
            if tool == "mcp":
                if not enabled:
                    raise ConfigError(f"{path}: Dark-Moon MCP access cannot be disabled for a configured agent")
                permission["darkmoon_*"] = "allow"
                continue
            permission["edit" if tool in {"write", "edit", "patch"} else tool] = "allow" if enabled else "deny"
        changes.append("migrated tools to permission")

    if "mcp" in data:
        servers = data["mcp"]
        if servers != ["darkmoon"] and servers != "darkmoon":
            raise ConfigError(f"{path}: only the globally registered darkmoon MCP server can be migrated")
        changes.append("migrated per-agent mcp to darkmoon_* permission")

    # Last-match permission semantics require the wildcard deny before specific
    # allows. Keep any explicit narrow rules, but never inherit a broad allow.
    if permission.get("*") == "allow":
        changes.append("replaced broad tool allow with least-privilege deny")
    narrow: dict[str, Any] = {"*": "deny", "darkmoon_*": "allow"}
    if name == "pentest":
        narrow["task"] = "allow"
    for tool, rule in permission.items():
        if tool in {"*", "darkmoon_*", "task"}:
            continue
        narrow[tool] = rule
    result["permission"] = narrow

    description = result.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ConfigError(f"{path}: description must be a non-empty string")
    result["description"] = description.strip()
    if not body.strip():
        raise ConfigError(f"{path}: prompt body is empty")

    ordered: dict[str, Any] = {
        "description": result.pop("description"),
        "mode": result.pop("mode"),
    }
    for key in ("model", "variant", "temperature", "top_p", "hidden", "color", "steps", "disable", "options"):
        if key in result:
            ordered[key] = result.pop(key)
    ordered["permission"] = result.pop("permission")
    if result:
        raise ConfigError(f"{path}: unhandled supported field(s): {', '.join(sorted(result))}")
    _validate_supported_field_types(ordered, path)
    return ordered, body.strip("\n"), changes


def _serialize_agent(data: dict[str, Any], body: str) -> str:
    frontmatter = yaml.safe_dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100000,
    ).strip()
    return f"---\n{frontmatter}\n---\n{body.rstrip()}\n"


def migrate_agents(agents_dir: Path) -> list[Path]:
    if not agents_dir.is_dir():
        raise ConfigError(f"agents directory does not exist: {agents_dir}")
    source_files = sorted(agents_dir.rglob("*.md"))
    if not source_files:
        raise ConfigError(f"no Markdown agents found in {agents_dir}")

    prepared: list[tuple[Path, Path, dict[str, Any], str, list[str]]] = []
    targets: dict[Path, Path] = {}
    for source in source_files:
        data, body = read_agent(source, allow_legacy=True)
        name = _canonical_name(source, data)
        target = source.with_name(f"{name}.md")
        if target in targets and targets[target] != source:
            raise ConfigError(f"duplicate agent identifier {name!r}: {targets[target]} and {source}")
        if target.exists() and target != source and target not in source_files:
            raise ConfigError(f"cannot rename {source} to existing file {target}")
        targets[target] = source
        normalized, body, changes = _migrate_metadata(source, data, name, body)
        if target != source:
            changes.append(f"renamed to {target.name}")
        prepared.append((source, target, normalized, body, changes))

    written: list[Path] = []
    for source, target, data, body, changes in prepared:
        rendered = _serialize_agent(data, body)
        source.write_text(rendered, encoding="utf-8", newline="\n")
        if target != source:
            source.replace(target)
        written.append(target)
        if changes:
            print(f"[agent-migrate] {source.name}: {'; '.join(changes)}", file=sys.stderr)
    return written


def _replace_prompt_section(body: str, canonical: str, start_title: str, end_title: str) -> str:
    fence = "=" * 80

    def bounds(text: str) -> tuple[int, int]:
        title = text.find(start_title)
        end_title_at = text.find(end_title, title + len(start_title))
        if title < 0 or end_title_at < 0:
            raise ConfigError(f"cannot migrate pentest prompt section {start_title!r}: section marker missing")
        start = text.rfind(fence, 0, title)
        end = text.rfind(fence, title, end_title_at)
        if start < 0 or end < 0:
            raise ConfigError(f"cannot migrate pentest prompt section {start_title!r}: fence missing")
        return start, end

    old_start, old_end = bounds(body)
    new_start, new_end = bounds(canonical)
    return body[:old_start] + canonical[new_start:new_end] + body[old_end:]


def migrate_required_prompt_sections(agents_dir: Path, canonical_agents_dir: Path) -> None:
    """Upgrade only OpenCode-incompatible orchestrator instructions in old volumes."""
    current_path = agents_dir / "pentest.md"
    canonical_path = canonical_agents_dir / "pentest.md"
    if not current_path.is_file():
        raise ConfigError(f"pentest agent is missing: {current_path}")
    if not canonical_path.is_file():
        raise ConfigError(f"canonical pentest agent is missing: {canonical_path}")
    data, body = read_agent(current_path, allow_legacy=False)
    _, canonical = read_agent(canonical_path, allow_legacy=False)
    changes: list[str] = []

    if "dynamically discover available agents within the OpenCode" in body:
        body = _replace_prompt_section(body, canonical, "PHASE 1 —", "PHASE 2 —")
        changes.append("updated filename-based agent discovery")
    if "SUBAGENT PROMPT = RAW AGENT FILE" in body or 'Any additional fields (e.g., description) are forbidden' in body:
        body = _replace_prompt_section(body, canonical, "PHASE 6 —", "PHASE 7 —")
        changes.append("updated task tool schema and prompt loading")
    if "DISPATCH: cms/lms sub agent" in body:
        legacy = "DISPATCH: cms/lms sub agent"
        mapping_start = canonical.find("DISPATCH MAPPING (use the exact matching subagent_type):")
        mapping_end = canonical.find("\nCONTEXT PASS:", mapping_start)
        if mapping_start < 0 or mapping_end < 0:
            raise ConfigError("canonical pentest prompt is missing the CMS dispatch mapping")
        body = body.replace(legacy, canonical[mapping_start:mapping_end])
        changes.append("updated CMS agent identifiers")
    body = body.replace("cms/lms sub agent", "matched CMS specialist")
    body = re.sub(r"(?m)^(\s*)flask(\s+→)", r"\1python-flask\2", body)
    body = re.sub(r"(?m)^(\s*)ruby(\s+→)", r"\1ruby-on-rails\2", body)

    rendered = _serialize_agent(data, body)
    if rendered != current_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n"):
        current_path.write_text(rendered, encoding="utf-8", newline="\n")
    if changes:
        print(f"[agent-migrate] pentest.md: {'; '.join(changes)}", file=sys.stderr)


def _check_file_references(value: Any, base: Path, source: str) -> None:
    if isinstance(value, str):
        for match in FILE_REFERENCE.finditer(value):
            raw = match.group(1)
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                candidate = base / candidate
            if not candidate.exists():
                raise ConfigError(f"{source}: referenced prompt/config file does not exist: {candidate}")
    elif isinstance(value, dict):
        for nested in value.values():
            _check_file_references(nested, base, source)
    elif isinstance(value, list):
        for nested in value:
            _check_file_references(nested, base, source)


def validate_agents(agents_dir: Path) -> dict[str, dict[str, Any]]:
    files = sorted(agents_dir.rglob("*.md"))
    if not files:
        raise ConfigError(f"no Markdown agents found in {agents_dir}")
    agents: dict[str, dict[str, Any]] = {}
    for path in files:
        data, body = read_agent(path, allow_legacy=False)
        forbidden = set(data) & LEGACY_AGENT_FIELDS
        unknown = set(data) - SUPPORTED_AGENT_FIELDS
        if forbidden:
            raise ConfigError(f"{path}: legacy agent field(s): {', '.join(sorted(forbidden))}")
        if unknown:
            raise ConfigError(f"{path}: unsupported agent field(s): {', '.join(sorted(unknown))}")
        _validate_supported_field_types(data, path)
        name = path.stem
        if not SLUG.fullmatch(name):
            raise ConfigError(f"{path}: filename is not a valid agent identifier")
        if name in agents:
            raise ConfigError(f"duplicate agent identifier: {name}")
        expected_mode = "primary" if name == "pentest" else "subagent"
        if data.get("mode") != expected_mode:
            raise ConfigError(f"{path}: expected mode={expected_mode}, got {data.get('mode')!r}")
        if not isinstance(data.get("description"), str) or not data["description"].strip():
            raise ConfigError(f"{path}: missing description")
        if not body.strip():
            raise ConfigError(f"{path}: prompt body is empty")
        permission = _validate_permission(data.get("permission"), path)
        if "options" in data:
            if data["options"] is None:
                raise ConfigError(f"{path}: options must be an object of explicit provider options")
            _validate_options(data["options"], path)
        if list(permission)[:2] != ["*", "darkmoon_*"]:
            raise ConfigError(f"{path}: permission order must begin with '*' deny then 'darkmoon_*' allow")
        if permission["*"] != "deny" or permission["darkmoon_*"] != "allow":
            raise ConfigError(f"{path}: Dark-Moon agents must deny other tools and allow darkmoon_*")
        if name == "pentest" and permission.get("task") != "allow":
            raise ConfigError(f"{path}: pentest must be allowed to dispatch subagents with task")
        if name != "pentest" and permission.get("task") == "allow":
            raise ConfigError(f"{path}: specialist agents must not dispatch other agents")
        _check_file_references(data, path.parent, str(path))
        agents[name] = data
    if "pentest" not in agents:
        raise ConfigError("pentest agent is missing")
    primary = [name for name, data in agents.items() if data["mode"] == "primary"]
    if primary != ["pentest"]:
        raise ConfigError(f"pentest must be the only Dark-Moon primary agent, got: {primary}")
    return agents


def _walk_forbidden(value: Any, *, path: tuple[str, ...] = ()) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            current = path + (str(key),)
            if key in REQUEST_LEAK_FIELDS and not (key == "mcp" and not path):
                found.append(".".join(current))
            found.extend(_walk_forbidden(nested, path=current))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(_walk_forbidden(nested, path=path + (str(index),)))
    return found


def validate_config(config_file: Path, agents_dir: Path) -> dict[str, Any]:
    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"invalid generated OpenCode config {config_file}: {exc}") from exc
    leaked = _walk_forbidden(config)
    if leaked:
        raise ConfigError(f"{config_file}: legacy metadata remains at: {', '.join(leaked)}")
    if config.get("default_agent") != "pentest":
        raise ConfigError(f"{config_file}: default_agent must be pentest")
    darkmoon = config.get("mcp", {}).get("darkmoon", {})
    if darkmoon.get("enabled") is not True or darkmoon.get("command") != ["/usr/local/bin/darkmoon-mcp"]:
        raise ConfigError(f"{config_file}: global darkmoon MCP server is not enabled correctly")
    if "permission" in config and config["permission"] == {"*": "allow"}:
        raise ConfigError(f"{config_file}: global unrestricted tool permission is forbidden")
    agent_options = config.get("agent", {})
    if not isinstance(agent_options, dict):
        raise ConfigError(f"{config_file}: agent must be an object when present")
    for name, agent in agent_options.items():
        if not isinstance(agent, dict):
            raise ConfigError(f"{config_file}: agent.{name} must be an object")
        unknown = set(agent) - SUPPORTED_AGENT_FIELDS - {"prompt"}
        if unknown:
            raise ConfigError(f"{config_file}: agent.{name} has unsupported fields: {', '.join(sorted(unknown))}")
        _validate_supported_field_types({key: value for key, value in agent.items() if key != "prompt"}, config_file)
        if "prompt" in agent and not isinstance(agent["prompt"], str):
            raise ConfigError(f"{config_file}: agent.{name}.prompt must be a string")
        bad_options = set(agent.get("options", {})) & REQUEST_LEAK_FIELDS
        if bad_options:
            raise ConfigError(f"{config_file}: agent.{name}.options contains leaked metadata: {sorted(bad_options)}")
    _check_file_references(config, config_file.parent, str(config_file))
    validate_agents(agents_dir)
    return config


def _atomic_json(path: Path, data: dict[str, Any], *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temp = Path(handle.name)
    temp.chmod(mode)
    temp.replace(path)


# Free, text-only, tool-capable (agentic) chat models on the Nous
# (inference-api.nousresearch.com) provider, with parameters verified
# against the provider's /models endpoint. Supplied so the local
# OpenAI-compatible strategy exposes the custom `nous` provider complete
# with reasoning/effort handling and context/cost metadata.
_NOUS_FREE_MODELS: dict[str, Any] = {
    "tencent/hy3:free": {
        "name": "Hy3:free",
        "reasoning": True,
        "limit": {"context": 262144, "output": 128000},
        "cost": {"input": 0, "output": 0, "cache_read": 0},
        "modalities": {"input": ["text"], "output": ["text"]},
        "options": {"reasoningEffort": "high"},
    },
    "poolside/laguna-s-2.1:free": {
        "name": "Laguna S 2.1:free",
        "reasoning": True,
        "limit": {"context": 262144, "output": 131072},
        "cost": {"input": 0, "output": 0, "cache_read": 0},
        "modalities": {"input": ["text"], "output": ["text"]},
    },
    "poolside/laguna-xs-2.1:free": {
        "name": "Laguna XS 2.1:free",
        "reasoning": True,
        "limit": {"context": 262144, "output": 32768},
        "cost": {"input": 0, "output": 0, "cache_read": 0},
        "modalities": {"input": ["text"], "output": ["text"]},
    },
    "upstage/solar-pro4:free": {
        "name": "Solar Pro 4:free",
        "reasoning": False,
        "limit": {"context": 524288, "output": 131072},
        "cost": {"input": 0, "output": 0, "cache_read": 0},
        "modalities": {"input": ["text"], "output": ["text"]},
    },
}


_ALLOWED_MODALITIES = {"text", "audio", "image", "video", "pdf"}


def _nous_model_entry(m: dict[str, Any]) -> dict[str, Any]:
    """Sanitize one Nous /models entry into an opencode provider model entry."""
    out: dict[str, Any] = {"name": m.get("name") or m.get("id")}
    ctx = m.get("context_length")
    mx = (m.get("top_provider") or {}).get("max_completion_tokens")
    if isinstance(ctx, (int, float)) and isinstance(mx, (int, float)):
        out["limit"] = {"context": int(ctx), "output": int(mx)}
    p = m.get("pricing") or {}

    def _num(v: object) -> float:
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0

    out["cost"] = {
        "input": _num(p.get("prompt")),
        "output": _num(p.get("completion")),
        "cache_read": _num(p.get("input_cache_read")),
        "cache_write": _num(p.get("input_cache_write")),
    }
    arch = m.get("architecture") or {}
    im = [x for x in (arch.get("input_modalities") or []) if x in _ALLOWED_MODALITIES]
    om = [x for x in (arch.get("output_modalities") or []) if x in _ALLOWED_MODALITIES]
    if im and om:
        out["modalities"] = {"input": im, "output": om}
    sp = m.get("supported_parameters") or []
    out["reasoning"] = "reasoning" in sp
    if "reasoning_effort" in sp:
        de = (m.get("reasoning") or {}).get("default_effort")
        if de:
            out["options"] = {"reasoningEffort": de}
    return out


def _nous_provider_models(base_url: str) -> dict[str, Any]:
    """Enumerate the full Nous catalog (like a built-in provider).

    Queries the provider's /models endpoint and sanitizes every entry so the
    model picker exposes context/cost/reasoning metadata. Falls back to the
    curated free set if the endpoint is unreachable (e.g. offline bootstrap).
    """
    try:
        import urllib.request

        url = (base_url or "").rstrip("/") + "/models"
        if not url.startswith("http"):
            raise ValueError("missing base URL")
        req = urllib.request.Request(
            url, headers={"Accept": "application/json", "User-Agent": "opencode-config"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        models = {m["id"]: _nous_model_entry(m) for m in payload.get("data", []) if m.get("id")}
        if models:
            return models
    except Exception:
        pass
    return dict(_NOUS_FREE_MODELS)


def _local_provider_models(provider_id: str, model_id: str) -> dict[str, Any]:
    """Model map for a local OpenAI-compatible provider.

    The custom `nous` provider is enumerated in full from the live /models
    endpoint (like a built-in provider); every other local provider just
    exposes the single configured model.
    """
    if provider_id == "nous":
        return _nous_provider_models(os.environ.get("OPENCODE_LOCAL_BASE_URL", ""))
    return {model_id: {"name": model_id}}


def render_config(config_file: Path, auth_file: Path) -> str:
    local = (
        os.getenv("OPENCODE_LOCAL_MODE", "false") == "true"
        and os.getenv("OPENCODE_LOCAL_PROVIDER_ID")
        and os.getenv("OPENCODE_LOCAL_BASE_URL")
        and os.getenv("OPENCODE_LOCAL_MODEL")
    )
    anthropic = not local and os.getenv("ANTHROPIC_BASE_URL") and os.getenv("ANTHROPIC_MODEL")
    cloud = (
        not local
        and not anthropic
        and os.getenv("OPENROUTER_PROVIDER")
        and os.getenv("OPENROUTER_API_KEY")
        and os.getenv("OPENCODE_MODEL")
    )

    provider: dict[str, Any] | None = None
    if local:
        provider_id = os.environ["OPENCODE_LOCAL_PROVIDER_ID"]
        model_id = os.environ["OPENCODE_LOCAL_MODEL"]
        model = f"{provider_id}/{model_id}"
        options: dict[str, Any] = {"baseURL": os.environ["OPENCODE_LOCAL_BASE_URL"]}
        if os.getenv("OPENCODE_LOCAL_API_KEY"):
            options["apiKey"] = os.environ["OPENCODE_LOCAL_API_KEY"]
        provider = {
            provider_id: {
                "npm": "@ai-sdk/openai-compatible",
                "name": os.getenv("OPENCODE_LOCAL_PROVIDER_NAME", "Local model"),
                "options": options,
                "models": _local_provider_models(provider_id, model_id),
            }
        }
        strategy = "local OpenAI-compatible"
    elif anthropic:
        model_id = os.environ["ANTHROPIC_MODEL"]
        model = f"anthropic/{model_id}"
        provider = {"anthropic": {"models": {model_id: {"name": model_id}}}}
        strategy = "Anthropic-compatible"
    elif cloud:
        provider_id = os.environ["OPENROUTER_PROVIDER"]
        model_id = os.environ["OPENCODE_MODEL"]
        # If OPENCODE_MODEL already contains the provider prefix (e.g.
        # "nvidia/minimaxai/minimax-m3"), don't double it up.
        if model_id.startswith(f"{provider_id}/"):
            model = model_id
        else:
            model = f"{provider_id}/{model_id}"
        strategy = f"cloud provider {provider_id}"
    else:
        model = "opencode/big-pickle"
        strategy = "OpenCode fallback"

    config: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "model": model,
        "small_model": model,
        "default_agent": "pentest",
        "mcp": {
            "darkmoon": {
                "type": "local",
                "command": ["/usr/local/bin/darkmoon-mcp"],
                "timeout": 36_000_000,
                "enabled": True,
            }
        },
    }
    if provider:
        config["provider"] = provider
    _atomic_json(config_file, config)

    if cloud:
        _atomic_json(
            auth_file,
            {os.environ["OPENROUTER_PROVIDER"]: {"type": "api", "key": os.environ["OPENROUTER_API_KEY"]}},
            mode=0o600,
        )
    elif auth_file.exists():
        auth_file.unlink()
    return f"{strategy}: {model}"


def apply_configuration(
    config_file: Path,
    auth_file: Path,
    agents_dir: Path,
    canonical_agents_dir: Path | None = None,
) -> None:
    migrate_agents(agents_dir)
    if canonical_agents_dir is not None:
        migrate_required_prompt_sections(agents_dir, canonical_agents_dir)
    validate_agents(agents_dir)
    strategy = render_config(config_file, auth_file)
    validate_config(config_file, agents_dir)
    print(f"[opencode-config] {strategy}", file=sys.stderr)
    print(f"[opencode-config] wrote and validated {config_file}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("migrate", "validate", "apply"):
        item = sub.add_parser(command)
        item.add_argument("--agents-dir", type=Path, required=True)
        if command in {"validate", "apply"}:
            item.add_argument("--config-file", type=Path, required=command == "apply")
        if command == "apply":
            item.add_argument("--auth-file", type=Path, required=True)
            item.add_argument("--canonical-agents-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "migrate":
            migrate_agents(args.agents_dir)
            validate_agents(args.agents_dir)
        elif args.command == "validate":
            if args.config_file:
                validate_config(args.config_file, args.agents_dir)
            else:
                validate_agents(args.agents_dir)
        else:
            apply_configuration(args.config_file, args.auth_file, args.agents_dir, args.canonical_agents_dir)
    except ConfigError as exc:
        print(f"opencode-config: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
