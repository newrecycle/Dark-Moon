# Independent worker claim — Splunk forwarder verification

**Claimed:** 2026-10-28
**Worker:** ChatGPT — separate from concurrently publishing `pro` workers
**Base:** `8c2d4cf9c47908a8240ad6b6689e822ce6b386db`
**Working branch:** [`agent/splunk-hec-offline-verification-20261028`](https://github.com/newrecycle/Dark-Moon/commit/e3140f3bf13de1962b6f140188525eb806ead09b)
**Status:** Historical isolated verification record. Reconciled into `pro`; later five-collection tests and the shared Splunk verification workflow supersede the isolated workflow. See `docs/handoff/branch-reconciliation-2026-10-28.md`.

## Exclusive work scope

Verify and, only where the contract requires it, correct the offline Splunk HEC forwarder: `integrations/upstream/splunk/forwarder/darkmoon-to-hec.py`. Focus on safe event serialization, HEC admission, TLS/redirect behavior, retry semantics, REST data contracts and published-vs-local remediation identity.

## Owned files

- `docs/worker-claims/splunk-hec-offline-verification-2026-10-28.md` (this claim)
- `integrations/upstream/splunk/test/test_forwarder_contract.py` (new)
- `integrations/upstream/splunk/forwarder/darkmoon-to-hec.py` (scoped fixes only)
- `integrations/upstream/splunk/forwarder/README.md` (scoped notes only)
- `.github/workflows/splunk-forwarder-verification.yml` (branch-specific offline check)

Do not edit shared API dispatchers, handoff ledgers, other workers' tests or their branches. The isolated branch is the sole publication target until the user or coordinating workers approve integration.

## Safety

No live Splunk/Darkmoon calls, vendor binaries, external notification, deployment or assessment. Tests will use static fixtures and stubbed request openers. Never claim vendor runtime parity. Record measured CI outcomes rather than inferring success from source.

## Verification evidence

- [Isolated GitHub Actions run 40665836183](https://github.com/newrecycle/Dark-Moon/actions/runs/40665836183): Python syntax check passed; **15/15** forwarder contract tests passed.
- Implementation commit: [`a1a3454`](https://github.com/newrecycle/Dark-Moon/commit/a1a34541d1904a7eeef4cf274fefd79156a114f4).
- Real Splunk host, vendor runtime and end-to-end network delivery remain unverified.
- The worker did **not** update `pro`; subsequent integration must reconcile with newer `pro` commits without force-push.
