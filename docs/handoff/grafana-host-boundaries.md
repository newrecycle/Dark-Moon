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
results. Both matrix legs passed in run 41005616438 on a97c504. The previously
observed 13.1 acceptance remains valid separate evidence.

Reproduce with the exact commands in the workflow, substituting either tested
image version for the matrix expression. Requires Docker, Go from go.mod, Node
22, npm and ordinary build-network access. Never bind this old-version fixture
to a public interface or reuse its credentials in a deployment.

Signed Grafana Catalog distribution requires the maintainer's signing account
and release process. It is not emulated with an unsigned local signature.
Exact commercial visual matching and the exact minimum patch 10.4.0 remain
separate compatibility evidence. Splunk and GitLab Ultimate prerequisites are
listed in current-pro-status.md; they are not replaced by this Grafana test.


The same private host job now starts a version-matched Playwright container
using the dependency already locked/installed by the plugin build. No browser
network access outside the fixture origin is allowed. It signs into the real
Grafana with synthetic credentials, opens all eight app views, exercises a
severity filter and saved retest, denies an unavailable explicit datasource,
checks uncaught page errors and retains desktop/mobile screenshots. This
closed the executable native-browser gap for the sampled versions: both legs
passed in run 41006932019 on ddf7542. All eight views, the severity filter,
saved retest, inaccessible-source denial and protected-content checks passed.
Desktop/mobile screenshots are retained; this is not exact vendor visual matching.


The first browser run loaded the overview/campaign/finding pages on both real
hosts, then exposed ambiguous accessible names on native selects: option text
became part of the implicit label, preventing exact Severity lookup. Production
datasource, severity, campaign and retest controls now have explicit accessible
names. The filter check also waits for its matching native query response.
The test still requires all eight pages and never substitutes API-only success.
