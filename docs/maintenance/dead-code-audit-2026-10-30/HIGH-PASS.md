# High-pass review — 30 October 2026

This supersedes the medium pass's deferred-removal queue. Baseline remains
`d691fdc`; nothing has been committed or pushed. Original CSVs are retained as
an auditable record of the initial conservative scan. `high-*.csv` records the
reviewed dispositions and evidence. Retaining a public API or framework input
is a compatibility decision, not a claim that every possible caller executed.

## Result

- All 944 baseline files accounted for: 928 retained, 16 proposed removals.
- All 84 Python symbol candidates reviewed: 82 retained, two unused helpers removed.
- 205 dependency declarations reviewed and retained. The initial regex missed
  `go.yaml.in/yaml/v2`; the high inventory corrects that omission (80 Go module
  declarations in total). The earlier count of 204 was incomplete by one.
- No lockfile, dependency manifest, authentication gate, remediation verdict,
  production oracle, or host registration was weakened.

## Additional cleanup beyond the original ten files

The current Grafana app registers eight real datasource-backed routes in
`components/App/App.tsx`; `module.tsx` lazily loads that app and AppConfig. Its
plugin metadata advertises those views and a separate configuration page.
Neither webpack entries nor dynamic imports register the old four starter
pages. Their only reference chain was internal to the abandoned scaffold:

- `src/pages/PageOne.tsx`, `PageTwo.tsx`, `PageThree.tsx`, `PageFour.tsx`;
- `src/components/testIds.ts`, `src/utils/utils.routing.ts`;
- the unused `ROUTES` enum in `src/constants.ts` (the active base URL stays).

The starter Playwright tests still expected those unreachable pages and an
obsolete app-level API-key form. They are replaced with current contracts:
eight metadata-advertised app routes, unknown-route fallback, and saving a
selected datasource UID without storing another API key. Existing Jest route,
configuration and datasource tests remain intact. SOURCES.json records the
additional upstream exclusions/adaptation.

Two unregistered, module-level Python helpers had no callers or export registry:
`_sast_time` in the GitLab mapper and `first_match` in the privacy campaign lab.
Other uses of datetime/regex remain; their imports were retained. Public storage,
executor and registry helpers remain compatibility APIs. BaseWorkflow examples
and TEMPLATE helpers remain developer scaffolds.

## Why the other findings stay

- WorkflowRegistry imports every eligible workflow module and discovers
  BaseWorkflow subclasses with `inspect.getmembers`; absent literal class calls
  do not make AD/Kubernetes/subdomain/web-crawler workflows dead.
- FastMCP decorators, HTTP `do_OPTIONS`, AST `visit_*` methods and unittest class
  discovery are implicit dispatch contracts.
- Python/TypeScript extensionless module imports, React lazy imports, package
  root SDK exports, Node tests and build-tool default config names resolve the
  filename-search false positives. Public SDK exports remain supported APIs.
- Go compiles package files together; Mage's tagged file is a build entry.
  Jenkins compiles Java sources and loads Jelly configuration/help resources by
  class/resource convention. Splunk nav/conf/icon files are installed resources,
  not Python import targets. Package-local duplicate fixtures/icons/licenses
  remain necessary for independent distributions.
- Grafana's `.config/tsconfig.json` includes ambient declaration files.
  Its Jest config explicitly imports `.config/jest/utils.js`.
- Installed Grafana ESLint configuration explicitly loads its declared peer
  plugins/parser. SWC Jest requires SWC core and core declares helpers as a peer.
  Grafana data declares i18n. Build/format/sign/browser tooling is retained even
  when application source does not import a package name directly.
- Installed `pydantic-settings` metadata requires `python-dotenv>=1.2.2` and its
  dotenv provider imports that module. No dotenv removal is justified by grep.
- Maven's parent/BOM/HPI, structs annotations, Workflow Step API, credential APIs,
  Jackson mapping, Warnings-NG SARIF, workflow test plugins and resource-bundling
  exec plugin each have explicit POM/source/test roles. No Maven executable was
  available here; native Maven graph/build verification was not performed.
- The Go module graph was attempted with the actual pinned Go 1.26.3 compiler.
  Some zip downloads redirected to `storage.googleapis.com` and were forbidden
  by the configured network path. `go test ./...` therefore failed during setup.
  Partial `go mod why` output is not evidence that a module is unused; all 80
  declarations remain `retain-blocked-validation`, with no manifest/sum change.

A direct declaration can sometimes be redundant with a transitive dependency.
That alone is insufficient justification for changing an explicit reproducible
framework/build contract. This audit proposes no dependency pruning on that basis.

## Verification and limits

- Full MCP/community plus collected GitLab tests: **513 passed, 310 subtests**.
- GitLab's standalone mapper unit runner: **37 passed, 0 failed**.
- Grafana: typecheck, production webpack build and **3 Jest suites / 7 tests passed**.
  Webpack warns about the existing 1.23 MiB overview screenshot.
- Lint ran and failed on the existing `react-hooks/set-state-in-effect` error in
  DatasourceView.tsx:78, plus two deprecated Select warnings. That file was
  byte-compared with HEAD and is unchanged. No rule was disabled.
- Go native tests are blocked as described above; no Go success is claimed.
- Docker Grafana 13.1.0 failed to unpack due to daemon storage exhaustion.
  The smaller supported 10.4.19 image succeeded after retry. Generated public
  assets required readable permissions before Grafana could register the app.
- Initial revised browser tests revealed a status-selector collision and an
  accidental attempt to treat the separate configuration page as an app view.
  Those test mistakes were corrected; the initial failures are not passes.

The browser check uses real Grafana 10.4.19 and system Chromium. Only the
configuration test's datasource-list response is synthetic. The settings POST
and UI are real; no backend datasource query or native Go compatibility is
established by this frontend-only host. No model/forge gate was rerun or closed.

These dispositions close the static cleanup review conservatively. They do not
prove absence of all dead branches, undocumented external callers, or dynamic
behavior on every supported host. Native Go/Maven verification remains an
explicit limitation, not a fabricated completion result.

Final browser rerun: **11 passed in 30.4 seconds**, including authentication,
eight app routes, unknown-route fallback, and the datasource settings POST.
Exact final output is retained under `evidence/playwright-final.txt`.
