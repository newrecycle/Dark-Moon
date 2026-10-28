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
