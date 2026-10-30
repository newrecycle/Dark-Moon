> **Current extension:** Window controls and recorded as-of observations are now implemented; see [posture observations](posture-observations.md). Earlier no-window/no-as-of statements below describe their historical checkpoints.

# Record-backed dashboard (D01 / I07)

The WebUI overview uses a server-calculated `posture` object included in the
existing authenticated workspace snapshot. The standalone authenticated
`GET /api/v1/dashboard/posture` returns only this aggregate projection. It
includes IDs, timestamps, classifications and counts, excluding evidence,
report bodies, finding titles/endpoints/descriptions and proposal patches or
validation output. Viewers can read it. Query filters are rejected (400) so a
requested date range cannot silently appear to be applied.

## Cohort and denominators

All values describe **current stored state across all retained records**. There
is no historical-as-of reconstruction or implicit rolling window. Findings
from repeated assessments count separately. Project and target totals count
registered records, including those with no assessment. Campaign/finding totals
count retained rows, including unlinked finding records. The coverage note
reports findings with no registered target or retained campaign.

| Metric | Numerator / population | Meaning and navigation |
| --- | --- | --- |
| Severity share | Findings with the exact severity / all retained findings | Includes all triage states; links to that severity. Missing severity is `unknown`. |
| Active exposure | Findings outside false_positive, remediated, resolved, closed, fixed / all retained findings | Accepted risk and unknown statuses stay active; links to the active cohort. |
| Excluded exposure | Findings in those five states / all retained findings | This is triage disposition, not independent fix verification. |
| Confirmed / exploited | Separate current status counts | Labels may be changed by operator triage; no independent exploitation proof is inferred. Zero counts remain visible. |
| Target risk | Highest recognized active severity for findings whose target_id equals the registered target | Cached target/campaign risk labels are ignored. No active findings means `none`; only unrecognized active severities means `unknown`. |
| Local validation share | Linked proposals with status validated / all linked proposals | Includes queued, failed, rejected and other states in the denominator. An empty denominator displays unavailable, not 0% or 100%. |
| MITRE share | Findings with an exact recorded technique field / all retained findings | One field per finding; missing fields counted separately. No inferred attack coverage or parsing of multi-value strings. |
| Mean recorded duration | Sum of eligible duration_seconds / eligible campaigns | Positive finite recorded durations outside running/queued states; missing, zero, boolean, invalid and nonfinite values excluded. Eligible / total campaign counts are shown. |

A proposal is linked only when both its campaign ID and finding ID match a
retained finding and its campaign exists. Identical finding IDs in different
campaigns cannot cross-link proposals. Every retained linked proposal is one
record in the rate, including multiple proposals for the same finding. The
number of distinct campaign/finding identities with proposals is also shown.
Unlinked proposals are reported separately and remain available in the full
remediation workspace. Local validation does not establish deployment or target
remediation.

Targets rank lexicographically by active critical, high, medium, low and info
counts, then all remaining active findings, then target ID. The initial table
shows ten; Show all and the Targets total expose every registered target.
Finding links use the finding's stored target identity rather than guessing it
from a host or silently reassigning it to a campaign. Latest-assessment buttons
use the target's dated campaign with the newest timezone-aware start; ties use
campaign ID. Undated, naive or malformed dates sort last in assessment history.
Running durations are never presented as completed assessment durations.

## Drill-downs

Finding URL and REST filters now also support `project_id`, `mitre_attack_id`,
and `triage=active|excluded`. These compose with existing search, status,
severity, campaign, target, sort and page controls. Missing status matches
`unconfirmed`; missing severity matches `unknown`. Clear resets all filters,
and reload/login and browser history preserve them. Default list results retain
the existing safe projection. No evidence search is added.

Local proposal links retain `linked=1` and an optional exact `status` in the
remediation route. Their displayed rows match the rate's cohort. Clear returns
to all proposals. Dashboard target/campaign links retain record identity.

The existing SDK `/dashboard/overview` and timeseries contracts are retained;
clients wanting this explicitly defined current-state cohort should use
`/dashboard/posture`. This does not complete P01: other authenticated workspace
and evidence routes still require the redaction/reveal work in the backlog.

## Validation and remaining scope

- Combined MCP/community suite: **308 tests and 17 subtests passed**. The final
  focused posture/query run passed **20 tests and 6 subtests**, covering the
  exact denominators and drill-down filters.
- Thirteen new Python tests cover empty and idle workspaces, orphans, repeated
  identities, stale risk, accepted risk/legacy states, duration eligibility,
  deterministic dates, no source mutation, secret absence in the aggregate,
  ownership isolation, authentication, viewer access and changes after triage.
- JavaScript query tests cover URL round-trip and composed project/MITRE/triage
  cohorts alongside existing 20,000-record sort/page checks.
- Chromium acceptance checks keyboard target navigation, exact target/MITRE/
  project counts, reload/login, filter reset, live triage changes, latest campaign
  navigation, local proposal filters and 390/1440px layouts. Reviewed screenshots
  retain horizontal table scrolling on small screens.
- Official SDK 0.2.0 and legacy Action/VS Code contract tests pass.

Date-window/as-of metrics, deduplicated vulnerability identity across campaigns,
project hierarchy drill-down refinements, independent deployed-remediation
verification and the native Grafana host/plugin remain open. No claim of exact
visual parity with the reference application is made.

## 29 October: campaign-start window API

GET /api/v1/dashboard/posture now optionally accepts one `from` and/or `to`
timezone-aware ISO datetime. The selected campaign-start interval is half-open:
from inclusive, to exclusive. Invalid, blank, duplicate, unknown and reversed
bounds return 400. Undated campaigns are excluded and counted explicitly.
Projects/targets/findings/proposals are restricted to the selected campaigns.
No bounds retains the existing all-retained cohort. Requests remain authenticated.

Example: `/api/v1/dashboard/posture?from=2026-01-01T00:00:00Z&to=2027-01-01T00:00:00Z`.
The result identifies `cohort=campaign_start_window_current_state` and normalized
UTC `window` bounds. This is **current triage for assessments started in that
window**, not historical state as of the end date, distinct-vulnerability
counting, or a deployed-fix claim. The dashboard UI retains its all-retained
view; a window picker and correctly cohort-scoped aggregate drill-downs remain
open. The API does not silently change the UI's cohort.

Run `PYTHONPATH=mcp .venv/bin/python -m pytest tests/community/test_posture.py
tests/community/test_evidence_access.py -q`. Observed local result: 27 passed,
6 subtests. Tests cover UTC-equivalent boundaries, upper-bound exclusion,
empty window, input nonmutation, strict query validation, safe HTTP cohort
metadata and authentication. No vendor response comparison.
