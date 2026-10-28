# Splunk snapshot and retest consumer continuation

Date: 28 October 2026. Source baseline: `b8f5bf5` on `pro`. This work leaves the
active Grafana, run-discovery, finding-history verification scopes and the
previous Jenkins workstream untouched. No behavioral tests or native hosts ran.

## Source reconciliation

Two completed independent branches were inspected, without merging their
unrelated parent histories or asserting their test results for this new source:

- `agent/splunk-forwarder-transport-security`, commit
  `7b26130d7eff6af0d8c31a6b68e9530c39741f9e`: strict verified-HTTPS URL admission
  before requests and before bearer headers in REST polling; explicit lab opt-out.
- `agent/splunk-hec-offline-verification-20261028`, implementation
  `a1a34541d1904a7eeef4cf274fefd79156a114f4` and handoff
  `e3140f3bf13de1962b6f140188525eb806ead09b`: safe event/host locators, UTC naive
  timestamps, typed retry/batch configuration and non-retried HEC refusal.

The stricter transport validator and request-boundary checks are retained with
the second branch's projection/admission improvements. Empty query/fragment
delimiters and backslashes are rejected too. HEC responses are size bounded.
Failure messaging acknowledges potentially admitted earlier/uncertain batches.
Existing branch tests/workflows remain available for the verification worker;
they were not copied, rewritten or executed in this integration pass.

## Consumer gap and resulting contract

REST polling previously omitted retests entirely. Aggregate retests could not
populate per-finding searches, and those searches grouped by an optional title
which the fork does not provide. Polling now requires typed responses from five
collections: campaigns, vulnerabilities, pull requests, retests and targets.
Missing/failed support stops preparation before HEC transmission. Export files
can optionally include targets for exact saved-ID host enrichment.

Aggregate retests produce one `record_type=lifecycle` snapshot plus comparison
snapshots. Empty comparisons retain status and references. Completed aggregate
records require explicit arrays; malformed rows, conflicting aliases and
duplicate scoped comparisons fail. Parent references cannot be overridden by
comparison metadata. Original `not_observed` verdicts remain unchanged.
Legacy flat retest rows remain supported.

Comparison metadata retains base/new campaigns, run, target and current finding.
`finding_campaign_id` distinguishes `new` findings in the new campaign from
base findings, and `finding_key` qualifies the finding ID by that campaign.
Ordinary finding observations use the same campaign-qualified key. Unscoped
legacy findings are labeled with a `legacy::` key rather than assigned a campaign.
Local and published remediation records retain explicitly validated finding-ID
arrays (maximum 1000); local record identity remains available for numeric SCM
references without guessing a PR number.

Dashboards separate local proposals, published PRs, lifecycle state and finding
comparisons. Optional title fields are columns, never grouping requirements.
Finding detail uses its scoped key. Search-time keys also cover old indexed
records. Mutable finding filters run after latest-observation selection;
accepted/unknown states remain open and zero denominators stay unavailable.
Simple XML query tokens use Splunk's string quoting filter. Primary reference:
https://help.splunk.com/en/splunk-cloud-platform/create-dashboards-and-reports/simple-xml-dashboards/10.1.2507/drilldown-and-dashboard-interactivity/token-usage-in-dashboards

## Remaining boundaries and verification handoff

- These are metadata snapshots. Repeated polling/retry may repeat ingestion;
  fingerprints are deduplication inputs, not exactly-once delivery guarantees.
- Source timestamps and the selected search window do not establish current
  complete-workspace coverage or observed lifecycle transitions. Latest indexing
  time resolves repeated source timestamps only within the selected window.
- No missing/fixed/deployed verdict is inferred from absence, local validation,
  successful HEC admission, or an empty comparison array.
- Splunk's parser, search-time EVALs, dashboard rendering, native authentication
  and licensed host behavior remain unverified for this combined implementation.
- The existing alert action's credential/session management and scope binding
  remain a separate review item; this increment changes no outbound action code.

Post-commit verification should reconcile both branch test modules, update their
three-collection assumption to five, and add aggregate/flat retest, exact target
join, cross-campaign duplicate finding, multi-link remediation, numeric SCM ID,
locator leakage, empty lifecycle, changed mutable fields and token-escaping cases.
Run only offline fixtures or explicitly permitted disposable hosts. Do not call
real providers, launch assessments, send external HEC/webhook traffic or run
vendor binaries. Record actual source/ref, commands and results; no old isolated
CI run establishes this combined checkpoint's acceptance.

## Local verification implemented — 28 October 2026

The coordinating worker executed the post-commit verification request directly.
The reconciled branch tests now live on `pro`, with five-collection REST
expectations and additional aggregate/flat retest, scoped identity, enrichment,
HEC admission, configuration and package contracts. A real owned-loopback
HTTP fixture exercises polling/projection/batched HEC and authenticated saved
target launches; its TLS fixture checks CA trust and hostname failure/success.

Observed locally: 56 Python tests (including alert/package/loopback contracts),
13 Node setup tests and all seven legacy guard assertions passed. The package
build exposed and fixed SIGPIPE from `tar | head` under pipefail. Regression
tests also fixed port-zero admission, inherited aggregate comparison metadata
and duplicate allowlist CSV headers. No tests start an assessment engine.

Repeatable Linux and Windows-alert jobs are in
`.github/workflows/splunk-verification.yml`. Hosted results are recorded in
`docs/validation/splunk-offline-2026-10-28.md` when observed; a pending workflow
is not a pass. Native Splunk/SPL/SDK acceptance remains unverified: this runtime
has neither Docker nor a licensed Splunk host. XML/stanza/DOM-service checks
are not relabeled native acceptance.
