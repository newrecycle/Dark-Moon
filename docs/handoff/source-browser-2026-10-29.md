# Scoped source browsing — 29 October 2026

Configure absolute owned Git roots in DARKMOON_SOURCE_REPOSITORIES, separated by
the platform path separator. A repository identifier is `repo_` plus the SHA-256
hex digest of its exact configured path string. Configuration changes invalidate
future use of removed roots. Paths are not added to default workspace choices.
The administrator enters the known path and explicitly clicks Refresh source
files. There is no automatic enumeration on form opening or path changes.

POST /api/v1/evidence/grants with kind source and the repository identifier
issues the existing session-bound, one-use, 45-second grant. Admission checks
configuration only, without filesystem probing. POST /api/v1/source-files with
JSON {"repository_id":"repo_..."} and X-Darkmoon-Evidence-Grant consumes it before
probing. Viewer/analyst, absent/replayed/expired/wrong-resource grants and removed
roots fail closed. Old GET enumeration stays forbidden.

Only tracked regular filenames are offered, never contents, untracked names,
tracked symlinks or submodules. Directory symlinks are rejected. Git execution
has a five-second deadline and 1-MiB output limit; at most 5000 unique names are
offered with explicit truncation. Repository metadata is operator-trusted;
this is not a sandbox for hostile repositories modified concurrently by another
principal. Administrators must approve roots and control their Git metadata.

Names and selected paths clear on close, expiry, repository changes, window blur
and hidden documents. Responses are discarded after session/path/request changes.
This cannot retract filenames already copied or observed.

Reproduce from checkout root using the API parity runbook's environment:

```bash
PYTHONPATH=mcp .venv/bin/python -m pytest tests/community/test_evidence_access.py -q
node --check mcp/community/static/workspace.js
```

The new real-Git HTTP case verifies no unauthorized probe, role/scope denial,
one-use/replay, removed configuration, tracked-only enumeration and symlink
exclusion. Local result: 12 evidence tests passed. Browser acceptance now checks
explicit listing and blur clearing; take its result from the hosted run for this
commit, not from the test source. No vendor equivalence claim.
