# Changelog

All notable changes to the Darkmoon Jenkins plugin (`darkmoon-scan`) are
documented here. This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-24

### Added
- `darkmoonScan` pipeline step that drives the `darkmoon-ci` CLI (`run` /
  `summary` / `findings` / `report`) for OSS and Pro backends.
- Findings-based build gate: `failOn` -> FAILURE, `unstableOn` -> UNSTABLE,
  computed from severity counts (never from the pentest process exit code); a CLI
  tool error (exit 1) aborts the build.
- warnings-ng (SARIF) integration for findings visualization via `recordIssues`.
- Redaction-safe by default: the `Finding` model omits any evidence field and
  SARIF carries only title/metadata; the un-redacted report is a two-key opt-in
  (`includeFullReport`, which passes `--full --private`).
- Pro token / OSS license passed via Jenkins Secret-text credentials as env vars,
  never on the command line.
- Licensed under MIT.

### Security
- The published `darkmoon-scan.hpi` contains no lab/demo data. Real Juice Shop
  fixtures live only in the dev-time `src/test/**` and `e2e/**` trees, which are
  not packaged into the HPI.
