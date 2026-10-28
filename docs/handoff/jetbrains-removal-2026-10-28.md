# JetBrains integration — intentional removal (2026-10-28)

**Product decision:** This fork no longer maintains, ships, tests, publishes, advertises, or supports a JetBrains/IntelliJ IDE plugin. The standalone JetBrains consumer is optional and was removed without altering the backend, shared TypeScript SDK/CLI or retained consumers. No marketplace operations or user IDE changes are authorized.

## Git and source provenance

- Authoritative branch: `pro` in `newrecycle/Dark-Moon`.
- Baseline inspected before editing: `f1408942d7b89ed52c66015d370132b7fa59eb64` (2026-10-28).
- Upstream JetBrains source, **historical only:** `https://github.com/ASCIT31/darkmoon-jetbrains.git` at `8e54c5375261f9c0243e5cb3c63e79ad2ad7289d`, MIT. Its original `LICENSE` and its former bridge/client Zod license applied to the deleted subtree; license notices and snapshot manifests for retained Jenkins, Action, VS Code and SDK distributions are unaffected.
- Original patch snapshots and previously executed validation records remain accessible through immutable Git history and historical audit documents. This is not history rewriting and no upstream marketplace artifact was changed.
- Work used GitHub Git-object staging against the inspected remote tree because the working environment cannot resolve GitHub for a local `git clone`. No existing local worktree/index, uncommitted user changes or other worker files were modified. Publication requires a non-forced, expected-head compare-and-swap ref update.

## Removed from the active tree

- Entire `integrations/upstream/jetbrains/` tree (68 tracked blobs): Gradle root/client builds, Kotlin client/UI/service and tests, native plugin.xml/icons/messages, Gradle wrapper, bundled portable SDK + Node bridge, fixtures and all subtree-specific licenses/resources.
- `.github/workflows/community-jetbrains.yml`.
- `tests/community/Dockerfile.jetbrains-host`, `Dockerfile.jetbrains-host.dockerignore`, `jetbrains-cache.gradle`, and `jetbrains_host.sh`.
- Superseded cross-integration marketing image `docs/pics/integrations.svg`, which still depicted JetBrains.
- JetBrains import record in active `integrations/upstream/SOURCES.json`; the upstream commit/licence provenance is recorded here.
- JetBrains installation/marketplace badges, links and cross-promotions in active README/catalog/support content; active gap-ledger rows are marked **intentionally removed**, not passing or pending. Past technical notes are explicitly labelled superseded.

## Retained without changing functionality

The canonical `integrations/upstream/client` SDK/CLI, Jenkins HPI bundled CLI, GitHub Action, GitLab, VS Code bridge and native tests, n8n, Grafana, Splunk and all server/backend/scanning/remediation/web UI routes remain in place. Java/Gradle are not removed from unrelated components merely for sharing a language/runtime. No real scans, provider calls, external notifications, deployments or marketplace mutations occur as part of this change.

## Verification record and limits

The staging operation deletes only the subtree and enumerated dedicated infrastructure, and modifies only active support/provenance/documentation. Historical benchmark and audit evidence is retained and annotated. The final tree and published diff must be reviewed for dangling live references and accidental changes; actual hosted CI results (if any) should be documented separately from queued checks.

**Meaning of removal:** no active JetBrains consumer is shipped. Past commit history, source-comparison documentation and old audit narratives may still mention the removed plugin to explain its provenance. This is not a statement that the upstream project or historical Marketplace listing has been deleted.

## Observed hosted verification (2026-10-28)

The first removal commit `b6e1067fb08a1d9cea989ba2e37e5a38009df191`
removed 68 integration-subtree blobs plus six dedicated workflow/harness/marketing
files, without deleting any retained shared consumer or backend implementation.
After the hosted reference audit found additional active references, small focused
follow-up commits removed the public backend integration-catalog advertisement,
outdated SDK consumer docs/comments and the golden-generator's Kotlin-specific
comment. The generator and SDK types/behavior were preserved unchanged. The
preexisting historical SDK changelog is explicitly superseded, not rewritten.

The initial [distribution audit 40776644379](https://github.com/newrecycle/Dark-Moon/actions/runs/40776644379)
failed `git diff --check` on a whitespace residue left in the VS Code README;
that line was corrected. The next [audit 40776693068](https://github.com/newrecycle/Dark-Moon/actions/runs/40776693068)
correctly identified active SDK contract/code comments and the backend catalog;
these were corrected without removing the SDK/golden fixtures. The
[final inventory audit 40776843380](https://github.com/newrecycle/Dark-Moon/actions/runs/40776843380)
**passed**: its `git diff --check`, remaining workflow YAML parsing, source
manifest/retained-license consistency and tracked live-reference scan all
succeeded. Historical `docs/handoff`, dated audit records and the superseded
SDK changelog remain evidence, not current product advertisements.

Observed successful relevant hosted checks:
- [Root Tests 40776843396](https://github.com/newrecycle/Dark-Moon/actions/runs/40776843396): success on the audit-fix head.
- [SDK/CI contracts 40776644455](https://github.com/newrecycle/Dark-Moon/actions/runs/40776644455): success on original removal; other SDK source-comment-only follow-up runs should be checked separately.
- [Grafana integration verification 40776644249](https://github.com/newrecycle/Dark-Moon/actions/runs/40776644249), [Splunk offline verification 40776644294](https://github.com/newrecycle/Dark-Moon/actions/runs/40776644294), [campaign isolation 40776644331](https://github.com/newrecycle/Dark-Moon/actions/runs/40776644331) and [browser acceptance 40776644446](https://github.com/newrecycle/Dark-Moon/actions/runs/40776644446): success on original removal.

Longer-running native VS Code, n8n and Grafana host checks were still running
when this paragraph was written; queued/in-progress runs are not recorded as
passing. The environment did not expose a GitHub-reachable local clone or
working tree, so Git-object staging, draft commit comparison and guarded
`pro` publication substituted for local index/worktree operations. No
rebase, forced update, PR or external marketplace mutation occurred.
