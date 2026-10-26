# Actual owned-loopback analysis — 26 October 2026

[CI run](https://github.com/newrecycle/Dark-Moon/actions/runs/40422317137)
tested source `ed329f158b3d6d9f795ad1e85765e3ccc8775f1e`.
The `owned-lab-analysis` job built a disposable toolbox, executed three real
HTTP probes through DarkMoon's Docker adapter and BaseWorkflow, pushed native
campaign/finding records, finalized the report, and checked WebUI campaign,
graph, options, Markdown and PDF responses. No mocked execution transport was used.

Measured results: two confirmed observations (missing hardening headers and
unescaped inert HTML reflection); the negative authentication control returned
HTTP 401. Neither JavaScript execution nor an LLM-driven pentest was performed.

- [Machine-readable analysis and HTTP evidence](analysis.json)
- [Generated native DarkMoon report](report.md)
- [Native campaign, target, finding and infrastructure records](records)

These are observations of an intentionally configured, owned ephemeral lab,
not findings against this WebUI or any third-party service. The target and its
container were removed after the run. No user workspace keys or control-state
files are included.

The original CI artifact ZIP has SHA-256
`ed810be5032c541495a2bffda09a4c0d764904ce27d77494274887d35b7d429a`.
Artifact id: `12697089795`. JSON records and the native Markdown report here
retain their original bytes from that artifact.

To inspect this data in a disposable local WebUI workspace from the repo root:

```bash
TASK_LAB_DIR=$(mktemp -d)
cp -R docs/validation/owned-lab-20261026/records "$TASK_LAB_DIR/records"
DARKMOON_DATA_DIR="$TASK_LAB_DIR/records" DARKMOON_PYTHON="$PWD/.venv/bin/python" ./community.sh
```

This copy keeps generated dashboard keys and control state outside the source
repository. The sample target no longer exists; starting a new assessment still
uses your separately configured runtime.
