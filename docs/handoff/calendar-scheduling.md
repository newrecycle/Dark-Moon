# Calendar scheduling (S01)

The scheduler now supports one-time, elapsed-interval, daily, weekly and monthly
rules. Daily/weekly/monthly rules support every N periods (1–366), anchored to
the selected first local date/time in an IANA timezone. The schedule display
name is separate from the assessment/program name.

## Timing contract

- Calendar times stay at the selected local clock time across DST changes.
- Nonexistent local times during a forward clock jump are skipped. A one-time
  or interval start at such a time is rejected, so the operator can choose a
  valid start explicitly.
- Repeated times during a backward clock jump run once, using the selected
  first (`fold: 0`) or second (`fold: 1`) occurrence.
- Monthly dates that do not exist are skipped rather than silently moved to
  month-end. Every-N rules remain anchored to the original month/date.
- Missed occurrences coalesce into one claim after restart. Calendar rules
  advance to the next future anchored occurrence; elapsed intervals advance
  from the claim clock, preserving existing interval behavior.
- Overlapping jobs for the same schedule are skipped and recorded. One-time
  claims are consumed, including failed launches, and require explicit re-arm
  or a new schedule to try again. Re-arming uses a new occurrence key.
- Existing records without a rule keep their interval, next-run and one-shot
  behavior. No automatic data migration or reinterpretation is required.

Preview lists up to five occurrences with local offsets and UTC timestamps.
Preview does not create a schedule, queue a job, or contact a target. Past first
occurrences are marked overdue. Calendar calculations explicitly use packaged
`tzdata`, independent of the host OS timezone database. Timezone updates take
effect after an application restart; future civil-time changes use the installed
package's rules. The readiness check includes this dependency.

## Editing and history

The WebUI supports edit, preview, duplicate paused, pause/resume, delete and
history. Changing a rule re-anchors its next occurrence; unchanged rules and
name-only saves preserve the next due time and prior job metadata. The full assessment
scope and saved credential references are retained by the editor. Concurrent
edits require the current integer `version`; stale saves fail explicitly.
Pausing/deleting cannot resurrect a record through a stale scheduler snapshot
or completion callback. A claim already being enqueued or running may continue.

Duplicates get a new ID, start disabled, and inherit no job/history references.
Up to 100 claimed occurrences per schedule are retained, including skipped
overlaps and failed enqueue attempts. History distinguishes enqueue disposition
from the current job status and links to the recorded job/campaign. It does not
fabricate history for runs before this feature. Deleted records' retained
history stays in the private control store; the schedule history route requires
an existing schedule.

## REST additions

Both `/api/v1/scheduler` and `/api/v1/schedules` support the new operations. The
former preserves the SDK's `data` wrapper; legacy schedule responses remain
unwrapped where they were previously unwrapped.

- POST collection: existing flat launch fields, or `{spec, rule, display_name,
  enabled}`. A rule contains `kind`, `timezone`, `start_local`, optional `every`
  and `fold`, plus `seconds` for elapsed intervals.
- POST `.../preview`: same definition; returns occurrences and timing policies.
- GET `.../{id}`: current definition, version and next due time.
- PATCH `.../{id}`: `{version, spec?, rule?, display_name?, enabled?}`. The legacy
  `{enabled: boolean}` toggle remains accepted. UI toggles send a version.
- POST `.../{id}/duplicate`: `{version}`; returns a new paused definition.
- GET `.../{id}/history`: `{data, total}`.
- DELETE `.../{id}`: removes the schedule, not existing jobs.

Mutations and preview require an operator/admin session. Viewers may read
schedules and history. No new external service or automation account is used.

## Validation

295 combined MCP/community tests and 17 subtests passed. Calendar cases cover
Edmonton's historical 2024 spring gap/fall fold, every-two-week anchoring, month-end skips,
leap years, legacy intervals, late starts, restart history, concurrent edits,
simultaneous scheduler claims, bounded overlap history, failed one-shot claims,
explicit re-arm, edit-during-launch and route authorization.

The initial hosted pass exposed newer timezone data than the local system,
which invalidated tests that assumed fixed Edmonton offsets in future years.
Tests now exercise historical DST transitions and check future local/UTC
equivalence without hardcoding future political rules. Packaged timezone data
is used consistently. A follow-up also prevents name-only/full-form saves from
resetting an unchanged recurrence to its original past anchor.

Chromium acceptance covers calendar preview with offsets, monthly creation,
full-scope editing, stale-save rejection, nonexistent-time errors, one-time
conversion, paused duplication, empty history and pause/delete. Desktop and
390px form layouts are inspected through retained fixture screenshots. SDK,
graph and finding-query checks remain part of validation; target execution in
browser tests uses the existing fake launcher.
