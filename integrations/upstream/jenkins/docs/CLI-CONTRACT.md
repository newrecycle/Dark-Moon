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

## Jenkins OSS launch identity

The Jenkins overlay invokes the configured OSS script as
`script <single-prompt-argument> --format json`. The normal `darkmoon.sh`
wrapper passes these arguments to the pinned OpenCode runtime. Its JSON event
contract is pinned at [OpenCode run.ts, revision 77b3b467](https://github.com/ASCIT31/opencode/blob/77b3b46788623317115ae920cf0072e54aa2643c/packages/opencode/src/cli/cmd/run.ts).
Custom scripts must accept these trailing arguments and emit the same producer
contract; old scripts that only create files are intentionally rejected.

A `step_start` JSON line supplies `sessionID`; its `part.type` must be
`step-start` and `part.sessionID` must agree. All observed supported events must
retain the root identity. A detached Node relay reads that child's private
stdout pipe and sends only completion/root metadata over a private IPC channel.
It discards stderr and raw text/tool bodies, retaining at most one 64-KiB line.
Oversized lines are discarded through their delimiter. It persists no raw log.

The producer must exit successfully before a campaign verdict can be read.
Exactly one regular, single-link campaign file (at most 4 MiB) must have the
matching `opencode_session_id`, a matching filename/record ID and no child-run
marker. The status read rechecks that binding. Missing/conflicting identities,
duplicate bindings, failed producers and stale/foreign campaigns never become
empty successful findings. PROGRAM is a display label, not a correlation key.
Unrelated concurrent campaigns and repeated program names remain supported.
A prelaunch filename set is used only to reject replay of an existing campaign;
it never selects a candidate or supplies a missing root identity.

The relay uses the requested CLI timeout (default one hour, maximum 24 hours)
and a ten-second startup handshake deadline. Background `launch` returns after
the child starts; the relay continues draining output if that CLI exits. The
`run` command retains its existing pass/policy/error exit codes. Follow-up reads
by an explicit campaign ID remain supported. No API, model or shared SDK change
is required. This relies on the trusted local launcher/storage boundary, not a
cryptographic attestation or transactional snapshot of all assessment output.
