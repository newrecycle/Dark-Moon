# Upstream campaign isolation merge

Scope: merge `6eebee5` and `edfe9cb` from ASCIT31/Dark-Moon into `pro`,
starting at `90e30a4`. The uncorrected dry merge was textually clean but mixed
independent WebUI campaigns when an OpenCode database already contained a root.

## Corrections before merge

- Preserve each explicit WebUI launch ID. Never select the newest global root.
- Pass the caller's complete OpenCode root through `opencode_session_id`, separate
  from the existing privacy `session_id`. The registered campaign plugin uses
  the public `tool.execute.before` hook and native `session.get` API from the
  pinned runtime (`77b3b467`), resolves nested parents, and rejects failed lookups.
- Exact SQLite ancestry supports direct callers supplying a complete child ID;
  missing/migrating databases preserve the supplied identity, without creating a
  database or guessing another root. Direct clients should supply a root ID.
- Keep complete identities, including distinct roots with equal eight-character
  prefixes. Repeated root/child initialization preserves findings, report state
  and the original privacy session, including across midnight.
- MCP callers without a bound identity start a fresh campaign per initialization
  call. They must reuse the returned campaign ID for pushes; repeated calls are
  intentionally not treated as evidence of belonging to the same run.
- Add a campaign-isolation CI gate covering agent Markdown changes, backend
  behavior, native plugin binding and the graph controller.

Validation before merge: 251 tests and 9 subtests passed; the production plugin
passed concurrent-root/nested-child/API-failure tests under Node 24. Chromium
browser acceptance, graph navigation and `tools/check-no-regression.sh` passed.
These checks use disposable state and offline transports; no provider account
login or paid inference is performed.

## Merge validation

The merge retained the corrected campaign implementation when resolving the
single `live_push.py` conflict. Upstream Chromium flags and the production-repo
deployment guard are retained. Its regression tests now pass actual root and
child IDs, including a newer unrelated root, instead of repeating `MCPCONST` as
the only caller identity. Its Tests workflow runs on Markdown-only changes too.

Merged local validation:

- 255 tests and 9 subtests passed, including 13 focused campaign/flag regressions.
- Chromium browser acceptance and the graph controller passed.
- Actual Chromium launched, rendered, accepted an interaction and closed with
  each of the two agent-prescribed argument lists. This is a functional smoke
  test; it does not establish a memory ceiling or prove OOM cannot occur.
- OpenCode 1.19.4 provider catalog, Basic-auth rejection, model readback and
  disposable key write/delete passed. The production campaign plugin resolved
  real root, child and grandchild sessions through the native API while another
  newer root existed, preserving the separate privacy session ID.
- Agent invariant gate and whitespace checks passed.

Hosted campaign isolation and browser acceptance passed for correction commit
`6b48072`. The merge triggers fresh runs, including the image build, native
campaign binding, prescribed browser flags, and owned-loopback analysis. There
is no local Docker client/daemon, so Docker/Compose checks require those hosted
runs. No real provider login or paid inference was performed.
