# Finding-scoped Splunk retest actions

28 October 2026. Additive fork feature after the two Splunk verification prompts
were implemented locally and the corrected hosted Linux/Windows gate passed.
The old default action remains `retest_scope=target`.

## Behavior

`retest_scope=finding` requires a retest action, an allowlisted host and exact
base campaign/finding IDs. Optional action parameters `campaign_id` and
`finding_id` override result fields. Otherwise comparison events prefer
`result.finding_campaign_id` to `result.campaign_id`, so an old finding ID is
not accidentally attached to the comparison's newly launched campaign.
`result.finding_id` supplies the selected finding. Malformed/missing input IDs
and combinations are rejected before any launch or credential lookup.

For a live action, after the existing quota/credential guards:

1. Read authenticated target metadata and resolve the allowlisted host to one
   saved target ID (host or IP metadata; ambiguous matches refuse).
2. Read filtered public campaign collection metadata. The selected campaign ID
   must occur exactly once and belong to that target.
3. Read filtered public finding metadata using campaign/target and an ID search
   hint, then require one **exact** finding ID with both scope references.
   No full campaign finding/evidence body is fetched.
4. POST the exact target, campaign and `finding_ids: [id]`, retaining the profile.
   Declared partial/offset metadata, read/auth/shape failures and mismatches stop
   before POST; no fallback to a newer campaign is attempted.
5. Require the launch to confirm its selected base campaign and, if supplied,
   the same `before_ids`. Acceptance still does not establish completion.

Every metadata response is bounded at 8 MiB. No secret or raw metadata body is
logged. The existing TLS/redirect and immutable credential-generation contract
applies to every call. Dry-run uses no network and explicitly labels remote
scope unverified. New UI controls and both finding-oriented example searches
carry this mode; examples stay disabled and dry-run by default.

The fork backend now treats an explicitly missing base as missing, never as an
instruction to choose the target's latest campaign. An explicit target/base
mismatch is rejected before enqueueing. Target-only legacy hostname lookup and
campaign-only calls remain available; saved engagement and safe-harbor scope
remain. A deleted target is a missing resource, not an attempted launch.

## Limits and evidence

This selects the findings used for comparison and their category focus. It does
not guarantee that the assessment executes only one endpoint or one finding.
Original multi-target engagement boundaries are not erased. Metadata/preflight
and POST are separate requests; native/admin mutation races are not claimed
transactionally isolated. Successful launch or `not_observed` is not proof of
exploit retest, deployment or repair, and no vendor wire parity is asserted.

Observed local verification at this feature checkpoint: 65 Python tests passed,
including mocked exact-scope rejection cases, actual owned-loopback scoped POST,
and the real fork Operations reference checks with its launcher mocked. The
seven legacy alert guard assertions passed. The existing 13 Node setup tests
were unchanged; the previous hosted Linux/Windows result is documented in
`docs/validation/splunk-offline-2026-10-28.md`, not claimed as a hosted result for
this later feature. The new feature's hosted gate is recorded only after its
actual run is observed. Native Splunk/SPL/form behavior remains unverified.

Tests use synthetic metadata, temporary files, mocked launchers and owned
loopback servers. They do not contact a provider, execute a real assessment,
send external notifications or run proprietary binaries.
