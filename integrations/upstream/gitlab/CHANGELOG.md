# Changelog

All notable changes to the Darkmoon GitLab CI/CD Component are documented here.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-24

### Added
- `scan` component (`templates/scan`) that runs `darkmoon-ci run --json --fail-on`
  against a target and turns the normalized, redaction-safe findings into native
  GitLab reports:
  - `gl-code-quality-report.json` (Code Quality / CodeClimate — MR widget).
  - `gl-sast-report.json` (GitLab SAST security-report schema — Ultimate widget).
- Findings-based fail policy surfaced via the CLI exit code (`2` = policy tripped,
  `1` = tool error); blocking by default, opt-in non-blocking via
  `allow_failure_exit_codes`.
- Auto / OSS / Pro modes; Pro secrets passed via env, never argv.
- Redaction-safe by design: only the finding **title** + generic metadata
  (category, CWE/OWASP, CVE, MITRE id, CVSS) reach the shared reports. The full
  report is an opt-in, off-by-default internal artifact.
- Licensed under MIT.

### Security
- No lab/demo data ships in the component surface (`templates/`, `src/`). Real
  Juice Shop fixtures live only in the dev-time `test/` tree, which is not part
  of the consumed component.
