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
| `overview`     | `/api/v1/dashboard/overview`          | counts frame + severity/status distribution (long) frames        |
| `campaigns`    | `/api/v1/campaigns`                   | table incl. per-campaign finding stats                           |
| `findings`     | `/api/v1/vulnerabilities`             | table (id, title, severity, status, category, cve, cvss, mitre, endpoint) |
| `targets`      | `/api/v1/targets`                     | table (id, host, risk_level, status, open_vuln)                  |
| `timeseries`   | `/api/v1/metrics/timeseries`          | wide time-series frame                                            |
| `pullrequests` | `/api/v1/pull-requests`               | table (id, provider, repo, number, state, url, finding_ids)      |
| `retest`       | `/api/v1/retest/{retest_id}`          | table (finding_id, verdict, severity, base_status, new_status)   |

## Security: evidence is never exposed

The backend builds Grafana frames **only** from a per-query safe allowlist. A single choke point (`pick()`) hard-denies `description`, `evidence`, `raw`, `logs`, `commands`, `payloads`, `extracted_data` and any token, even if the API over-returns. The bearer token is never logged or written into a frame.

## Build

```
npm install
npm run build          # frontend -> dist/
mage -v build:linux    # Go backend -> dist/gpx_darkmoon_linux_amd64
```

Requires Node 22+ and Go (the module uses the toolchain pinned in `go.mod`).
