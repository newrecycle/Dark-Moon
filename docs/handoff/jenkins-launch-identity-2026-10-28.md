# Jenkins exact launch identity — 28 October 2026

Base: `987282698243bd4d890a635c797ffe37ca7199b7` on pro. Scope is the Jenkins
portable CLI overlay, its build/host fixtures and documentation. The shared
SDK, other consumers, server API and OpenCode campaign plugin are unchanged.

## Problem and decision

A single new campaign file could previously be attributed to an unrelated
Jenkins launch. Multiple candidates failed closed, but creation time, filenames
and PROGRAM labels could not prove which engine created a campaign.

Use the actual configured producer's JSON session identity. The pinned OpenCode
`run --format json` emits top-level sessionID and step-start part metadata. The
existing campaign plugin binds dashboard initialization to that verified root,
and the producer stores it as `opencode_session_id`. A private Node relay reads
only the child process's output pipe and passes root/completion metadata over
IPC. No model-supplied PROGRAM text or global newest-run lookup establishes the
binding. Waiting for producer success prevents a completed file from hiding a
later launch error or conflicting session.

Exactly one regular, single-link, bounded campaign record must match the root.
Its record ID must match its filename, it must not represent a subagent, and it
must not predate this launch's filename snapshot. Status reads verify the
binding again. The prelaunch snapshot only rejects replay; it cannot supply an
identity. All identities missing, contradictory or ambiguous cause failure.

The relay discards producer stdout/stderr bodies, bounds a retained JSON line
to 64 KiB, preserves background launch behavior after a start handshake and
bounds startup/engine execution. Both source components are hash-checked and
embedded into the HPI's standalone CLI; agents need no additional source file.
Legacy custom scripts without JSON identity output now fail deliberately.

## Evidence

- Built the standalone agent CLI with the pinned existing esbuild/Zod toolchain.
- **21 Node tests passed** against the built CLI, including two concurrent jobs
  with the same program in a shared data directory, a newer unrelated file,
  stale replay, foreign/missing/duplicate/conflicting roots, failed/time-bounded
  producer, bounded/discarded output, mutable binding, link admission, detached
  launch and one-shot verdict behavior.
- Shell/Python/Node syntax and git whitespace checks passed.
- Added five native HPI Pipeline cases, for 22 total; observed hosted results follow.

## Observed hosted acceptance

Implementation commit: [`5a5ab6eb`](https://github.com/newrecycle/Dark-Moon/commit/5a5ab6eb91fdb8ff38023a39669b5da2fc8523ff).
[Jenkins HPI and native agent integration, run 40815284758](https://github.com/newrecycle/Dark-Moon/actions/runs/40815284758)
completed **success**:

- All **21 bundled-launcher Node tests passed** during resource generation.
- Maven/JenkinsRule: **16 tests, zero failures/errors, one harness-injected test skipped**; build and HPI inspection passed.
- Actual HPI: **95,268 bytes**, standalone embedded CLI verified byte-for-byte.
- Native controller **Jenkins 2.580.2**; remote inbound agent **Node v22.23.4**.
- All **22 real installed-HPI Pipeline cases** matched their required result,
  Warnings NG count, named artifacts and secret/evidence absence checks.
- The unrelated-concurrent-campaign case succeeded with exactly one issue;
  duplicate/missing/wrong/conflicting roots and a failed producer all failed
  without a findings verdict. Existing high/medium/empty/error and missing
  credential/Node gates retained their expected behavior.
- Affected shared community regressions: **49 passed**.

[General Tests](https://github.com/newrecycle/Dark-Moon/actions/runs/40815284719)
and [supported integration distribution audit](https://github.com/newrecycle/Dark-Moon/actions/runs/40815284709)
also passed. The CI's base-image ID probes returned `unreported`; no digest
pinning or reproducibility claim is inferred from the reported host versions.

## Boundaries

The configured launcher and agent storage remain trusted. This is an explicit
process/session binding, not a signature or atomic snapshot across campaign,
finding and report files. A compromised engine/agent can still falsify its own
output. Mutually untrusted jobs need separate agent/container and data storage.
Local process termination cannot guarantee stopping work inside Docker or a
remote launcher. Windows-agent behavior and other host versions are not newly
validated. No live assessment, provider call, external delivery or deployment
was performed by the verification fixtures.
