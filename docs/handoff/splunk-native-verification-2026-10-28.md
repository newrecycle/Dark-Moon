# Splunk native acceptance handoff — 28 October 2026

Scope is exclusively `integrations/upstream/splunk/`, two new dedicated
GitHub workflows, and this handoff/validation record. The source was staged on
the isolated branch `agent/splunk-native-verification-20261028` from
`pro` commit `f1408942d7b89ed52c66015d370132b7fa59eb64`. Existing
Splunk offline Linux/Windows tests and finding-scoped retest cases are
preserved. No unrelated integrations were modified.

## Native evidence boundary

**Native Splunk acceptance is UNAVAILABLE at this checkpoint**: no
operator-provided disposable, already-licensed Splunk host, management
credentials, HEC token, Splunk Web session or self-hosted runner were provided.
The new manual-only native workflow has not run against a Splunk service.
It must NOT be described as passing. The existing Linux/Windows runs were
mock/owned-HTTP fixture tests, not native Splunk searches or SplunkJS behavior.

The native workflow does not download commercial Splunk, set acceptance
arguments, obtain licenses, accept license/terms prompts, run proprietary
Dark Moon runtimes, trigger external notifications or send HEC to other hosts.
The native runner requires explicit operator attestation and literal-loopback
URLs. An absent host is an unavailable prerequisite (exit code 3), not a
passing native search/UI gate.

## Implemented acceptance path

- `test/native_acceptance.py` validates the **built package**, installs it
  using the operator-staged, local-server archive, queries **native**
  app/views/alert/config resources, indexes ten safe test observations to
  a loopback Splunk HEC and waits for them through **actual native SPL**.
  It asserts search-time field extraction and calculated-key precedence,
  CIM aliases, severity normalization, separate campaign-qualified findings,
  latest-before-status semantics, empty native searches, real lifecycle
  and `not_observed` handling, and separate local proposal/PR sourcetypes.
  A missing search result, native API error or malformed response fails.
- `test/native_fixture.py` is an owned-loopback Dark Moon metadata service.
  It can return valid, empty, unavailable, malformed, foreign-scope and
  contradictory launch responses. Its only accepted POST has the exact
  synthetic target/campaign/finding and safe-harbor scope. It does not
  execute assessments or publish outcomes.
- `test/native_browser.cjs` exercises **native Splunk Web and SplunkJS**
  token creation and exact realm lookup, old generation preservation,
  concurrent saves, failed credential creation and an actual settings
  write with intentionally lost acknowledgment. It also verifies native
  dashboard registration/drilldown and remediation views.
- `test/native_action.py` calls the **installed** Splunk action via
  `splunk cmd python3`, authenticating with a real native Splunk session.
  It tests exact preflight and selected finding, refuses empty/broken/foreign
  metadata, rejects conflicting launch identities, and exercises the
  eight-attempt rolling quota against only the owned local fixture.
  Diagnostics assert that session keys and test tokens are not emitted.
- `.github/workflows/splunk-native-host.yml` is *manual only* and uses
  a preauthorized self-hosted `splunk-native-disposable` runner. It runs
  all three native phases sequentially, not a syntactic substitute.
  `.github/workflows/splunk-native-offline.yml` preserves the full
  previous Linux Splunk suite, setup Node tests and legacy alert guards
  plus the new fixture/prerequisite tests, with **explicit** native unavailable
  reporting. The existing `splunk-verification.yml` remains unchanged.

The full setup and version/permission dependencies are documented in
[the native acceptance runbook](../../integrations/upstream/splunk/test/NATIVE-ACCEPTANCE.md).

## Source defects found and repaired

1. `default/macros.conf` had `index=darkmoon OR index=main
   sourcetype=darkmoon:*` without grouping. The OR branch could include
   unrelated indexed data from `index=darkmoon`. The macro now explicitly
   groups the indexes and applies `sourcetype=darkmoon:*` to both.
2. `default/props.conf` was missing both defense-in-depth redaction
   SEDCMD rules on `darkmoon:remediation`, unlike the other ingested
   sourcetypes. The local remediation rules now match the finding rules.
3. `darkmoon_findings.xml` offered severity `info`, while its
   `props.conf` calculated-field output is `informational`. The
   filter now uses the native calculated value, with matching color mapping.

The new offline regression tests assert these source contracts. The native
test will independently fail if the effective installed macro, native
field alias/EVAL or dashboard selection differs.

## Acceptance limitations still outstanding

The host is mandatory to establish effective Splunk conf layering,
calculated-field precedence, SPL parser/SDK behavior, actual app installation
and Splunk Web UI forms. Supported Splunk Enterprise 9.x/10.x, bundled Python
versions, SplunkJS permissions, old credential realm visibility, default
indexes, HEC availability, app-install API behavior, host TLS trust, search
processing delay and app restart needs vary by version. A single successful
host test is not proof of Splunk Cloud or cross-version parity.

The native harness intentionally uses an unlicensed-fork-independent local
Dark Moon fixture. It cannot prove behavior of a proprietary vendor Dark Moon
service or a real assessment. Host/manual restart/fixture operator permissions
and actual browser selector differences may expose defects when a host
becomes available; document and fix them rather than treating skipped cases
as passes. User approval is required before running the manual native host
job on their legally usable host.
