# Grafana host boundaries

The retained grafana-native-host.yml now runs the actual packaged plugin on
10.4.19 (the declared 10.4 support family) and 13.1. The official 10.4.19 release
is documented at https://grafana.com/grafana/download/10.4.19 . These disposable
hosts run on a private internal Docker network with synthetic credentials,
unsigned-plugin opt-in only for the fixture, telemetry disabled and no real
DarkMoon target. The adjacent Python fixture requests the actual Grafana API.

Each matrix leg builds the actual app and datasource, provisions both, checks
that Grafana loads them, executes a datasource query through the native plugin
and verifies returned frame/schema/lifecycle identities. Per-version health,
plugin and datasource metadata are retained. Do not label every intervening
version accepted from two host samples or infer frontend rendering from API
results. The previously observed 13.1 host acceptance remains valid evidence;
the added matrix is pending execution at its matching commit.

Reproduce with the exact commands in the workflow, substituting either tested
image version for the matrix expression. Requires Docker, Go from go.mod, Node
22, npm and ordinary build-network access. Never bind this old-version fixture
to a public interface or reuse its credentials in a deployment.

Signed Grafana Catalog distribution requires the maintainer's signing account
and release process. It is not emulated with an unsigned local signature.
Native browser visual behavior and the exact minimum patch 10.4.0 remain
separate compatibility evidence. Splunk and GitLab Ultimate prerequisites are
listed in current-pro-status.md; they are not replaced by this Grafana test.
