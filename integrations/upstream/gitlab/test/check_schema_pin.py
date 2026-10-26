#!/usr/bin/env python3
"""Guard against SAST schema drift.

The mapper emits `version` == DEFAULT_SAST_SCHEMA_VERSION. This asserts that
value equals the `self.version` of the vendored LIVE schema, which is refreshed
from security-report-schemas. If GitLab publishes a new schema, refresh the
vendored copy and this check (plus validate_schemas.py) forces the pin to move
deliberately instead of drifting.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))
import darkmoon_gitlab_report as m  # noqa: E402

schema = json.load(open(os.path.join(HERE, "vendor", "sast-report-format.schema.json")))
live = schema.get("self", {}).get("version")
pinned = m.DEFAULT_SAST_SCHEMA_VERSION
if live == pinned:
    print("schema pin OK: mapper=%s == live vendored schema=%s" % (pinned, live))
    sys.exit(0)
print("SCHEMA DRIFT: mapper default %s != live schema %s "
      "(refresh vendor/sast-report-format.schema.json and the pin)" % (pinned, live),
      file=sys.stderr)
sys.exit(1)
