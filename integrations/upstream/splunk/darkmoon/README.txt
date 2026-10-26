Darkmoon Pentest — Splunk App
=============================

SOC ingestion for Darkmoon AI pentest results (via HTTP Event Collector) plus an
offensive-validation loop that triggers a Darkmoon retest/campaign from a Splunk
correlation search.

Author:   ASC-IT (SARL) / Darkmoon
Version:  1.0.0
License:  MIT (see LICENSE)

What it does
------------
* Parses Darkmoon JSON events into clean, CIM-aligned sourcetypes:
  darkmoon:campaign, darkmoon:finding, darkmoon:retest, darkmoon:pr.
* Ships SOC dashboards (Simple XML): SOC Overview, Findings, MITRE ATT&CK &
  Technologies, Campaigns, Remediation & Retest, and a Setup & Help page.
* Provides a hard-secured custom alert action, "Send to Darkmoon", that launches
  a retest/campaign against an ALLOWLISTED target only.

Privacy / safety
----------------
Events carry SAFE metadata only: campaign/finding ids, severity, status, target
reference, MITRE, technology and timestamps. Evidence, secrets, credentials,
tokens and request/response bodies are NEVER ingested. A defense-in-depth SEDCMD
also redacts token-like strings at index time.

The alert action enforces: target allowlist (lookups/darkmoon_targets.csv),
safe-harbor (non-destructive default), token from storage/passwords, rate
limiting, and TLS verification. Dry-run is ON by default.

Edition note
------------
Ingestion and dashboards work with any Darkmoon edition that can emit events.
The alert action and setup page call the Darkmoon Pro REST API and are Pro-only;
the open-source Darkmoon CLI does not expose that API.

Setup
-----
See the in-app "Setup & Help" dashboard, or the repository README.
