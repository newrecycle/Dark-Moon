# Darkmoon Security Posture — Grafana integration

> **🔒 PRO-ONLY — requires the Darkmoon Pro REST API (`/api/v1`).**

> **📦 Marketplace status:** Dashboards + self-host app plugin available here now. grafana.com dashboards library submission **pending publication**.

Visualize your [Darkmoon](https://dark-moon.org) autonomous-pentest results in
Grafana: a **security-posture dashboard** that mirrors the Darkmoon web app —
overview KPIs, findings over time, severity/status distributions, campaigns,
targets, a full vulnerabilities table, MITRE ATT&CK, technologies, remediation
pull-requests and derived **retest verdicts** — with a full
overview → campaign → finding → evidence-metadata → remediation drill-down.

Two ways to run it:

1. **Dashboard + Infinity datasource** (no build, no install) — import one JSON,
   point the [Infinity datasource](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/)
   at your Darkmoon REST API. Works on Grafana Cloud and self-hosted.
2. **Self-hosted App plugin** with a Go backend datasource that keeps your
   Darkmoon token in `secureJsonData` — **Private signature (free)**, for teams
   that prefer a native, token-secured datasource.

> **Safe by design.** The dashboards render **safe fields only** — never a finding
> description, evidence, raw request/response, or report body. Evidence is shown
> as **counts/booleans only** (the Darkmoon two-key redaction rule). All synthetic
> screenshots below use the bundled **Demo Shop** dataset.


## ⭐ Darkmoon ecosystem

Darkmoon is open-source — **a star really helps us grow.** [![Star the Darkmoon core](https://img.shields.io/github/stars/ASCIT31/Dark-Moon?style=social&label=Star%20Darkmoon)](https://github.com/ASCIT31/Dark-Moon)

🌐 **Website:** [dark-moon.org](https://dark-moon.org) · 📚 **Docs:** [docs.dark-moon.org](https://docs.dark-moon.org) · ⭐ **Star the core:** [github.com/ASCIT31/Dark-Moon](https://github.com/ASCIT31/Dark-Moon)

**Install the integrations, right where you work:**

| Platform | Get it |
|---|---|
| VS Code | [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Darkmoon.darkmoon-vscode) |
| JetBrains | [JetBrains Marketplace](https://plugins.jetbrains.com/plugin/34497-darkmoon) |
| GitHub Actions | [GitHub Marketplace](https://github.com/marketplace/actions/darkmoon-pentest) |
| GitLab CI/CD | [CI/CD Catalog](https://gitlab.com/explore/catalog/Dark-Moon-X/darkmoon-scan) |
| Jenkins | [Download the .hpi](https://github.com/ASCIT31/darkmoon-jenkins/releases) |
| Client & CLI | [npm: @darkmoon_ai/client](https://www.npmjs.com/package/@darkmoon_ai/client) |


## Screenshots

Rendered against the synthetic **Demo Shop** dataset (`demo-shop.local`, zeroed
secrets) in a real Grafana via the Infinity datasource. Aggregate/metadata only —
no evidence, no report bodies, no tokens.

**Security posture — overview**

![Darkmoon Security Posture overview](https://raw.githubusercontent.com/ASCIT31/darkmoon-grafana/main/docs/screenshots/overview-full.png)

**Vulnerabilities table** (safe fields only, every column filterable, click a title to drill down)

![Vulnerabilities table](https://raw.githubusercontent.com/ASCIT31/darkmoon-grafana/main/docs/screenshots/vulnerabilities-table.png)

**Findings over time · Severity distribution · MITRE ATT&CK**

![Findings over time](https://raw.githubusercontent.com/ASCIT31/darkmoon-grafana/main/docs/screenshots/findings-over-time.png)
![Severity distribution](https://raw.githubusercontent.com/ASCIT31/darkmoon-grafana/main/docs/screenshots/severity-distribution.png)
![MITRE ATT&CK](https://raw.githubusercontent.com/ASCIT31/darkmoon-grafana/main/docs/screenshots/mitre-attack.png)

**Remediation pull-requests · Retest verdicts**

![Remediation pull requests](https://raw.githubusercontent.com/ASCIT31/darkmoon-grafana/main/docs/screenshots/pull-requests.png)
![Retest verdicts](https://raw.githubusercontent.com/ASCIT31/darkmoon-grafana/main/docs/screenshots/retest-verdicts.png)


## Install — dashboard + Infinity datasource (recommended, no build)

1. **Install the Infinity datasource** (free, Grafana-Catalog-signed):
   Grafana → *Connections → Add new connection → Infinity*
   (`yesoreyeram-infinity-datasource`). On Grafana Cloud it is one click.
2. **Add a Darkmoon datasource** of type *Infinity*. If your Darkmoon Pro API
   requires a token, set **Authentication → Bearer Token** to your Pro / API token
   (stored in `secureJsonData`, server-side only). Optionally set **Security →
   Allowed hosts** to your Darkmoon host (SSRF hardening).
3. **Import the dashboard**: Grafana → *Dashboards → New → Import* → upload
   [`dashboards/darkmoon-security-posture.json`](dashboards/darkmoon-security-posture.json).
4. Set the dashboard variables:
   - **Darkmoon datasource** → the Infinity datasource from step 2
   - **Darkmoon API base URL** → e.g. `https://darkmoon.example.com` (no trailing slash)

That's it — the panels query `‹base›/api/v1/dashboard/overview`,
`/vulnerabilities`, `/campaigns`, `/targets`, `/pull-requests`, `/retest/{id}` and
`/vulnerabilities/{id}/evidence-meta`.

### Instant preview (no Darkmoon backend)

Import [`dashboards/darkmoon-security-posture-demo.json`](dashboards/darkmoon-security-posture-demo.json)
instead — it is pre-wired to the bundled **Demo Shop** fixtures on GitHub raw and
renders immediately with any Infinity datasource.


## Install — self-hosted App plugin (Private signature = free)

For a native, token-secured datasource (Go backend), install the app plugin from
[`plugin/`](plugin/). It is **not** Catalog-signed (that requires a paid commercial
signature for a vendor plugin); run it under a **Private signature** or as an
allow-listed unsigned plugin on your own instance:

```bash
# Grafana config (grafana.ini or env)
GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=darkmoon-securityposture-app,darkmoon-securityposture-datasource
```

Download `darkmoon-securityposture-app.zip` from
[Releases](https://github.com/ASCIT31/darkmoon-grafana/releases), unzip into your
Grafana plugins directory, restart Grafana, enable the app, then add a
**Darkmoon** datasource: set **Base URL** + **Darkmoon token** (kept in
`secureJsonData`). The backend's `CheckHealth` calls `GET /api/v1/system/info` and
reports the edition + contract version. To build from source, see
[`plugin/README.md`](plugin/README.md) (`npm ci && npm run build` + `mage -v build:linux`).


## Local test lab (docker-compose)

```bash
python3 scripts/gen_fixtures.py       # (re)generate the Demo Shop dataset
python3 scripts/gen_dashboards.py     # (re)generate the dashboards
docker compose up                     # Grafana + Infinity + Darkmoon mock
# open http://localhost:3009  (admin / admin) → folder "Darkmoon"
```

The mock (`fixtures/mock_server.py`) serves the exact Darkmoon REST shapes and
honours query filters, so the production dashboard runs against it unchanged.
Pin a Grafana version with `GRAFANA_TAG=10.4.7 docker compose up`.

Automated assertions (data renders + no forbidden field is ever selected):

```bash
bash scripts/test-local.sh
```


## Panels

| Panel | Source endpoint | Type |
|---|---|---|
| Estate KPIs, Active campaigns, Critical/High, Exploited/Confirmed, Remediation rate | `/dashboard/overview`, `/campaigns` | Stat / Gauge |
| Findings over time (by severity) | `/campaigns` (date + stats) | Time series |
| Severity distribution / Status distribution | `/dashboard/overview` | Bar gauge / Pie |
| Last campaigns / Targets at risk | `/campaigns`, `/targets` | Table (drill-down links) |
| Vulnerabilities (filterable, safe fields) | `/vulnerabilities` | Table |
| MITRE ATT&CK / Category breakdown | `/vulnerabilities` | Bar chart |
| Technologies | `/targets` (flattened) | Table |
| Pull requests (remediation) | `/pull-requests` | Table |
| Retest verdicts / Retest detail | `/retest/{id}` | Stat / Table |
| Campaign / Finding / Evidence-metadata detail | `/campaigns/{id}`, `/vulnerabilities/{id}`, `/vulnerabilities/{id}/evidence-meta` | Stat / Table |

**MTTR is intentionally not shown**: the Darkmoon data model carries no
per-finding open/close timestamps, so it cannot be computed honestly.


## Compatibility

| Component | Supported |
|---|---|
| Grafana | **≥ 10.4** (tested 10.4.7, 13.2, 13.3 Cloud) |
| Infinity datasource | `yesoreyeram-infinity-datasource` (free, Catalog-signed) |
| Darkmoon | Pro REST API (`/api/v1`), contract version `1`. |
| App plugin backend | Go (linux/amd64 shipped; build others with `mage`) |


## Security & privacy

- **Safe fields only.** No panel selects `description`, `evidence`, `raw`, `logs`,
  `commands`, `payloads` or `extracted_data`. `scripts/test-local.sh` fails the
  build if any dashboard does. The Go backend re-applies the same allowlist.
- **Evidence = metadata only.** The evidence panel shows presence + counts via
  `/vulnerabilities/{id}/evidence-meta` — never content (two-key redaction rule).
- **Secrets never leak.** The Darkmoon token lives in the datasource
  `secureJsonData` (server-side); it is never returned to the browser, logged, or
  embedded in a dashboard. CI secrets are read from GitHub Actions secrets only.
- **SSRF hardening.** Set the Infinity datasource **Allowed hosts** to your
  Darkmoon host; the Go backend only ever calls its configured base URL.
- Treat all finding/target data as untrusted — tables render data, never HTML.


## CI

- **`.github/workflows/deploy.yml`** — on push to `main`, tag, or manual dispatch:
  idempotently provisions the Darkmoon Infinity datasource + imports the dashboards
  into the Grafana instance defined by the `GRAFANA_URL` / `GRAFANA_SA_TOKEN`
  repository secrets.
- **`.github/workflows/validate.yml`** — builds the app plugin and runs the
  official Grafana **plugin-validator** on it.


## License

MIT © 2026 ASC-IT (SARL) / Darkmoon. See [LICENSE](./LICENSE).

## 🎥 Video tutorial

[![Watch the Darkmoon + Grafana tutorial on YouTube](https://img.youtube.com/vi/L7K-y0HPudk/maxresdefault.jpg)](https://youtu.be/L7K-y0HPudk)

▶ **[Watch the full Darkmoon + Grafana tutorial on YouTube](https://youtu.be/L7K-y0HPudk)** — real setup, end to end.

## Darkmoon ecosystem

Darkmoon is an open-source, AI-powered penetration testing platform. It runs a full autonomous assessment and this integration brings the results into your Grafana workflow.

- ⭐ **Flagship (star it):** https://github.com/ASCIT31/Dark-Moon
- 📚 **Docs:** https://docs.dark-moon.org
- 🌐 **Website:** https://dark-moon.org
- 🔗 **Related integrations:** [Splunk](https://github.com/ASCIT31/darkmoon-splunk) 
