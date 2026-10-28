# Jenkins HPI native verification — 28 October 2026

## Tested artifact and provenance

**Fork revision:** [`a2e46790424ef772e892bfdff467341087e2e0e4`](https://github.com/newrecycle/Dark-Moon/commit/a2e46790424ef772e892bfdff467341087e2e0e4), isolated `agent/jenkins-native-acceptance-20261028` branch.

**Dedicated gate:** [Jenkins HPI and native agent integration — run 40788128120](https://github.com/newrecycle/Dark-Moon/actions/runs/40788128120): **completed success**. The separate [general Tests run 40788128218](https://github.com/newrecycle/Dark-Moon/actions/runs/40788128218) also passed.

- Maven `clean verify`: **16 tests, 0 failures, 0 errors, 1 skipped** (JenkinsRule Pipeline tests included); SpotBugs found zero issues.
- HPI built and inspected: **93,244 bytes**; its plugin JAR contains the patched, standalone `darkmoon-client/darkmoon-ci.cjs` and matches the build output byte-for-byte.
- Native host: **17 Pipeline builds** in the real installed HPI, all expected statuses, Warnings NG issue totals and named artifact checks passed; remote CLI extraction and workspace with spaces verified.
- Affected shared regression: `PYTHONPATH=mcp python -m pytest tests/community/test_community.py -q` — **49 passed in 5.44 s**.
- No commercial runtime, vendor binary, external assessment, provider request, notification or deployment was used.

**Tested host versions:** Jenkins **2.580.2** from `jenkins/jenkins:lts-jdk21`; plugin **0.1.0-SNAPSHOT**; separate inbound-agent image `jenkins/inbound-agent:jdk21` with agent Node **v22.23.4**; host Eclipse Temurin Java **21.0.13+9**, Apache Maven **3.9.15**, Node **v22.23.4**, npm **10.9.9**, Docker **29.4.2**. Plugin target bytecode is Java 17. The Jenkins/inbound-agent/Node container tags were floating at test time; the original image IDs were not reported by the Docker inspection step, so this is not a digest-pinned image reproduction claim.

**CLI source provenance:** patched portable client **0.2.1-darkmoon.1**, based on source commit `126f6daa930318dd2de0fb61a49ea0fdaf00e0dd`; original bundled snapshot SHA-256 `b76b685802a1973875e28398da0cbbca8cec14e1017011f46656c56c4e638828`; Jenkins-overlay source SHA-256 `d4064ce729ee3d23c436f142e66b82a435eb895a6c59c3f9e9193786596a0d35`. Build-time dependencies `zod@3.25.76` and `esbuild@0.25.12` are pinned and bundled. `e2e/prepare-cli.sh` compares the source SHA-256 with `snapshot.json` before packaging. Neither the controller nor agent needs an npm install or developer-home CLI checkout.

## Native scenarios observed

| Synthetic case | Jenkins result | Warnings NG issues | Archived named artifacts |
| --- | --- | ---: | ---: |
| High severity | FAILURE | 1 | 3 |
| Empty findings | SUCCESS | 0 | 3 |
| Nonempty below thresholds | SUCCESS | 1 | 3 |
| Missing explicitly referenced report | FAILURE (severity gate) | 1 | 2 |
| Malformed campaign record | FAILURE | none published | 1 |
| Running campaign exceeding its deadline | FAILURE | none published | 1 |
| Medium severity | UNSTABLE | 1 | 3 |
| Missing findings | FAILURE | none published | 1 |
| Malformed findings JSON | FAILURE | none published | 1 |
| Non-array findings JSON | FAILURE | none published | 1 |
| Foreign-campaign findings | FAILURE | none published | 1 |
| Ambiguous concurrent campaign records | FAILURE | none published | 1 |
| Failed assessment | FAILURE | none published | 1 |
| Stopped assessment | FAILURE | none published | 1 |
| Timed-out assessment | FAILURE | none published | 1 |
| Missing configured Secret Text credential | FAILURE | none published | 0 |
| Agent missing Node on PATH | FAILURE | none published | 1 |

The driver checks the plugin manager's active HPI, confirms the separate agent connection and `node` version, executes every case as an actual Jenkins Pipeline build, validates Warnings NG's consumed SARIF totals and Jenkins statuses, inspects every archived artifact for synthetic credential/evidence markers, and ensures no unrelated workspace files or opt-in full reports were archived. The same agent workspace is reused, and a missing current-campaign report cannot fall back to an older report. An additional JenkinsRule test simulates a downstream findings HTTP 401 with a deliberately sensitive error body and verifies failure with no empty SARIF or console disclosure.

## Reproduction

```bash
cd integrations/upstream/jenkins
mvn -B -ntp clean verify
unzip -l target/darkmoon-scan.hpi | grep 'WEB-INF/lib/darkmoon-scan.jar'
unzip -l target/darkmoon-scan.jar | grep 'darkmoon-client/darkmoon-ci.cjs'
bash e2e/run-e2e.sh
cd ../../..
PYTHONPATH=mcp python -m pytest tests/community/test_community.py -q
```

Requires Java 21, Maven 3.9+, Node/npm 18+, Docker, Python 3 and network access to dependency repositories at build time. The native driver uses an isolated Docker network, a loopback-published Jenkins port, temporary containers and fixture-only assessments.

## Corrections and remaining limits

Corrected obsolete assumptions about `~/darkmoon-client` and `darkmoon-client-0.1.0.tgz`, plus bundled CLI runtime dependencies. The Jenkins OSS snapshot now rejects absent/malformed/foreign findings instead of returning `[]`, refuses ambiguous multi-candidate campaign attribution, and never falls back to a different campaign's report or follows report paths/symlinks outside the configured reports directory. Strict status, credential and failure-versus-unstable gates remain enforced by the Pipeline step.

**Limits:** OSS candidate discovery uses local campaign files and can associate one newly observed candidate without a producer-signed nonce; ambiguity is now rejected, but this is not atomic or cryptographic launch attribution. A licensed commercial Pro endpoint, real assessment, remote non-Docker host, Windows agent and vendor-wire parity were not tested. The native controller and agent image tags were not pinned to digests. The single skipped Maven test was a Jenkins harness-injected test, not a failed native acceptance case.
