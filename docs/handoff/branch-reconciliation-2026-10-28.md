# Branch reconciliation — 28 October 2026

Inspected default branch `pro` at `438f3af4b86ab13b943f55067e4b4c8190a7be0c`. No open PRs were present at the initial inventory. All 14 non-default branch tips below are retained as ancestors of the reconciliation commit. Branch names can be removed without discarding their commits.

## Integration decisions

- Nine worker branches had already been incorporated through squash commits. Ordinary three-way merges confirmed their current implementations were present. Conflicts preserve later pro fixes: bounded patch reads, safe lifecycle projections, raw-output clearing, updated Jenkins dependency versions, five-collection Splunk polling, transport validation and recorded acceptance evidence.
- The isolated Splunk claim document is retained as historical evidence and marked reconciled. Its duplicate narrow workflow is superseded by the shared Linux/Windows Splunk gates.
- `deps` has an identical tree to pro; its 24 additional commits are synchronization history. That history is retained, and the branch is retired.
- The remaining Dependabot branch is patch-equivalent to an already squash-merged pro commit; no dependency version is reverted.
- `master`, `old` and `hermes-single-container-merge` are divergent historical architectures. They differ from pro in 889, 936 and 921 files respectively. They omit the current community/integration implementation; master also contains explicit CI-disabling commits, and Hermes replaces the current runtime. These lines are retired with history-only merges, preserving the current pro tree. This records supersession; it does not claim their alternative runtime features were ported.

## Dependency policy

Routine and security Dependabot PRs now target pro directly. Duplicate ecosystem entries are consolidated; grouped routine updates have one open PR per ecosystem. Jenkins npm manifests are included. Read-only validation remains; staging synchronization, promotion PR creation and the privileged auto-merger are removed. Merges are manual so routine PRs are not silently auto-promoted when branch routing changes. See [dependency maintenance](../dependency-maintenance.md).

## Branch snapshot

| Branch | Retained tip | Disposition |
| --- | --- | --- |
| `agent/credential-adapters-access-20261028` | [`c4379931e6`](https://github.com/newrecycle/Dark-Moon/commit/c4379931e66336db26f77142f3db536a9e32d976) | Worker history reconciled |
| `agent/gitlab-native-acceptance-20261028` | [`50b0a8a054`](https://github.com/newrecycle/Dark-Moon/commit/50b0a8a05432b26b89f87791c0d1f44759c3a6fa) | Worker history reconciled |
| `agent/jenkins-native-acceptance-20261028` | [`a2e4679042`](https://github.com/newrecycle/Dark-Moon/commit/a2e46790424ef772e892bfdff467341087e2e0e4) | Worker history reconciled |
| `agent/splunk-forwarder-transport-security` | [`7b26130d7e`](https://github.com/newrecycle/Dark-Moon/commit/7b26130d7eff6af0d8c31a6b68e9530c39741f9e) | Worker history reconciled |
| `agent/splunk-hec-offline-verification-20261028` | [`e3140f3bf1`](https://github.com/newrecycle/Dark-Moon/commit/e3140f3bf13de1962b6f140188525eb806ead09b) | Worker history reconciled |
| `agent/splunk-native-verification-20261028` | [`bccb0cd8b1`](https://github.com/newrecycle/Dark-Moon/commit/bccb0cd8b18806a5dae64ba23d5ecb50884a9223) | Worker history reconciled |
| `agent/vscode-native-acceptance-20261028` | [`4a9c13304a`](https://github.com/newrecycle/Dark-Moon/commit/4a9c13304ac1965f1bb703be3fb82ddd852c2c56) | Worker history reconciled |
| `dependabot/npm_and_yarn/integrations/upstream/jenkins/npm_and_yarn-54d3728c9a` | [`d3500a66cf`](https://github.com/newrecycle/Dark-Moon/commit/d3500a66cf4d850b4f8cd425bb320acdef745f0d) | Already squash-merged |
| `deps` | [`5e9f989d2a`](https://github.com/newrecycle/Dark-Moon/commit/5e9f989d2ab5bee94a21cd13fecc8b0fe6626f11) | Staging history retired |
| `hermes-single-container-merge` | [`abf42cc584`](https://github.com/newrecycle/Dark-Moon/commit/abf42cc584e4603a8c8567bac699e36dd609694b) | Superseded architecture; history retained |
| `master` | [`63250c8359`](https://github.com/newrecycle/Dark-Moon/commit/63250c8359d5ae57274d6aca87905106a08c5e11) | Superseded architecture; history retained |
| `old` | [`c6df39e494`](https://github.com/newrecycle/Dark-Moon/commit/c6df39e4948c41836b199c6286a34167daae248a) | Superseded architecture; history retained |
| `work/evidence-policy-20261028` | [`d5168f80c5`](https://github.com/newrecycle/Dark-Moon/commit/d5168f80c5da2a65e25069f948f4370c45df9b8b) | Worker history reconciled |
| `work/finding-history-durability-20261028` | [`451fd07097`](https://github.com/newrecycle/Dark-Moon/commit/451fd070974cf4521729defe20d6786ea3d83ee1) | Worker history reconciled |

## Cleanup safeguards

The one-time cleanup job checks the exact branch tips in the adjacent JSON snapshot, verifies every tip is an ancestor of pro, rejects branches referenced by open PRs, and deletes only those named refs using an atomic push with expected-tip leases. A changed tip, active PR or rejected deletion stops cleanup. It never rewrites pro or deletes a newly created Dependabot branch. The temporary cleanup workflow is removed after its result is observed.

## Validation

- Full backend suite: **478 tests and 256 subtests passed** (101.06 seconds).
- Splunk offline Python suite: **73 tests passed**; setup contract: **13 Node tests passed**.
- Campaign binding, graph navigation and finding-query Node contracts passed.
- Dependency policy tests: **4 passed**, including read-only pro validation and removal of privileged staging mergers.
- All workflow YAML parsed; temporary cleanup shell/Python syntax passed.
- Disposable Git cleanup checks passed for success, stale tips, active head/base PRs, advanced pro and concurrent-update atomic lease rejection.
- `git diff --check` passed. Runtime source trees under `mcp`, `conf` and `integrations` are byte-for-byte unchanged from the inspected pro commit.

Hosted cleanup and policy CI results will be recorded after publication. No native host revalidation is claimed for this history/configuration-only reconciliation.
