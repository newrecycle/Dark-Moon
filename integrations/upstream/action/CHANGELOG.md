# Changelog

All notable changes to the Darkmoon GitHub Action are documented here.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-24

### Added
- Official GitHub Action that runs a Darkmoon campaign (OSS or Pro) against a
  target, waits for completion, and gates the workflow on a findings-based fail
  policy (`fail-on`), never on the pentest process exit code.
- Outputs: severity counts, `campaign-id`, `policy-failed`, and report/SARIF paths.
- SARIF 2.1.0 export for GitHub code scanning (redaction-safe: title + metadata
  only, never evidence, `raw`, or extracted data).
- Optional PR comment and step-summary with a redaction-safe severity table.
- Capability-gated live progress (SSE on Pro, polling otherwise); surfaces the
  client's OSS concurrency/collision warnings.
- Two-key opt-in `full-report` writes the un-redacted report to a private runner
  file only (path output), never to logs, SARIF, outputs, or the PR comment.
- Reusable workflow (`.github/workflows/darkmoon-reusable.yml`) and examples.
- Licensed under MIT.

### Security
- The executed bundle (`dist/index.js`) and the vendored `@darkmoon_ai/client`
  tarball contain no lab/demo data. Real Juice Shop fixtures live only in the
  dev-time `src/__tests__` / `test-fixtures` / `e2e` trees, which are not part of
  the action's runtime surface.
