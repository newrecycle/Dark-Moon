# Dependency maintenance

Routine updates use the real Python/npm directories and target deps, with one open version PR per ecosystem and weekly grouping. This is three queues, not a global one-PR guarantee. Security-only entries retain default-branch advisory coverage and explicit security grouping; GitHub security PR limits are separate.

The sync workflow advances deps only when it contains no unpromoted commits. It never forces or resets either branch. Closed unmerged PRs are not approval to incorporate their code. Historical PR records cannot be deleted by deleting branches.

Automatic merging/promotion is not enabled by this checkpoint: the repository needs a tested dependency candidate gate before write automation can safely promote updates. Repository security-alert/security-update toggles cannot be inspected or changed through the available connector administration capabilities; verify them in repository Settings → Security.
