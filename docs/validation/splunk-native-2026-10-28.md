# Splunk native acceptance evidence — 28 October 2026

## Current verdicts

| Gate | Observed result | What it establishes |
| --- | --- | --- |
| Existing Linux/Windows Splunk contract workflow | Passed at prior source checkpoints; see `splunk-offline-2026-10-28.md` and finding-scope handoff | Local HTTP/TLS, mocks, packaging, Node VM and quota, **not** native Splunk |
| New isolated-branch offline run [40777200326](https://github.com/newrecycle/Dark-Moon/actions/runs/40777200326) at `f61574e6` | **PASS**: 71 Python tests, Node 13 setup tests, seven legacy alert guards, Python/JS syntax checks | Includes native-boundary preflight, loopback stub and source-defect regression cases; **not** Splunk-host acceptance |
| Host-gated native installation, HEC, SPL, dashboard/SplunkJS and installed alert action | **UNAVAILABLE** | No operator-provided licensed disposable Splunk host, credentials or compatible self-hosted runner were supplied; no native attempt has been executed |

The new offline gate deliberately ran `native_acceptance.py --native`
without host authorization and observed **exit 3, NATIVE UNAVAILABLE**.
The enclosing offline job's PASS means the failure-closed prerequisite check
worked; it **must not** be recorded as a native PASS. The initial isolated
branch run [40777087608](https://github.com/newrecycle/Dark-Moon/actions/runs/40777087608)
failed one new regression: remediation's SEDCMD token pattern omitted the
backslash quoting used by the finding sourcetype. The source was corrected
and the subsequent offline gate passed.

## Reproduction

Offline (all pre-existing and new contract tests retained):

```sh
python -m unittest discover -s integrations/upstream/splunk/test -p 'test_*.py' -v
node --test integrations/upstream/splunk/test/setup_contract.cjs
python integrations/upstream/splunk/test/test_alert_action.py
```

Native host — **manual only**, on an operator-authorized local Splunk runner:

```sh
python integrations/upstream/splunk/test/native_acceptance.py --check
python integrations/upstream/splunk/test/native_acceptance.py --native
node integrations/upstream/splunk/test/native_browser.cjs
python integrations/upstream/splunk/test/native_action.py
```

The browser and action tests require a running `native_fixture.py`, whose
loopback base URL is supplied through `SPLUNK_NATIVE_DARKMOON`. See
`integrations/upstream/splunk/test/NATIVE-ACCEPTANCE.md` for package staging,
license/host prerequisites, exact environment variable names, permissions,
quota isolation and manual workflow wiring.

No vendor terms were accepted, no Splunk image was acquired, no original
commercial Dark Moon binaries were executed, and no real target assessments,
external HEC destinations, webhooks or notifications were used.

## Native results to record if an operator runs the manual gate

Record the run ID, exact Splunk Enterprise version/build, packaged app archive
digest, OS, native Python/SplunkJS versions, TLS/HEC/index configuration,
prerequisite state and per-phase PASS/FAIL. Preserve the failing stage and
generic diagnostics without raw credentials, session keys, response bodies or
target metadata. If it cannot start, mark **UNAVAILABLE**, never green.

Known unresolved cross-version boundaries include app-install/reload behavior,
effective `props.conf`/EVAL precedence, Splunk Web form selectors, native
`storage/passwords` permissions and old realm retirement, actor/session
behavior in the installed action, and native HEC/search indexing visibility.
