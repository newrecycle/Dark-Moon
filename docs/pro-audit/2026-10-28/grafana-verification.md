# Grafana fork verification — 28 October 2026

## Scope and provenance

This is **fork-tested** verification for `integrations/upstream/grafana`, based on implementation anchor
`b8218dd142a8e5ab0aab22e812746c69f4dc5d97` and later **non-destructive**
updates on `pro`. Source is authoritative; all intervening unrelated commits
were retained. No commercial Pro binary or production provider was executed.

The [focused Go/frontend run (success)](https://github.com/newrecycle/Dark-Moon/actions/runs/40725844906)
tested the contract and application component fixtures. The
[disposable Grafana 13.1 host run (success)](https://github.com/newrecycle/Dark-Moon/actions/runs/40727729155)
packaged the real plugin and executed a fixture-backed retest query via Grafana's
own authenticated `/api/ds/query` endpoint. Both GitHub Actions workflow gates
run on `pro` and can be dispatched manually:

- [Grafana integration verification workflow](../../../.github/workflows/grafana-integration-verification.yml)
- [Grafana isolated host workflow](../../../.github/workflows/grafana-native-host.yml)

## Exact verification commands and results

From `integrations/upstream/grafana/plugin`, the focused workflow used
Go 1.26.3 (from `go.mod`) and Node 22:

```sh
gofmt -l pkg/plugin/*.go pkg/models/*.go pkg/main.go
gofmt -w pkg/plugin/*.go pkg/models/*.go pkg/main.go
go test -race ./pkg/...
go build ./pkg/...
npm ci --ignore-scripts
npm run typecheck
npm run test:ci -- --watch=false
npm run build
test -f dist/plugin.json
test -f dist/datasource/plugin.json
test -f dist/datasource/img/logo.svg
```

All focused workflow steps passed at run 40725844906. Formatting runs in the
disposable CI workspace; that does **not** certify that every tracked Go source
has already been rewritten by `gofmt`.

The separately executed native host built the **actual fork package**:

```sh
npm ci --ignore-scripts
npm run build
go run github.com/magefile/mage -v build:linux
test -x dist/datasource/gpx_darkmoon_linux_amd64
test -f dist/datasource/plugin.json
```

The workflow launched a synthetic Python API and `grafana/grafana:13.1` on a
disposable Docker `--internal` network, provisioned a Darkmoon datasource and
enabled app, checked both from the native Grafana HTTP API, then issued
`POST /api/ds/query` for `retest_demo_1`. Grafana returned both
`retest_state` and `retest` frames with exact completed status,
`camp_demo_01` (base), `camp_demo_04` (new), `tgt_web`, and
`run_demo_retest`. Run 40727729155 passed. It uploaded sanitized
health/app/datasource metadata, but no payload secrets or raw evidence.

## Coverage added

- Incomplete/queued/running/failed/interrupted retests can have
  `verdicts: []` and no `findings` array while retaining a separate
  lifecycle frame and exact campaign/target/run IDs.
- Completed retests require an explicit comparison array (valid empty array
  accepted). Invalid rows, duplicate finding identities, contradictory
  `findings`/`verdicts` aliases, mismatched top-level identity and unrelated
  row campaign/target/run references are rejected.
- Comparison `current_finding_id` is preserved; `not_observed` is not promoted
  into `fixed`.
- Grafana time picker UTC bounds override stale query `params.from/to`;
  explicit bounds without a picker still work; invalid and reversed intervals
  reject.
- ISO-week year transitions, valid 2020-W53, invalid week 53, sparse timestamp
  alignment and missing-series null gaps are tested.
- Findings retain exact `campaign_id`; valid CVSS zero differs from invalid
  or missing/null scores.
- React tests reject unequal/malformed frames rather than implying empty data,
  prohibit substitution for an explicitly unavailable datasource, ignore stale
  responses, and keep lifecycle-only retest views visible.
- Go transport tests verify no following/forwarding of bearer credentials to
  a redirect target, plus allowlisted evidence metadata projection.

## Resolved defects and harness corrections

The retest adapter now rejects foreign optional references on individual
comparison rows instead of silently ignoring them. Existing application
scaffold Jest tests referred to removed pages/API secret fields, so they were
replaced by assertions of current live app routes and UID-only configuration.
Explicit datasource fallback was documented and locked with React regression
coverage.

The native host harness initially found operational acceptance gaps:
a deprecated `grafana/grafana-oss:13.1.0` image reference, attempting to
access an internal Docker network through an inaccessible host-published
port, and using a plugin-detail HTTP lookup not available in the pinned host
path. The final gate used `grafana/grafana:13.1`, an internal peer's HTTP
client, and the Grafana plugin collection endpoint, then successfully
exercised the real datasource query. Earlier failed/cancelled runs are not
treated as success.

## Remaining boundaries

Grafana **13.1** passed on a disposable host; this does not establish
compatibility with Grafana 10.4/12.x or a signed Catalog distribution.
Native browser visuals/Playwright are not established by the API host check.
No licensed commercial Pro response/body, real target assessment, external
provider login or authorization, plugin signing, cloud deployment, external
notification, or third-party remote API was invoked. The tests exercise the
fork's schema and synthetic fixture, not vendor-wire parity. Continue
protecting metadata-only outputs and review consumer permissions when
configuring production datasource access.
