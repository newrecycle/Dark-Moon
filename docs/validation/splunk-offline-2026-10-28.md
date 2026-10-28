# Splunk offline verification — 28 October 2026

Source implementations: `7ac6cda` (forwarder/dashboard) and `f1d52ed`
(alert/setup), followed by the source corrections and gate in this checkpoint.
The user explicitly requested that the coordinating worker implement and run
both previous verification prompts before proceeding to the next feature.

## Observed local results

| Command | Result | Actual boundary |
| --- | --- | --- |
| `python -m unittest discover -s integrations/upstream/splunk/test -p 'test_*.py' -q` | 56 passed, no skips | stdlib mocks, real owned-loopback HTTP/TLS, process quota and actual GNU-tar package |
| `node --test integrations/upstream/splunk/test/setup_contract.cjs` | 13 passed | actual setup script in Node VM with mocked DOM/SplunkJS callbacks; failed/uncertain/concurrent saves |
| `python integrations/upstream/splunk/test/test_alert_action.py` | all seven assertions passed | disposable subprocess dry-runs and quota state; no assessment |

Regressions fixed: verified transport accepted port zero; aggregate parent
metadata could supply a comparison verdict/title/current finding; duplicate
CSV headers silently selected the wrong allowlist column; the packager's
listing pipeline could fail with SIGPIPE after creating its archive.
The old branch tests' three-collection assumptions were updated to the actual
five-collection contract without weakening authentication or result guards.

## Reproduction and hosted gate

`.github/workflows/splunk-verification.yml` runs the full suite/setup/legacy
guards on Linux and the alert/setup subset on Windows. Linux requires OpenSSL
for the temporary owned TLS certificate. Windows deliberately excludes the
POSIX special-file case; its process-lock admission and setup tests still run.
Observed hosted results and the two checkout failures are recorded below.
Each result is scoped to its named commit and actual test boundary.

## Remaining limits

No Docker or licensed Splunk host is available in this executor. All test
traffic goes to disposable loopback fixtures; no external service is exercised.

SPL behavior, calculated-field precedence, native SplunkJS password creation,
settings-stanza atomicity/acknowledgement loss, real authentication/permissions,
old credential retirement and proprietary host compatibility remain unverified.
The tests do not execute a scan engine, vendor binary, real HEC destination,
external notification or deployment. Mocked dashboard/SDK checks do not replace
those native boundaries, and no unconditional regression-freedom claim is made.

## First hosted attempt

[Run 40765343877](https://github.com/newrecycle/Dark-Moon/actions/runs/40765343877)
on `fb3eec45e403c9186ed769118324a47956abc087`: the Linux full-contract,
loopback TLS, package, setup and legacy-guard steps all passed. The Windows
job failed before tests during full repository checkout because an unrelated
SDK report fixture includes a colon in its filename. Its new sparse checkout
selects only `integrations/upstream/splunk`; no SDK file is renamed or omitted
from the Linux job. Windows test success remains pending the corrected run.

The [sparse-checkout attempt 40765816714](https://github.com/newrecycle/Dark-Moon/actions/runs/40765816714)
again passed Linux, but Windows Git rejected the unrelated tree path even with
sparse checkout, before any tests ran. The corrected job now consumes only the
portable Splunk source artifact produced by its successful Linux job in the
same workflow. It does not disable NTFS protections or alter other integrations.
Windows test success remains pending the artifact-based run.

## Observed corrected hosted result

[Run 40766256740](https://github.com/newrecycle/Dark-Moon/actions/runs/40766256740)
on `898e4851f04b2a975ea48dabc12ce77bed7e8d7d` passed both jobs.
Linux: 56 Python tests, 13 Node tests, all seven legacy guards, actual package
build and owned-loopback HTTP/TLS checks passed. Windows: 12 alert test methods
ran with the one explicitly POSIX-only case skipped; the other 11, including
the eight-process quota ceiling, passed. All 13 Windows Node setup tests passed.
The same commit's [Tests run 40766256759](https://github.com/newrecycle/Dark-Moon/actions/runs/40766256759)
also passed. These observed results complete the available offline verification
for both source increments; no licensed Splunk host/SPL/SDK claim is added.

## Observed finding-scoped retest result

Feature commit `c92c39958e6b4bcfc0baf03466ef6c6c80f34c98` adds explicit
finding-mode preflight and exact campaign/target guards. Its
[Splunk run 40767933407](https://github.com/newrecycle/Dark-Moon/actions/runs/40767933407)
passed both jobs: Linux ran 65 Python tests with no skips, 13 Node tests and all
seven legacy guards; Windows ran 16 alert methods, with 15 passed and one
POSIX-only skip, plus 13 Node tests passed. Linux includes the new exact-scope
mock cases, real owned-loopback scoped POST and real Operations reference checks
with the launcher mocked. The package check also passed.

The same commit's [campaign isolation run 40767933416](https://github.com/newrecycle/Dark-Moon/actions/runs/40767933416)
passed: its focused preflight reported 20 tests and eight subtests; the full
backend suite reported 420 tests and 209 subtests. Graph navigation and finding
query checks passed. Tests, community SDK/CI contracts, browser acceptance,
webhook offline verification and community runtime validation also passed.
The broader native n8n workflow was still in progress when this entry was
written; no result is inferred for it. These runs do not establish native
Splunk, proprietary scanner or real assessment behavior.
