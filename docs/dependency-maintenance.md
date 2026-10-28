# Dependency maintenance: deps staging and manual pro promotion

## Branch roles

- **pro** is the repository default branch and the protected/manual promotion destination.
- **deps** is the dependency staging branch. Routine Dependabot version-update PRs target **deps**, not pro.
- Dependabot does **not** merge PRs by itself. A separate unprivileged validation workflow tests each candidate; a privileged workflow merges only successful, same-repository Dependabot PRs with the exact tested head SHA into **deps**.
- Only a human merges **deps -> pro**. The automation never merges dependency staging into pro.

Routine updates use the real Python/npm/GitHub Actions directories and weekly grouping. Grouping is per ecosystem/directory rather than one globally shared PR queue. The default-branch security-only entries retain GitHub's security-advisory update coverage; GitHub's security update PRs always target **pro**, not a non-default target branch. Review urgent security PRs separately and promptly.

## Automated flow

1. On Monday, Dependabot checks the configured package managers and opens candidate PRs with **base = deps**. To run sooner, use **Insights -> Dependency graph -> Dependabot -> Check for updates** in GitHub, for each configured ecosystem.
2. `.github/workflows/dependency-staging-validation.yml` runs as a **read-only PR workflow**, obtains the exact changed-file list from GitHub, rejects unsupported changes, and runs the corresponding dependency install/build/test checks. These tests execute dependency code without any write token or secrets.
3. After the *successful* staging validation completes, `.github/workflows/dependency-staging-automerge.yml` runs from **pro**. It executes no PR code, confirms the PR is opened by `dependabot[bot]`, still targets **deps**, comes from this repository, and has exactly the validated head SHA. Only then does it squash-merge into deps. Failed, skipped, stale, draft, or unexpected PRs never get automatically merged.
4. Every push to **pro**, plus a daily reconciliation, runs `.github/workflows/sync-pro-to-deps.yml`. It merges pro **into deps** while keeping unpromoted dependency commits. It does not reset, force-push, or delete either branch. A conflict stops the job for manual resolution rather than dropping changes.
5. After staging, the merge workflow tries to create or maintain a standing **deps -> pro** promotion PR; this is intentionally never auto-merged. Review that PR and click **Merge** when you want the batch. If creation is disabled, use [Compare deps into pro](https://github.com/newrecycle/Dark-Moon/compare/pro...deps?expand=1) and create a PR manually.

## GitHub settings to check

- **Settings -> Security -> Advanced Security** (or **Code security and analysis**, depending on UI): enable Dependabot version updates, Dependabot security updates, and the dependency graph. The installed connector cannot inspect or change every setting.
- **Settings -> Actions -> General -> Workflow permissions**: allow GitHub Actions to write where needed; enable **Allow GitHub Actions to create and approve pull requests** if you want the standing promotion PR created automatically. Keep other workflows least-privileged.
- If branch protection / rulesets apply to **deps**, permit the staging bot's validated merge path, or specify the required checks compatible with it. Requiring human reviews on deps will deliberately stop automation. Do **not** configure deps-to-pro auto-merge.
- Do not set **pro** as Dependabot's `target-branch` for routine updates. Dependabot reads this config from the default branch (`pro`).

## Troubleshooting

- **No updates/PRs:** Dependabot is weekly and only raises PRs when eligible updates exist. Check the Dependabot logs under Insights and the current branch's manifests.
- **Closed earlier PRs:** Reconfigured targets/groups can close old Dependabot PRs; closed/unmerged PRs do not change dependencies and GitHub retains their history.
- **PR open but not staged:** Inspect the **Dependency staging validation** and **Merge validated Dependabot PRs into deps** Actions runs. Failed dependencies, unsupported files, merge conflicts, or permissions block automated merges. Fix the update or stage it manually after review.
- **deps not synchronized:** Inspect **Sync pro into deps** for conflicts or branch permissions. The daily reconciliation retries missed push triggers.
- **No deps -> pro PR:** Check the action warning and repository Actions PR-creation setting. Use the compare link above when necessary.
- **Security alerts:** GitHub security PRs target the default pro branch and are never automatically staged/merged by this routine-dependency workflow.

Important: `GITHUB_TOKEN`-authored merges may not trigger additional push workflows. Validation therefore runs on the original Dependabot PR before the staging merge; daily pro-to-deps sync covers missed sync events. CI remains necessary again when you manually promote deps into pro.
