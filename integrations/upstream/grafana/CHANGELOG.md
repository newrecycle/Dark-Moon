# Changelog

All notable changes to the Darkmoon Grafana integration are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-25

### Added
- **Darkmoon Security Posture** dashboard (Infinity datasource, FREE path) mirroring
  the Darkmoon web app: overview KPIs, findings-over-time by severity,
  severity/status distributions, campaigns & targets tables, full vulnerabilities
  table (filterable), MITRE ATT&CK & category breakdowns, technology inventory,
  remediation pull-requests, and derived retest verdicts (fixed / still_present /
  regressed / new).
- Overview → campaign → finding → evidence-metadata → remediation/retest drill-down
  via dashboard variables and data links.
- Self-contained **Demo** dashboard wired to the bundled synthetic "Demo Shop"
  fixtures — renders instantly with no backend.
- **App plugin** `darkmoon-securityposture-app` with a nested Go backend datasource
  (`darkmoon-securityposture-datasource`) holding the Darkmoon token in
  `secureJsonData`, for the native self-hosted experience (Private signature = free).
- `docker-compose.yml` test lab: Grafana + Infinity + a Darkmoon REST mock serving
  the Demo Shop fixtures.
- Provisioning YAML for the datasource and dashboards.
- CI: `deploy.yml` (idempotent datasource + dashboard provisioning to Grafana) and
  `validate.yml` (Grafana plugin validator on the app plugin).

### Security
- Safe fields only: dashboards NEVER render finding descriptions, evidence, raw
  data, or report bodies. Evidence is surfaced as **counts/booleans only** via the
  `/evidence-meta` endpoint (two-key redaction rule honoured).
- The Go backend re-applies a field allowlist even if the API over-returns.
