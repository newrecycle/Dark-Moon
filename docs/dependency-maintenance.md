# Dependency maintenance on pro

Dependabot opens both routine version-update PRs and security-update PRs against
the default branch, **pro**. There is no staging branch, branch synchronization,
or promotion PR. Review the diff and passing checks, then merge the PR manually.
The former privileged staging/security auto-merger has been removed: routing
routine updates to pro must not silently make them eligible for automatic merges.

`.github/dependabot.yml` has one entry each for GitHub Actions, Python and npm,
with separate version-update and security-update groups. Python covers `mcp`
and `mcp/community`; npm covers the Action, client, n8n, VS Code, Grafana and
Jenkins manifests. Updates retain the weekly Monday 09:00 America/Edmonton
schedule. Each ecosystem allows one open routine PR, so this is up to three
routine queues, not one repository-wide PR limit. GitHub handles security-update
limits independently.

`Dependency PR validation` runs with a read-only token on same-repository
Dependabot PRs to pro. It rejects files outside the supported dependency files
and action-reference updates, runs baseline regressions and the relevant
ecosystem checks. Ordinary integration checks also apply. Validation does not
merge a PR or deploy anything; branch protection/review rules still apply.

Enable dependency graph, Dependabot alerts and Dependabot security updates in
repository security settings if desired. Their enabled state is separate from
this checked-in configuration. No write-token workflow is needed for this flow.

If an existing PR has no validation run, ask Dependabot to rebase/update it, or
inspect its applicable checks before merging. A failed, missing or pending check
is not a successful validation. Existing closed PRs remain historical records;
deleting their branches does not delete the PRs.
