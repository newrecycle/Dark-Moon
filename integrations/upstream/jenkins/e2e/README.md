# Real-Jenkins E2E

`run-e2e.sh` builds the produced `.hpi`, installs it together with the **real**
`darkmoon-ci` CLI (from `$DARKMOON_CLIENT_DIR`, default `~/darkmoon-client`) into a
`jenkins/jenkins:lts-jdk21` container, and runs a declarative pipeline (defined by
`casc.yaml`) against a fixture-backed OSS campaign materialized by `engine-standin.sh`
(a stand-in for the Darkmoon engine, which is out of scope for the integration).

Asserts: build result `FAILURE` (fail policy), warnings-ng `totalSize=5`, and the
report / SARIF / CLI-log archived on the controller. Requires Docker.
