# Darkmoon Security Posture — Grafana App

A Grafana **App plugin** (`darkmoon-securityposture-app`) that bundles a **nested Go backend datasource** (`darkmoon-securityposture-datasource`) for the [Darkmoon](https://github.com/ASCIT31) security platform.

It turns Darkmoon's REST API into Grafana dashboards: campaign risk, findings, target exposure, vulnerability trends over time, and remediation pull requests — without ever exposing sensitive evidence.

## Distribution & signing

This plugin is intended for **self-hosting under a Private (free) signature**. It is shipped **unsigned** in this repository. To run it in a locked-down Grafana, either:

- sign it privately with your own Grafana Cloud account:
  ```
  export GRAFANA_ACCESS_POLICY_TOKEN=<your token>
  npx @grafana/sign-plugin@latest --rootUrls http://localhost:3000
  ```
- or allow it as unsigned in `grafana.ini` / env:
  ```
  GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=darkmoon-securityposture-app,darkmoon-securityposture-datasource
  ```

The paid commercial Catalog signature is intentionally **not** pursued.

## Datasource configuration

| Field       | Where            | Notes                                                        |
| ----------- | ---------------- | ----------------------------------------------------------- |
| `baseUrl`   | jsonData         | Darkmoon API base URL, e.g. `https://darkmoon.example.com`  |
| `mode`      | jsonData         | `auto` (default), `oss`, or `pro`                            |
| `darkmoonToken` | secureJsonData | Pro bearer token / JWT. Encrypted; only sent to the backend |

Health check calls `GET {baseUrl}/api/v1/system/info` and reports the detected edition (Pro contract version when available).

## Query types

| queryType      | Endpoint                              | Output                                                            |
| -------------- | ------------------------------------- | ---------------------------------------------------------------- |
| `overview`     | `/api/v1/dashboard/posture` (404 fallback to `/overview`)          | counts frame + severity/status distribution (long) frames        |
| `campaigns`    | `/api/v1/campaigns`                   | table incl. per-campaign finding stats                           |
| `findings`     | `/api/v1/vulnerabilities`             | table (id, title, severity, status, category, cve, cvss, mitre, endpoint) |
| `targets`      | `/api/v1/targets`                     | table (id, host, risk_level, status, open_vuln)                  |
| `timeseries`   | `/api/v1/metrics/timeseries`          | wide time-series frame                                            |
| `pullrequests` | `/api/v1/pull-requests`               | table (id, provider, repo, number, state, url, finding_ids)      |
| `retest`       | `/api/v1/retest/{retest_id}`          | lifecycle/reference frame plus comparison rows, including current_finding_id |

## Security: evidence is never exposed

The backend builds Grafana frames **only** from a per-query safe allowlist. A single choke point (`pick()`) hard-denies `description`, `evidence`, `raw`, `logs`, `commands`, `payloads`, `extracted_data` and any token, even if the API over-returns. The bearer token is never logged or written into a frame.

## Build

```
npm install
npm run build          # frontend -> dist/
mage -v build:linux    # Go backend -> dist/datasource/gpx_darkmoon_linux_amd64
```

Requires Node 22+ and Go (the module uses the toolchain pinned in `go.mod`).

## Fork integration implementation

The app now selects a configured Darkmoon datasource and reads live metadata
through Grafana's backend query API. Overview, campaigns, findings, targets,
30-day trends, published PRs, local proposals and retest status replace the
starter demo pages. The app stores only a default datasource UID. API URL and
credentials belong to the datasource configuration, where the token is encrypted.

Overview prefers this fork's retained-workspace posture endpoint, falling back
to the legacy overview only on HTTP 404. Missing counts remain unavailable;
malformed responses do not become clean empty frames. Sparse trends align on
timestamps with null gaps. Local proposals do not count as published PRs.
Credential health uses a protected campaign read rather than public system info.
Redirect forwarding is disabled, metadata responses are projected, and nested
objects cannot be serialized through scalar fields.

The SDK's Mage build places the nested datasource binary beside its manifest
at `dist/datasource/gpx_darkmoon_<os>_<arch>`. Nested datasource logo assets are
now copied into the package. Build/native verification is deferred to the later
pass; original vendor runtime compatibility is not established by this source.

## Retest and trend consumer follow-up (28 October 2026)

Retest reads accept the fork's initial `verdicts: []` shape before a `findings`
array exists. Lifecycle and exact base/new campaign, target and run references
remain visible with zero comparison rows. Completed records require an explicit
comparison array; malformed rows, conflicting aliases and foreign identities
fail instead of implying a clean result. `current_finding_id` is retained, and
`not_observed` is never translated into a deployed fix.

Datasource panel trends honor Grafana's selected UTC time range rather than
querying all retained campaigns. Explicit `params.from/to` remain supported
without a Grafana range. ISO week buckets use their actual Monday, including
week-year boundaries; invalid week 53 values are rejected. Finding rows include
`campaign_id`, and missing/invalid CVSS scores are null rather than zero.

The app rejects mismatched frame columns and does not silently substitute a
different datasource when an explicit selection is unavailable. Behavioral
checks, frontend types/build, Go formatting/build and native Grafana acceptance
are delegated; this source checkpoint does not establish those results.
