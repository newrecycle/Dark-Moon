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
Hosted runs have not yet been observed at the time this checkpoint is written.
Do not infer success from workflow submission or from an older branch run.

## Remaining limits

No Docker or licensed Splunk host is available in this executor. All test
traffic goes to disposable loopback fixtures; no external service is exercised.

SPL behavior, calculated-field precedence, native SplunkJS password creation,
settings-stanza atomicity/acknowledgement loss, real authentication/permissions,
old credential retirement and proprietary host compatibility remain unverified.
The tests do not execute a scan engine, vendor binary, real HEC destination,
external notification or deployment. Mocked dashboard/SDK checks do not replace
those native boundaries, and no unconditional regression-freedom claim is made.
