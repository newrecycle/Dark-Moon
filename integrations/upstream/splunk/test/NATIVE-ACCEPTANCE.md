# Native Splunk acceptance — operator-supplied disposable instance

This is **not** an emulator, a Docker license bootstrap or the historical
`run_e2e.sh`. The native gate intentionally cannot pass on GitHub-hosted
runners without an authorized Splunk Enterprise installation. **Do not run
`docker-compose.yml` to acquire/accept licenses or vendor terms.** No
proprietary Dark Moon binaries are executed.

## Required operator preparation

1. Provide an already licensed, legally usable **disposable** Splunk Enterprise
   host and consent to installing/replacing the open-source `darkmoon` app,
   indexing ten synthetic metadata records, and creating temporary encrypted
   fixture credentials. The workflow does not accept terms, install Splunk,
   enable alerts, publish PRs, contact targets, or run assessments.
2. Run the CI agent **on the same loopback host** as Splunk management HTTPS
   (:8089), Splunk Web (:8000, HTTP or HTTPS), and its HEC listener (:8088).
   No non-loopback destination is accepted by the native runner. Preconfigure
   an HEC token with permission for the disposable `main` index (or specified
   dedicated index), enable HEC, and preinstall Python 3.11+, Node and
   Playwright/Chromium. The Linux agent should run as the Splunk OS user when
   executing the installed alert action, with write access to its quota dir.
3. Provide Splunk administrator credentials with app-install, search, saved
   searches, settings and `storage/passwords` edit/list permissions. The
   test uses synthetic `fixture-darkmoon-token`, saved under a fresh opaque
   realm. A **fresh quota** is required: `$SPLUNK_HOME/var/run/darkmoon/ratelimit.json`
   must not exist before native alert testing. Do not erase an existing quota.
4. Provide an absolute writable server-local path in
   `SPLUNK_NATIVE_PACKAGE_FILE`, e.g. `/tmp/darkmoon-native.spl`. The
   operator runner builds the current package with `scripts/package.sh`,
   stages the exact result at that path, then asks Splunk's supported app
   REST endpoint to install/update that **server-local** archive. No
   external URL-based app installation occurs. If a version requires a
   manual restart, finish that restart before rerunning. The harness itself
   does not restart services or accept terms.
5. Configure the **manual-only** GitHub workflow
   `.github/workflows/splunk-native-host.yml` on a self-hosted Linux runner
   carrying label `splunk-native-disposable`, and protect the matching
   GitHub environment `splunk-native-disposable`. Settings/secrets:

| Variable/secret | Required | Meaning |
| --- | --- | --- |
| Variable `SPLUNK_NATIVE_ATTESTED` | yes | Exactly `1`, operator asserts the host is licensed/disposable |
| Variable `SPLUNK_NATIVE_MGMT` | yes | `https://127.0.0.1:8089` (or literal `::1`) |
| Variable `SPLUNK_NATIVE_WEB` | yes | `http://127.0.0.1:8000` (or HTTPS) |
| Variable `SPLUNK_NATIVE_HEC` | yes | `https://127.0.0.1:8088/services/collector/event` |
| Variable `SPLUNK_NATIVE_SPLUNK_HOME` | yes | Absolute preinstalled, running Splunk home |
| Variable `SPLUNK_NATIVE_PACKAGE_FILE` | yes | Absolute same-host archive staging path |
| Variable `SPLUNK_NATIVE_INDEX` | optional | Dedicated index or `main`; `darkmoon` must be searched by macro if selected |
| Variable `SPLUNK_NATIVE_CA_FILE` | optional | Trusted CA for local HTTPS |
| Variable `SPLUNK_NATIVE_INSECURE_LOOPBACK` | optional | `1` only on disposable literal-loopback HTTPS |
| Secret `SPLUNK_NATIVE_USER` | yes | Disposable Splunk administrator username |
| Secret `SPLUNK_NATIVE_PASSWORD` | yes | Administrator password |
| Secret `SPLUNK_NATIVE_HEC_TOKEN` | yes | Local HEC token, never sent remotely |

Only trigger **Splunk native host acceptance** manually. If the runner, secrets,
license/host authorization or other prerequisites are absent, **native status is
UNAVAILABLE**, never PASS. With no matching self-hosted runner, GitHub Actions
may remain queued; this is also **not** an acceptance result.

## Distinct gates and observed behavior

`python3 test/native_acceptance.py --native` installs the current packaged
app (using the staged local archive), retrieves **native** app registration,
dashboards, saved searches, macros and alert-action registration; indexes
synthetic metadata to the **real local Splunk HEC**; executes real native SPL
with search-time field aliases/EVALs, hostile indexed finding-key override,
campaign-qualified identities, newest-state filtering before status predicates,
valid empty searches, running/completed retests, `not_observed` without
fixed inference, and separate local proposal/published-PR source types.

`python3 test/native_fixture.py` exposes only a disposable owned-loopback
Dark Moon REST stub with exact target/campaign/finding metadata and controlled
empty, unavailable, malformed, foreign and malformed-response modes. It never
runs a target assessment and never sends notifications.

`node test/native_browser.cjs` uses actual **Splunk Web and SplunkJS**, not
the existing offline Node VM. It tests credential creation, exact selected
realm lookup in `storage/passwords`, failed storage writes, concurrent setup
saves, successful-but-unacknowledged settings writes, retention of old
generations, and live dashboard finding drilldown/registration. Fault-injected
503s are clearly distinct from real Splunk successes and are not native
vendor outages. Restores the synthetic fixture token for the alert test.

`python3 test/native_action.py` invokes the **installed** custom action with
the native Splunk Python runtime (`splunk cmd python3`), authenticates
against the local Splunk management API, and checks exact target/campaign/
finding preflight and POST against the local fixture. Malformed, unavailable,
empty and foreign metadata refuse; a contradictory launch acknowledgment
refuses; the ninth attempt exceeds an eight-attempt rolling quota. No
executable or network target beyond the loopback fixture is exercised.
Raw credentials, tokens, session keys and response bodies are not logged.

## Existing offline guarantees retained

The `splunk-verification.yml` Linux/Windows workflow now owns the consolidated
offline and native-prerequisite gate. It runs the complete
Python/loopback/package suite, all 13 Node setup tests and seven legacy alert
guards, plus new static prerequisite and fixture checks. Its expected
`native_acceptance.py --native` exit code **3** proves *UNAVAILABLE* for
missing host access, never native compatibility.

All flows are independent of any proprietary Dark Moon vendor runtime. Native
success is **limited to the exact installed Splunk version, host, permissions
and package checksum**; Splunk Cloud, non-loopback deployments, other
Splunk/SDK versions, GUI variations and production apps require separate
operator approval and testing. Search-time precedence, search ingest timing
and binary alert dispatch can differ across supported versions.

## Failure and evidence rules

- Exit **0** from every actual native phase (including Web and installed
  Python-action phase) is required for an end-to-end native PASS.
- Exit **3**, missing prerequisites or a queued runner means UNAVAILABLE.
- Other nonzero exit, missing native SPL results, permission errors or
  missing UI selectors are failures, **not** skipped/passed.
- GitHub checks of source, package XML/DOM, mocked callbacks, and synthetic
  HTTP fixtures never establish native behavior.
- Keep all GitHub logs and CI artifacts free of host names, actual passwords,
  session keys, tokens, raw HTTP bodies and indexed evidence. Disable
  screenshot/video traces for credential screens. Use this repo's
  `docs/validation/` records for observed-run IDs only.

The offline package preflight accepts an ordinary top-level `darkmoon/` directory,
requires the shipped application assets and refuses traversal, duplicate names,
local overrides, links and oversized expansions before contacting a host. Every
HEC admission response, including the first lifecycle event, must return code 0.
These checks and forwarder tests are offline evidence, not a native Splunk pass.
