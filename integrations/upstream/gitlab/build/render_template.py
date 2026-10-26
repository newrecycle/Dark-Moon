#!/usr/bin/env python3
"""Render templates/scan/template.yml from the .in skeleton + the mapper.

Keeps src/darkmoon_gitlab_report.py the single source of truth: its base64 is
embedded into the component so the shipped YAML is fully self-contained (a CI/CD
component is only YAML — the runner job cannot otherwise see the mapper file).
"""
import base64
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPER = os.path.join(ROOT, "src", "darkmoon_gitlab_report.py")
SKELETON = os.path.join(ROOT, "templates", "scan", "template.yml.in")
OUT = os.path.join(ROOT, "templates", "scan", "template.yml")
TOKEN = "@@MAPPER_B64@@"


def main() -> int:
    with open(MAPPER, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")  # single line, no wraps
    if "'" in b64 or "\n" in b64:
        print("unexpected characters in base64", file=sys.stderr)
        return 1
    with open(SKELETON, "r", encoding="utf-8") as fh:
        text = fh.read()
    if TOKEN not in text:
        print("token %s not found in skeleton" % TOKEN, file=sys.stderr)
        return 1
    text = text.replace(TOKEN, b64)
    header = ("# GENERATED FILE — do not edit by hand.\n"
              "# Source: templates/scan/template.yml.in + src/darkmoon_gitlab_report.py\n"
              "# Regenerate with: python3 build/render_template.py\n")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(header + text)
    print("rendered %s (%d bytes, mapper %d b64 chars)" % (OUT, len(text), len(b64)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
