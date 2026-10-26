#!/usr/bin/env python3
"""Validate emitted GitLab reports.

- gl-sast-report.json  -> validated against the LIVE security-report-schemas
  SAST schema fetched at setup (test/vendor/sast-report-format.schema.json).
- gl-code-quality-report.json -> validated against GitLab's documented CodeClimate
  required-field contract (description, check_name, fingerprint, severity enum,
  location.path, location.lines.begin | location.positions.begin.line).

Exit 0 = all valid, 1 = a validation error.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAST_SCHEMA = os.path.join(HERE, "vendor", "sast-report-format.schema.json")
CQ_SEVERITIES = {"info", "minor", "major", "critical", "blocker"}


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_sast(path):
    import jsonschema
    schema = load(SAST_SCHEMA)
    doc = load(path)
    jsonschema.validate(instance=doc, schema=schema)  # raises on error
    return "SAST OK: version=%s, %d vulnerabilities, validated vs live schema %s" % (
        doc.get("version"), len(doc.get("vulnerabilities", [])),
        schema.get("self", {}).get("version"))


def validate_codequality(path):
    doc = load(path)
    if not isinstance(doc, list):
        raise ValueError("code quality report must be a JSON array")
    seen_fp = set()
    for i, item in enumerate(doc):
        for req in ("description", "check_name", "fingerprint", "severity", "location"):
            if req not in item:
                raise ValueError("entry %d missing required field %r" % (i, req))
        if item["severity"] not in CQ_SEVERITIES:
            raise ValueError("entry %d severity %r not in %s" % (i, item["severity"], CQ_SEVERITIES))
        loc = item["location"]
        if "path" not in loc or not isinstance(loc["path"], str) or loc["path"].startswith("./"):
            raise ValueError("entry %d location.path invalid: %r" % (i, loc.get("path")))
        has_lines = isinstance(loc.get("lines"), dict) and isinstance(loc["lines"].get("begin"), int)
        has_pos = (isinstance(loc.get("positions"), dict)
                   and isinstance(loc["positions"].get("begin"), dict)
                   and isinstance(loc["positions"]["begin"].get("line"), int))
        if not (has_lines or has_pos):
            raise ValueError("entry %d missing location.lines.begin/positions.begin.line" % i)
        if not isinstance(item["fingerprint"], str) or not item["fingerprint"]:
            raise ValueError("entry %d fingerprint invalid" % i)
        seen_fp.add(item["fingerprint"])
    if len(seen_fp) != len(doc):
        raise ValueError("fingerprints are not unique (%d unique / %d entries)" % (len(seen_fp), len(doc)))
    return "Code Quality OK: %d entries, unique fingerprints, valid severities & locations" % len(doc)


def main(argv):
    if len(argv) < 2:
        print("usage: validate_schemas.py <gl-code-quality-report.json> <gl-sast-report.json>",
              file=sys.stderr)
        return 2
    cq_path, sast_path = argv[0], argv[1]
    ok = True
    try:
        print("[validate] " + validate_codequality(cq_path))
    except Exception as exc:  # noqa: BLE001
        print("[validate] CODE QUALITY INVALID: %s" % exc, file=sys.stderr); ok = False
    try:
        print("[validate] " + validate_sast(sast_path))
    except Exception as exc:  # noqa: BLE001
        print("[validate] SAST INVALID: %s" % exc, file=sys.stderr); ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
