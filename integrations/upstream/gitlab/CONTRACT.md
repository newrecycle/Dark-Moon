# What this component consumes from `darkmoon-ci`

This GitLab component is a thin consumer of the portable **`darkmoon-ci`** CLI
shipped by `@darkmoon_ai/client` (its own `CONTRACT.md` is the frozen source of
truth — `/home/mehdi/darkmoon-client/CONTRACT.md`, `CONTRACT_VERSION = 1.0.0`).
The component never reimplements the CLI; it invokes it and maps its output to
GitLab report formats.

## CLI surface used

```
darkmoon-ci run     --target <t> --json --fail-on <sev,list> [backend flags]
darkmoon-ci findings <campaignId> --json [backend flags]      # redaction-safe
darkmoon-ci report  <campaignId> --out <file> [backend flags] # redacted by default
```

Backend flags (all optional, passed identically to every subcommand):
`--mode auto|oss|pro`, `--pro-url <url>`, `--timeout <s>`, `--oss-data-dir <dir>`,
`--oss-reports-dir <dir>`, `--oss-script <path>`.

- `run --json` prints a **verdict** object: `{ campaignId, verdict, failOn,
  offending, total, reason }`. The component reads `campaignId`.
- `findings <id> --json` prints a **bare array** of normalized findings
  (`evidence: null` — redaction-safe).

### Exit codes (frozen: 0 / 2 / 1)

| Code | Meaning | Component behaviour |
|-----:|---------|---------------------|
| `0` | pass — no finding matched `--fail-on` | job passes |
| `2` | fail-policy tripped — a finding matched `--fail-on` | job **fails**; non-blocking lists `2` in `allow_failure:exit_codes` |
| `1` | tool / usage / backend error | job fails (real error) |

`--fail-on` is a **set of severities** that fail the build (e.g.
`critical,high`), not a threshold. Empty = never fail on findings.

## Normalized finding fields (used by the mapper)

Frozen enums are lowercase: `severity ∈ {critical,high,medium,low,info}`.

`id, title, severity, status, category, cve, cvssScore, cvssVector,
mitreAttackId, mitreAttackName, endpoint, description, remediation,
discoveredByAgent, discoveredAt, evidence`.

The component's mapper (`src/darkmoon_gitlab_report.py`) uses only redaction-safe
fields on shared surfaces:

- **Code Quality** — `description` = `title` (+ `[Darkmoon <category> · CVSS x]`),
  `check_name` = `darkmoon/<category>`, `fingerprint` = SHA-256 of
  `id|path|title`, `severity` mapped (`critical→blocker … info→info`),
  `location.path` = the `endpoint` path (method + host stripped),
  `location.lines.begin` = 1.
- **SAST** (security-report-schemas, read live at build/test) — `version` +
  `scan`/`vulnerabilities` per the live schema; severity mapped to Title-case;
  `identifiers` carry the Darkmoon category, an enriched CWE, CVE and MITRE
  ATT&CK id; `location.file` = endpoint path; `description` = `title` only;
  `solution` = `remediation`.

## Safety (§4) honoured

- The finding `description`/`evidence` (which can quote target infrastructure)
  is **never** copied into the Code Quality or SAST reports — only the `title`
  and generic metadata. `darkmoon-ci findings` is already redaction-safe
  (`evidence: null`); the component narrows further to the title.
- The `raw` backend object is never read, logged or emitted (per the client's
  safety contract).
- The full report (`darkmoon-ci report`, redacted) and the normalized findings
  JSON are attached only when `expose-full-report: true` (internal, opt-in).
- Secrets come from masked+protected CI/CD variables via the environment, never
  argv, never echoed.
