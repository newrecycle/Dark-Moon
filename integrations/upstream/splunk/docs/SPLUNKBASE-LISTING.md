# Splunkbase listing — paste-ready

Content to paste into the Splunkbase submission form (app id **9875**, name **Darkmoon Pentest**).
This is the *listing* copy — it is **not** shipped inside the app tarball (Splunkbase metadata is entered on the web form).

**Package to upload:** `dist/darkmoon-1.0.0.tar.gz` · **Content type:** Splunk App · **Hosting:** Splunkbase · **Access:** Public

---

## App name
Darkmoon Pentest

## Short description
Ingest Darkmoon AI-pentest results into Splunk over HEC and trigger a Darkmoon retest/campaign from a correlation search. CIM-aligned sourcetypes, SOC dashboards, and a hard-secured alert action. Safe metadata only — never evidence or secrets.

## Long description
Darkmoon Pentest brings your Darkmoon AI penetration-testing results into Splunk and closes the loop back to Darkmoon.

Ingestion: a producer (the bundled forwarder, or a Darkmoon Pro webhook) sends safe, JSON events to the HTTP Event Collector. The app parses them into CIM-aligned sourcetypes (darkmoon:campaign, darkmoon:finding, darkmoon:retest, darkmoon:pr) mapped to the Vulnerabilities data model. Events carry safe metadata only — campaign/finding ids, severity, status, target reference, MITRE ATT&CK, technology and timestamps. Evidence, secrets, credentials, tokens and request/response bodies are never ingested, with index-time redaction as a second line of defense.

Dashboards: six SOC views — Overview KPIs, Findings, MITRE ATT&CK & Technologies, Campaigns, Remediation & Retest, and Setup & Help — with drill-down.

Offensive-validation loop (Darkmoon Pro): the "Send to Darkmoon" alert action launches a retest or campaign from a Splunk correlation search, hard-secured with a target allowlist, safe-harbor default, token stored in storage/passwords, rate limiting, TLS verification and a dry-run default. Three example correlation searches ship disabled.

The alert action and setup call the Darkmoon Pro REST API and are Pro features; ingestion and dashboards work with any Darkmoon edition that can emit events.

## Categories (pick 2)
- **Security, Fraud & Compliance**
- **Vulnerability Scanner**
(alternatives: SIEM, Threat Intel — max 2)

## Summary (App-description form, min 800 chars)
Darkmoon Pentest brings your Darkmoon AI penetration-testing results into Splunk and closes the loop back to Darkmoon.

A producer — the bundled forwarder or a Darkmoon Pro webhook — sends safe JSON events to the HTTP Event Collector. The app parses them into CIM-aligned sourcetypes (darkmoon:campaign, darkmoon:finding, darkmoon:retest, darkmoon:pr) mapped to the Vulnerabilities data model, so findings sit alongside the rest of your security data. Events carry safe metadata only — campaign and finding ids, severity, status, target reference, MITRE ATT&CK technique, technology and timestamps. Evidence, secrets, credentials, tokens and request/response bodies are never ingested, with index-time redaction as a second line of defense.

Six SOC dashboards give analysts an immediate picture: an Overview of KPIs and posture, Findings with full filtering, MITRE ATT&CK and Technology coverage, Campaigns, Remediation and Retest tracking, plus Setup and Help. Every panel drills down from posture to campaign to finding.

For Darkmoon Pro users, the "Send to Darkmoon" alert action turns Splunk into an offensive-validation trigger: a correlation search can launch a retest or a new campaign, hard-secured with a target allowlist, a safe-harbor default, a token stored encrypted in storage/passwords, rate limiting, TLS verification and a dry-run default.

Ingestion and dashboards work with any Darkmoon edition that can emit events; the alert action and setup use the Darkmoon Pro REST API.

## Details (form field)
Dashboards (app nav):
- SOC Overview — active campaigns, critical/high, confirmed and exploited findings, remediation rate, retest verdicts, findings over time, top exploited assets.
- Findings — filter by severity, status, category, target and campaign; CVSS, CVE and MITRE. Safe metadata only.
- MITRE ATT&CK & Technologies — technique coverage, top techniques, affected technologies, technique×severity heat map.
- Campaigns — per-campaign risk, findings and outcomes, with drill-down.
- Remediation & Retest — pull-request states and retest verdicts (fixed, still_present, regressed, new) over time.

Data model: sourcetypes darkmoon:campaign|finding|retest|pr, CIM-mapped to the Vulnerabilities data model.

Offensive-validation (Pro): add the "Send to Darkmoon" alert action to a correlation search to launch a retest or campaign. It defaults to dry-run and refuses out-of-scope targets.

## Installation (form field)
1. Install the app (Splunkbase, or copy to $SPLUNK_HOME/etc/apps and restart Splunk).
2. Create a HEC token (Settings > Data inputs > HTTP Event Collector) accepting sourcetypes darkmoon:*.
3. Open Setup in the app to store the Darkmoon base URL and API token — stored encrypted in storage/passwords, never in a .conf.
4. Point the bundled forwarder (forwarder/darkmoon-to-hec.py) at your Darkmoon REST API or JSON export, or configure a Darkmoon Pro webhook to POST to HEC.
5. (Pro) For the offensive-validation loop, add the "Send to Darkmoon" alert action to a saved/correlation search and set the target allowlist.

## Troubleshooting (form field)
- No data: confirm the HEC token is enabled and events arrive as darkmoon:* (search: index=* sourcetype=darkmoon:* | stats count by sourcetype).
- Fields not extracted: events must be sent as JSON to HEC, not pre-indexed plain text.
- Alert action does nothing: it defaults to dry-run — disable dry-run once the target is in the allowlist; ensure the Darkmoon URL is HTTPS and the token is set in Setup.
- "Out of scope" refusals: add the target to the allowlist in Setup (safe-harbor blocks anything not explicitly allowed).

## Compatible Splunk versions
Splunk Enterprise 9.0, 9.1, 9.2, 9.3, 9.4 and latest 10.x; Splunk Cloud compatible. Platform-independent (CIM 5.x; alert action uses Splunk's bundled Python 3).

---

## Screenshots (upload from `docs/screenshots/`)

| Order | File | Caption (paste-ready) |
|---|---|---|
| ★ 1 (featured) | `01-soc-overview.png` | SOC posture at a glance: active campaigns, critical/high, confirmed & exploited, remediation rate, retest verdicts, findings over time and top exploited assets. |
| 2 | `02-findings.png` | Every finding with severity/status/category/target/campaign filters, CVSS, CVE and MITRE — safe metadata only, no evidence. |
| 3 | `03-mitre-attack.png` | MITRE ATT&CK coverage, top techniques, affected technologies and a technique×severity heat map. |
| 4 | `04-campaigns.png` | Assessment campaigns with risk, findings, criticals and outcomes; drill down to per-campaign findings. |
| 5 | `05-remediation-retest.png` | Remediation pull-request states and retest verdicts (fixed / regressed / still_present / new) over time. |
| 6 | `08-alert-action.png` | The Send to Darkmoon alert action wired into a correlation search — the offensive-validation loop, hard-secured. |
| 7 | `06-setup.png` | Set up: Darkmoon connection; the API token is stored encrypted in storage/passwords, never in a .conf. |
| 8 (optional) | `07-setup-help.png` | Reference / help. |

---

## Human-only upload step
Sign in to **splunkbase.splunk.com** with the account that owns app id 9875, upload `dist/darkmoon-1.0.0.tar.gz`, paste the copy above, attach the screenshots (feature `01-soc-overview.png`), and submit. Splunkbase cloud vetting mirrors the AppInspect precert, which is already clean (`docs/appinspect-precert.json`: 0 errors, 0 failures).
