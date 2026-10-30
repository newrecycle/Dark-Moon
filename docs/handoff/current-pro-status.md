# Current Pro reintegration status — 30 October 2026

Authoritative current queue for [pro](https://github.com/newrecycle/Dark-Moon/tree/pro).
Dated audits describe their inspected revision, not an active missing-feature
list. Read [commercial API acceptance](commercial-api-parity.md) before claiming
parity. The pinned commercial image is
sha256:48248382877ec1fd7362d2268656956268129d5ea565befab3a24436ea2fc907.

Implementation work has been delivered across all eight workstreams. Acceptance
is not universally closed: the positive model-review test and the unavailable
device/licensed-host/vendor observations below must not be counted as passed.

| Item | Delivered and verified | Remaining acceptance or boundary |
|---|---|---|
| 1. Shared SDK | Own-producer root-session binding; all unbound legacy discovery guesses removed; 106 tests/build; refreshed Action/VS Code archives and provenance; actual GitLab/VS Code consumers passed | Trusted producer storage remains an explicit trust boundary |
| 2. Source picker | Configured approved roots, administrator one-use grants; real Git HTTP and hosted browser acceptance | Approved roots must be operator-controlled |
| 3. Remediation | Scoped worktrees/edits; independent review model/credential configuration; bounded exact before/after source; actual SQLi exploit and variant probes, normal behavior and sandbox restrictions; actual HTTPS Gitea push/PR/readback/idempotency | Positive automatic model-review acceptance remains OPEN: CPU reviewers rejected a valid generated patch; no rejection was overridden |
| 4. UI navigation | All 13 original page surfaces mapped to authenticated independent views; exact-resource navigation, reload/Back/missing states; metadata-first report/proposal access; hosted browser passed | Exact vendor interactions/visual matching remain unverified |
| 5. Analytics | UTC assessment-start windows and preserved drill-downs; explicitly recorded as-of posture; archive/restore/prune; reviewed target-qualified finding identity groups | No invented pre-recording history or between-observation reconstruction |
| 6. Scale/recovery | Dashboard cursor consumer; principal/filter-bound frozen lifecycle pages; explicit retention; verified offline complete workspace backup/restore with quiescent restart and preserved history identities | No live cross-file transaction guarantee; external Git/worktree relocation needs operator review |
| 7. Graph/XR | Normal graph/path acceptance; permission denial, late permission, setup abort, external end, rejected end, shader compile/link cleanup; production lifecycle and browser checks passed | Physical headset rendering; independent exploitation evidence remains assessment-specific |
| 8. Native hosts | Actual CE/Runner, Jenkins, n8n, packaged VS Code; Grafana 10.4.19/13.1 native APIs and all eight app views in Chromium | Native Splunk, licensed Ultimate ingestion, Catalog signing and untested host versions |

JetBrains remains intentionally removed. PBKDF2 authentication, roles,
revocation, scoped evidence grants and manual publication remain intact.
No commercial Pro license is available or to be acquired; none of the 52
original API declarations is vendor-wire verified. Static extraction is not
runtime equivalence.

## Final executable checkpoint

On 18057c8, all four triggered workflows passed:

- Tests 41011660077: 508 tests, 297 subtests, production XR lifecycle and pure
  browser logic checks.
- Community browser 41011660160: routes, authentication, retained/recorded
  posture, assessment windows, frozen run pages and graph/path interactions.
- Runtime 41011660161: actual image/provider API, owned-loopback analysis,
  offline Docker SQLi remediation and actual disposable HTTPS publication.
- Distribution/provenance 41011660102.

The runtime artifact owned-lab-analysis (12958041662) contains
native-remediation.json. Its operator-reviewed publication is distinct from
the optional model-positive gate. Both SQLi variants are blocked after the
parameter-binding fix; normal behavior and sandbox restrictions remain.
A bad patch fails validation; an unavailable image is unreproduced.
The real Gitea PR stays open/unmerged, matches the exact head SHA and base,
leaves original source unchanged, and remains a single PR after a repeated call.
The ephemeral repository mount allows Gitea's generated hooks to execute;
TLS verification is enabled for both client and internal callbacks.

Other affected source checkpoints:

- SDK 4c921ee: all five triggered workflows passed, including actual GitLab
  CE/Runner 41000257766 and packaged VS Code 41000257813.
- Grafana ddf7542: both complete native API/browser matrix legs passed in
  41006932019, including filtering, saved retest, inaccessible source denial,
  protected-content checks and retained desktop/mobile screenshots.
- Native n8n on 64b6961: 41009928358 passed.
- Earlier image/provider, SDK and broad browser/native evidence is retained
  in the dated runbooks; do not imply a path-filtered workflow reran when it did not.

## Remaining acceptance and exact handoff

1. **Positive automatic model review:** real CPU inference produced a correct
   parameter-binding candidate but its reviewers rejected it, including with
   complete source context (41009928342). The production gate stayed closed.
   The positive gate is now an explicit manual workflow input, not a routine
   model-quality requirement on every push. Use
   [the model/forge runbook](remediation-model-forge-acceptance.md) and
   --configured-models with an explicitly selected capable endpoint. Require
   positive review >= .75, rejection of the unfixed control, real probes and
   real publication. The separate operator-reviewed pass does not close it.
2. **Splunk:** no operator-supplied preinstalled disposable licensed host,
   matching self-hosted runner or credentials are available. Do not acquire or
   accept a license. Exact preparation and commands are in
   [native Splunk acceptance](../../integrations/upstream/splunk/test/NATIVE-ACCEPTANCE.md).
   Offline Linux/Windows contracts and native preflight are separate evidence.
3. **GitLab Ultimate:** actual dashboard ingestion needs an appropriately
   licensed instance. No license will be acquired. CE 19.5.1 / Runner 19.5.0
   execution and exact uploaded SAST artifacts are already verified.
4. **Hardware/distribution:** no physical headset or Grafana signing account
   is available. Follow [XR acceptance](xr-device-acceptance.md) if hardware
   becomes available. Unsigned disposable-host loading is not Catalog signing.
5. **Commercial wire comparison:** authentic bodies, defaults, authorization
   and error behavior remain unavailable. Use the complete scenario matrix in
   [commercial API acceptance](commercial-api-parity.md); never fabricate responses
   or bypass activation.

## Reproduction and recovery

Start with the parity runbook's fresh checkout/environment commands. Then read:

- [UI route mapping](ui-route-acceptance.md)
- [Posture observations and reviewed identity](posture-observations.md)
- [Offline complete workspace recovery](workspace-recovery.md)
- [Actual model/Docker/forge acceptance](remediation-model-forge-acceptance.md)
- [Grafana native host boundaries](grafana-host-boundaries.md)
- [CI ownership and exact retained workflows](../ci.md)

Backups must be created with all writers stopped. Restore invalidates sessions
and grants, quiesces work and preserves verified vault/history material; it
does not replay old side effects. Source trust, observed-history limits and
transient observations missed while an external producer is offline remain
explicit operational contracts.
