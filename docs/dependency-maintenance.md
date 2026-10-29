# Dependency maintenance: staged routine updates and tested security updates

## Branch policy

- **pro** is the default branch, and the destination for urgent Dependabot security fixes. These security PRs **are automatically merged into pro after all PR checks pass**.
- **deps** stages routine Dependabot version updates. They are merged into deps automatically only after validation and successful PR checks.
- **deps -> pro** is manual. Routine updates are *never* automatically promoted into pro; the promotion PR remains for human review.
- **pro -> deps** synchronization preserves all commits and never force-pushes. Pushes to pro and a daily reconciliation run the sync workflow. The security-update merge workflow also attempts to merge pro into deps directly as soon as it merges a security fix.

The default branch in this repository is pro. GitHub creates security updates against the default branch even when version updates use `target-branch: deps`.

## Automated flow

1. Dependabot opens routine PRs to **deps** and security PRs to **pro**. The ecosystems, schedules and PR limits come from `.github/dependabot.yml`. GitHub treats security PR limits independently of version-update limits.
2. `.github/workflows/dependency-staging-validation.yml` is triggered by Dependabot PRs to **either** branch. It has read-only permissions, checks the complete list of changed files against the supported dependency manifests/lockfiles and GitHub Actions workflow YAML, runs baseline regressions and the applicable ecosystem install, typecheck, test and build checks. Jenkins build dependencies are also checked.
3. When validation succeeds, `.github/workflows/dependency-staging-automerge.yml` runs on the default branch with only the permissions needed to inspect CI and merge. It **does not check out or run any PR code**. It requires an open same-repository PR authored by `dependabot[bot]`, the identical validated commit SHA, and a non-draft state. For **pro**, it requires a genuine Dependabot head branch (`dependabot/*`). In the checked-in configuration all routine version-update groups target deps; consequently pro-targeted Dependabot PRs are handled as the security-update lane. GitHub can truncate long security PR descriptions, so the workflow does not use description text as its classifier.
4. The privileged merge workflow additionally waits for **all** GitHub PR checks to finish and pass (`gh pr checks --watch --fail-fast`), not just its own validation suite. A failed, cancelled, pending-at-timeout or missing check blocks merging. Immediately before merging, it re-checks the exact base and head SHA and uses the merge API's expected-head SHA guard.
5. The workflow **squash-merges** the verified PR: to **deps** for routine updates or to **pro** for security fixes. A security merge into pro immediately attempts a safe server-side merge of pro into deps. If there is a conflict or insufficient permission, neither history is rewritten; inspect the sync workflow and resolve the conflict manually.
6. After routine updates land on deps, the workflow creates or maintains a **manual deps -> pro** PR if permissions permit. Compare at [pro...deps](https://github.com/newrecycle/Dark-Moon/compare/pro...deps?expand=1).

**Important:** Security fixes entering pro automatically is intentional. This is an exception to the manual-promotion rule that applies to routine updates. A grouped Dependabot security PR can update several packages and can include breaking changes. All configured checks must pass, but automated tests cannot prove every behavior is safe.

## Configuration and repository settings

- **Settings -> Security -> Advanced Security / Code security and analysis:** enable dependency graph, Dependabot alerts and Dependabot security updates. Version updates use the checked-in configuration.
- **Settings -> Actions -> General -> Workflow permissions:** permit `contents: write` / `pull-requests: write` for the privileged merge workflow. Enable Actions PR creation only if you want the optional deps -> pro promotion PR.
- Branch protection and rulesets on **pro** or **deps** may require additional status checks and/or reviews. The workflow never bypasses rules or force-pushes; review requirements can still prevent automatic merges.
- Routine version updates for GitHub Actions, pip, and npm target **deps**, with `open-pull-requests-limit: 2` for each configured update entry. Security update entries remain default-branch scoped, and their PR limits are independent.
- **Security classification relies on branch routing:** all routine version-update entries must continue to use `target-branch: deps`. If you add a routine Dependabot entry targeting pro, that PR could also become eligible for automatic merging into pro. Keep the routing invariant and the workflow policy regression CI enabled.

## Troubleshooting

- **No PR created:** Check Dependabot settings and update logs. Routine updates follow their individual schedule and configured limits.
- **PR open but not merged:** Check Actions runs for **Dependency staging validation** and **Merge validated Dependabot dependency PRs**. All available PR checks must pass, and the bot author, allowed base, Dependabot head branch and tested head SHA must match.
- **PR predates these workflows:** Opening the workflow file on pro doesn't retroactively run it on existing PRs. A Dependabot rebase/update of the PR triggers new validation; do not merge without a fresh successful run.
- **CI pending/failing:** Automatic merging stops. Fix or investigate the failed check; it will not silently merge a failing dependency upgrade.
- **No deps -> pro promotion PR:** Enable Actions pull-request creation or manually open the compare link above.
- **deps behind pro after a security fix:** Inspect the automatic server-side merge warning and **Sync pro into deps**. Manual conflict resolution may be needed.

**Workflow permissions:** Dependabot-triggered PR workflows run with a read-only token and no repository secrets. The separate `workflow_run` merger has a write token but never executes PR code. GitHub-token-authored merges don't reliably start ordinary push workflows, which is why the security merger also syncs deps directly and the scheduled sync still runs daily.
