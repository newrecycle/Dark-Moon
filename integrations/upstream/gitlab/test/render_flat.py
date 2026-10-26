#!/usr/bin/env python3
"""Flatten the CI/CD component into a plain .gitlab-ci.yml for `gitlab-runner exec`.

`gitlab-runner exec` cannot resolve `include: component:` (server-side), so this
reproduces what GitLab does on include: interpolate every `$[[ inputs.X ]]`
token with the chosen input value and emit a standalone pipeline. Interpolation
is done on the RAW template text (as GitLab does), so a token inside a quoted
scalar stays a string and an unquoted token (e.g. the exit_codes array) becomes
typed YAML. TEST harness only — not part of the component.

Usage: render_flat.py out.yml key=value [key=value ...]
"""
import json
import re
import sys

import yaml

TOKEN = re.compile(r"\$\[\[\s*inputs\.([a-zA-Z0-9_.-]+)\s*\]\]")
TEMPLATE = "/home/mehdi/darkmoon-gitlab/templates/scan/template.yml"


def render_value(meta, raw):
    t = (meta or {}).get("type")
    if t == "array":
        return json.dumps(json.loads(raw))          # -> [4]
    if t == "boolean":
        return "true" if raw in ("true", "True", "1", True) else "false"
    return str(raw)


def main(argv):
    out = argv[0]
    overrides = dict(kv.split("=", 1) for kv in argv[1:])
    with open(TEMPLATE, encoding="utf-8") as fh:
        text = fh.read()

    # split spec doc from job doc on the document separator
    parts = re.split(r"\n---\n", text, maxsplit=1)
    spec_text, job_text = parts[0], parts[1]
    spec_inputs = yaml.safe_load(spec_text)["spec"]["inputs"]

    values = {}
    for name, meta in spec_inputs.items():
        meta = meta or {}
        if name in overrides:
            values[name] = render_value(meta, overrides[name])
        elif "default" in meta:
            d = meta["default"]
            values[name] = json.dumps(d) if isinstance(d, list) else (
                "true" if d is True else "false" if d is False else str(d))
        else:
            raise SystemExit("missing required input: %s" % name)

    def repl(m):
        name = m.group(1)
        if name not in values:
            raise SystemExit("unknown input referenced: %s" % name)
        return values[name]

    job_text = TOKEN.sub(repl, job_text)
    job_doc = yaml.safe_load(job_text)

    stages = sorted({j.get("stage", "test") for j in job_doc.values() if isinstance(j, dict)})
    out_doc = {"stages": stages}
    out_doc.update(job_doc)
    with open(out, "w", encoding="utf-8") as fh:
        yaml.safe_dump(out_doc, fh, sort_keys=False, default_flow_style=False, width=4096)
    print("wrote %s with jobs: %s" % (out, [k for k in job_doc]))


if __name__ == "__main__":
    main(sys.argv[1:])
