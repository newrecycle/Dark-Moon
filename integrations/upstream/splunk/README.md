# Darkmoon Pentest — Splunk App

> **📦 Marketplace status:** Submitted to Splunkbase (app 9875) — **pending approval** (Splunk review, up to 5 business days). Meanwhile, install the `.tar.gz` from [Releases](https://github.com/ASCIT31/darkmoon-splunk/releases).

SOC ingestion for **Darkmoon** AI pentest results over the HTTP Event Collector, plus an
**offensive-validation loop** that triggers a Darkmoon retest/campaign straight from a Splunk
correlation search. Ships CIM-aligned sourcetypes, six SOC dashboards, and a hard-secured
`Send to Darkmoon` alert action.

> **Privacy by design.** Events carry **safe metadata only** — campaign/finding ids, severity,
> status, target reference, MITRE, technology and timestamps. Evidence, secrets, credentials,
> tokens and request/response bodies are **never** ingested. A defense-in-depth index-time
> redaction also strips token-like strings.

App id `darkmoon` · content type **Splunk App** · version **1.0.0** · MIT.

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

Captured from a **real Splunk Docker** instance running this app against the synthetic
**Demo Shop** dataset (zeroed secrets, `demo-shop.local`). No evidence, endpoints or tokens.

**SOC Overview** — posture KPIs (active campaigns, critical/high, confirmed, exploited,
remediation rate), findings over time, severity/status distributions, top exploited assets:

![SOC Overview](https://raw.githubusercontent.com/ASCIT31/darkmoon-splunk/main/docs/screenshots/01-soc-overview.png)

**Findings** — every finding with severity/status/category/target/campaign filters and safe detail:

![Findings](https://raw.githubusercontent.com/ASCIT31/darkmoon-splunk/main/docs/screenshots/02-findings.png)

**MITRE ATT&CK & Technologies** — technique coverage, top techniques, affected technologies:

![MITRE ATT&CK](https://raw.githubusercontent.com/ASCIT31/darkmoon-splunk/main/docs/screenshots/03-mitre-attack.png)

**Campaigns** — assessment campaigns, outcomes and drill-down to findings:

![Campaigns](https://raw.githubusercontent.com/ASCIT31/darkmoon-splunk/main/docs/screenshots/04-campaigns.png)

**Remediation & Retest** — PR states and retest verdicts (fixed / regressed / still_present / new):

![Remediation & Retest](https://raw.githubusercontent.com/ASCIT31/darkmoon-splunk/main/docs/screenshots/05-remediation-retest.png)

**Send to Darkmoon alert action** — the offensive-validation loop wired into a correlation search:

![Alert action](https://raw.githubusercontent.com/ASCIT31/darkmoon-splunk/main/docs/screenshots/08-alert-action.png)

**Set up** — Darkmoon connection; the API token is stored encrypted in `storage/passwords`:

![Set up](https://raw.githubusercontent.com/ASCIT31/darkmoon-splunk/main/docs/screenshots/06-setup.png)

## Install

1. Download the `.spl`/`.tar.gz` from [Releases](https://github.com/ASCIT31/darkmoon-splunk/releases) and
   upload it via **Apps → Manage Apps → Install app from file**. Once approved (app 9875, pending), you will
   also be able to install it from Splunkbase: **Apps → Find More Apps → search "Darkmoon Pentest" → Install**.
2. Restart Splunk if prompted.
3. Open **Manage Apps → Darkmoon Pentest → Set up** to store the Darkmoon Pro base URL and API
   token (needed only for the alert action; ingestion and dashboards work without it).

## HEC ingestion setup

1. **Settings → Data inputs → HTTP Event Collector → New Token.** Name it `darkmoon`, set the app
   context to **Darkmoon Pentest**, optionally route to an index named `darkmoon`.
2. Point a producer at `https://<splunk>:8088/services/collector/event`:
   - **Pro (recommended):** register a Darkmoon webhook (`format=splunk_hec`) targeting the HEC
     URL. The Darkmoon dispatcher formats safe, HMAC-signed envelopes for you.
   - **Anyone:** run the bundled [`forwarder/darkmoon-to-hec.py`](forwarder/README.md).
3. Events land as `darkmoon:campaign`, `darkmoon:finding`, `darkmoon:retest`, `darkmoon:pr`,
   parsed and CIM-aligned (Vulnerabilities data model) by this app.

## Forwarder usage

```bash
export DARKMOON_TOKEN=...        # Pro bearer (poll mode)
export SPLUNK_HEC_TOKEN=...      # HEC token
# poll the Pro REST API and ship safe events:
python3 forwarder/darkmoon-to-hec.py \
  --rest-url https://darkmoon.internal:8443 \
  --hec-url  https://splunk.internal:8088/services/collector/event
# or from a JSON export, or dry-run to stdout:
python3 forwarder/darkmoon-to-hec.py --export export.json --stdout
```

See [`forwarder/README.md`](forwarder/README.md) for the full flag list and the export shape.

## Alert action safety model

`Send to Darkmoon` triggers a Darkmoon retest/campaign from a correlation search — an
**unauthenticated-by-default destructive capability on the Darkmoon side**, so it is hard-secured:

- **Target allowlist** — only hosts in `lookups/darkmoon_targets.csv` can ever be sent; everything
  else is refused (no arbitrary / out-of-scope scanning, ever).
- **Safe-harbor** — non-destructive profile enforced unless a target row explicitly opts in.
- **Auth** — the Darkmoon token is read at runtime from Splunk `storage/passwords` via the session
  key; it is never stored in a `.conf`, log or dashboard.
- **Rate limiting** — token bucket (max launches/hour), hard-capped in the script.
- **TLS verification** — on by default; non-HTTPS Darkmoon URLs are refused while verify is on.
- **Untrusted input** — any target derived from a result row is validated against a strict host/IP
  regex before use (prevents command/SSRF injection).
- **Dry-run ON by default** — nothing launches until you set `dry_run=0`.

Three example correlation searches ship **disabled** in `savedsearches.conf`
(exploited→retest, critical-spike→campaign, regression→retest). Review, restrict the allowlist,
then enable.

## OSS vs Pro boundary

Ingestion and dashboards work with any Darkmoon edition that can emit events. The **alert action**
and the **setup page** call the **Darkmoon Pro** REST API and are **Pro-only** — the open-source
Darkmoon CLI does not expose that API. This app never presents the Pro dashboard/API features as
open source.

## Compatibility

| | |
|---|---|
| Splunk Enterprise | 9.0+ (tested on the latest `splunk/splunk` Docker image) |
| Splunk Cloud | Yes (AppInspect precert + cloud tags clean) |
| Platform | Platform-independent (Simple XML dashboards, stdlib Python) |
| CIM | Vulnerabilities 5.x field mapping |
| Python | Alert action runs on Splunk's bundled Python 3 (`python.version=python3`, `python.required=3.13`) |

## Testing

Real, reproducible tests live in [`test/`](test/):

```bash
# offline (no Docker): safe-field allowlist + alert-action guards + mock launch
python3 test/gen_synthetic.py
python3 forwarder/darkmoon-to-hec.py --export test/fixtures/darkmoon-export.json --stdout
python3 test/test_alert_action.py
python3 test/test_mock_launch.py

# full E2E against REAL Splunk in Docker (parses, dashboards render, no leaks)
cd test && docker compose up -d splunk       # then wait for healthy
bash test/run_e2e.sh
```

AppInspect (Splunkbase cloud vetting mirrors this):

```bash
pip install splunk-appinspect
splunk-appinspect inspect darkmoon --mode precert
```

Latest local run: **0 errors, 0 failures, 0 future-failures** (2 ignorable warnings — the SplunkJS
telemetry notice and the generic "python file present" notice). Report: `docs/appinspect-precert.json`.

## License

MIT © 2026 ASC-IT (SARL) / Darkmoon. See [LICENSE](LICENSE).

## 🎥 Video tutorial

[![Watch the Darkmoon + Splunk tutorial on YouTube](https://img.youtube.com/vi/8w2i8nEBdQQ/maxresdefault.jpg)](https://youtu.be/8w2i8nEBdQQ)

▶ **[Watch the full Darkmoon + Splunk tutorial on YouTube](https://youtu.be/8w2i8nEBdQQ)** — real setup, end to end.

## Darkmoon ecosystem

Darkmoon is an open-source, AI-powered penetration testing platform. It runs a full autonomous assessment and this integration brings the results into your Splunk workflow.

- ⭐ **Flagship (star it):** https://github.com/ASCIT31/Dark-Moon
- 📚 **Docs:** https://docs.dark-moon.org
- 🌐 **Website:** https://dark-moon.org
- 🔗 **Related integrations:** [Grafana](https://github.com/ASCIT31/darkmoon-grafana) 
