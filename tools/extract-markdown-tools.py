#!/usr/bin/env python3
"""Print only tools declared by DarkMoon ``which`` inventory lines.

Recognized input has this form (spacing around the call may vary):

    darkmoon_execute_command(command="bash -c 'which tool1 tool2 2>&1'")

Only the names between ``which`` and the first shell redirection/operator or
the closing single quote are emitted. Standard output is therefore strictly
zero or more unique tool names, one per line. Errors go to standard error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = (
    REPO / "conf" / "agents",
    REPO / "darkmoon-settings" / "agents",
    REPO / "mcp" / ".opencode" / "agents",
)

# Match only the explicit DarkMoon toolbox inventory command. This deliberately
# ignores every other command, code block, inline-code span, and prose mention.
INVENTORY_START = re.compile(
    r"darkmoon_execute_command\s*\(\s*"
    r"command\s*=\s*\"bash\s+-c\s+'which\s+"
)

# A tool name must be a single executable-like token. Paths, options,
# placeholders, assignments, shell syntax, and prose cannot match.
TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+@-]*$")


def tools_from_line(line: str) -> set[str]:
    """Extract tool names from every inventory marker on one physical line."""
    tools: set[str] = set()

    for match in INVENTORY_START.finditer(line):
        tail = line[match.end() :]

        # The inventory is inside bash's opening single quote. Nothing after its
        # matching closing quote belongs to the `which` argument list.
        tail = tail.split("'", 1)[0]

        for token in tail.split():
            # Stop at redirects/operators such as 2>&1, >/dev/null, |, &&, or ;.
            if any(char in token for char in "<>&|;"):
                break
            # `which -a foo` is valid, but -a is an option rather than a tool.
            if token.startswith("-"):
                continue
            if TOOL_NAME.fullmatch(token):
                tools.add(token)

    return tools


def extract_tools(markdown: str) -> set[str]:
    """Extract tools from explicit inventory lines in Markdown text."""
    tools: set[str] = set()
    for line in markdown.splitlines():
        tools.update(tools_from_line(line))
    return tools


def markdown_files(inputs: Iterable[str]) -> list[Path]:
    """Resolve Markdown files/directories without following non-Markdown files."""
    files: set[Path] = set()
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            files.update(item for item in path.rglob("*.md") if item.is_file())
        elif path.is_file() and path.suffix.lower() == ".md":
            files.add(path)
        else:
            raise FileNotFoundError(f"not a Markdown file or directory: {path}")
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print only tools from DarkMoon 'which' inventory lines."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=[str(path) for path in DEFAULT_INPUTS if path.is_dir()],
        help="Markdown files/directories (default: agent-definition directories)",
    )
    args = parser.parse_args(argv)

    try:
        tools: set[str] = set()
        for path in markdown_files(args.paths):
            tools.update(extract_tools(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError) as exc:
        print(f"extract-markdown-tools: {exc}", file=sys.stderr)
        return 1

    for tool in sorted(tools, key=lambda value: (value.casefold(), value)):
        print(tool)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
