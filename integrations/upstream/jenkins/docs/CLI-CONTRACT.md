# `darkmoon-ci` interface consumed by this plugin

The plugin shells out to the portable `darkmoon-ci` CLI (built on `@darkmoon_ai/client`,
contract v1.0.0). This document is the exact surface the plugin depends on; it is verified
against the CLI's own conformance fixtures.

## Invocations (in order)

```
darkmoon-ci run    --target <t> --mode <auto|oss|pro> [--pro-url <url>]
                   [--oss-data-dir <d>] [--oss-reports-dir <r>] [--oss-script <s>]
                   --fail-on <csv> [--timeout <sec>] --json
darkmoon-ci findings <campaignId> --mode <..> [backend flags] --json
darkmoon-ci summary  <campaignId> --mode <..> [backend flags] --json
darkmoon-ci report   <campaignId> --mode <..> [backend flags] --out <file> [--full --private]
```

- `--fail-on` is a CSV of severities (e.g. `critical,high`); the plugin derives it from its
  `failOn` threshold. The plugin recomputes the gate itself from the `summary` output, so
  the CLI's verdict/exit code is authoritative-independent.

## Secrets (environment only — never argv)

| Env var             | Source                                   |
|---------------------|------------------------------------------|
| `DARKMOON_PRO_TOKEN`| `credentialsId` (Secret text)            |
| `DARKMOON_LICENSE`  | `licenseCredentialsId` (Secret text)     |
| `DARKMOON_PRO_URL`  | `apiUrl`                                  |

## Exit codes

| Code | Meaning                        | Plugin behavior                              |
|------|--------------------------------|----------------------------------------------|
| 0    | ran, fail-policy not tripped   | proceed                                       |
| 2    | ran, fail-policy tripped       | proceed (plugin recomputes gate from summary) |
| 1    | tool / usage / runtime error   | abort the step, archive the CLI log           |

## `run --json` output

```json
{ "campaignId": "camp_…", "verdict": "pass|fail",
  "failOn": ["critical","high"], "offending": {…}, "total": 5, "reason": "…" }
```

## `findings --json` output (redaction-safe)

A JSON array of normalized findings. Fields the plugin reads:

```
id, title, severity(critical|high|medium|low|info), status, category,
cve, cvssScore, cvssVector, mitreAttackId, mitreAttackName, endpoint,
description, remediation, discoveredByAgent, discoveredAt, evidence(null), edition
```

`evidence` is `null` unless the operator opts in — the plugin never opts in, so nothing it
emits carries evidence, raw requests/responses or extracted data.

## `summary --json` output

```json
{ "critical": 2, "high": 1, "medium": 2, "low": 0, "info": 0, "total": 5 }
```

Unknown severities normalize to `info` (never silently escalated).
