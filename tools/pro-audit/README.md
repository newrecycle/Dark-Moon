# DarkMoon Pro forensic audit kit

The script `darkmoon_pro_forensic_audit.py` targets **the original** `ascit/opencode-darkmoon-pro` image pinned to:

`sha256:48248382877ec1fd7362d2268656956268129d5ea565befab3a24436ea2fc907`

It does not modify Docker images, start a container, alter or bypass licensing, run pentests, create PRs, or write to API endpoints. It compares your fork only by reading/cloning the `pro` branch. Most stages require Python 3.11+ and common command-line tools; Docker is required only when extracting directly from the image. Optional stages need Node/npm, Playwright or Ghidra.

## Standard run (WSL, using locally pulled Docker image)

```bash
python3 darkmoon_pro_forensic_audit.py \
  --out ~/darkmoon-pro-complete-audit \
  --workers 4 \
  --stages inventory,contracts,frontend,fork,native,discovery,report,pack
```

If using the **three extracted archives** from the previous script instead of Docker, place them in a single directory and use `--archives-dir /path/to/archives`. Existing fork checkout can be specified via `--fork-path /path/to/Dark-Moon`. For a full image path inventory use `--full-inventory` with `inventory` (potentially slow).

## Late, high-cost static stages (all Angular bundles and compiled native modules)

```bash
python3 darkmoon_pro_forensic_audit.py \
  --out ~/darkmoon-pro-complete-audit \
  --stages js-ast,prettify,pack \
  --install-js-tools --workers 2

python3 darkmoon_pro_forensic_audit.py \
  --out ~/darkmoon-pro-complete-audit \
  --stages disasm,pack \
  --workers 2
```

The first command installs optional JS analysis dependencies **under the output directory**, with npm scripts disabled. The Babel scan identifies Angular template call sites, controls, listeners, validators, network requests and component metadata. Prettier produces one readable `.js` per original chunk. It **does not** reconstruct original `.ts` files, renaming, comments, or source maps.

## Optional Ghidra pseudocode stage (slowest; run last)

Install Ghidra and pass the path to `support/analyzeHeadless`:

```bash
python3 darkmoon_pro_forensic_audit.py \
  --out ~/darkmoon-pro-complete-audit \
  --stages ghidra,pack \
  --ghidra-bin /path/to/ghidra/support/analyzeHeadless \
  --ghidra-modules pipeline,patcher,validators,sandbox,routes_run,routes_retest \
  --ghidra-max-functions 0 \
  --ghidra-timeout 3600
```

Omit `--ghidra-modules` to analyze **all 32 native modules**. `--ghidra-max-functions 0` asks for all discovered functions per module. This could require considerable disk, RAM, and time. Ghidra outputs reconstructed C-like pseudocode, **not exact original Python algorithms**. High-level logic may remain ambiguous or be optimized away.

## Authorized live API capture (read-only)

Only point to a deployed instance you administer or have permission to test. The script never starts the licensed container or bypasses licensing. Localhost is allowed by default; an explicitly authorized remote instance requires `--allow-remote`. It never submits POST, PUT, PATCH or DELETE automatically.

```bash
export PRO_AUDIT_TOKEN='your-existing-authorized-token'
python3 darkmoon_pro_forensic_audit.py \
  --out ~/darkmoon-pro-complete-audit \
  --stages runtime,report,pack \
  --pro-url http://127.0.0.1:8000 \
  --auth-token-env PRO_AUDIT_TOKEN \
  --runtime-all-get \
  --ids-file /path/to/owned-fixture-ids.json
unset PRO_AUDIT_TOKEN
```

An optional **separate** `--fork-url http://127.0.0.1:<port>` compares response HTTP statuses and *shapes* for the original and your fork. The `ids-file` contains only your own disposable fixture IDs, e.g. `{"campaign_id":"camp_test", "run_id":"run_test", "target_id":"tgt_test", "vuln_id":"vuln_test", "schedule_id":"sched_test", "cred_id":"cred_test", "retest_id":"ret_test", "webhook_id":"wh_test", "pr_id":"pr_test"}`. Omit unavailable IDs; those requests are skipped. Default runtime mode hits only health/system/OpenAPI; `--runtime-all-get` opts into more reads. All captured responses are converted to **JSON field/type shapes**, not raw secrets or stored evidence.

## Optional Playwright browser audit

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
python3 darkmoon_pro_forensic_audit.py \
  --out ~/darkmoon-pro-complete-audit \
  --stages browser,pack --pro-url http://127.0.0.1:80
```

Passive browser mode opens documented routes, inventories controls, and records HTTP status/path and console text. `--screenshots` additionally saves screenshots (they can contain sensitive data; review before sharing).

For **manual** interaction capture, use a disposable owned test instance, run in a graphical environment with WSLg/X11, and interact with pages yourself:

```bash
python3 darkmoon_pro_forensic_audit.py \
  --out ~/darkmoon-pro-complete-audit \
  --stages browser-record,pack \
  --pro-url http://127.0.0.1:80 --headed --observe-seconds 300
```

The script records clicked/submitted/changed DOM control identities and HTTP methods, URL paths, and statuses, **without form values, request bodies, Authorization headers, or cookie values**. It cannot verify side-effecting workflows without separate explicit, safe fixtures and operator-driven actions.

## Output layout

- `raw/`: original selected Pro API `.py`/`.pyi`/`.so`, remediation `.pyi`/`.so`, tests, Angular bundles and Nginx configuration (safely excluded runtime credential stores).
- `manifest.json`: SHA-256 and size for all copied files.
- `contracts/`: AST-indexed signatures, class/data fields, defaults, raised errors, branch conditions, test expectations, prompts, original route decorators and root routes.
- `frontend/`: bundle references, Angular selectors, UI/router hints, event/control/validator/API call sites; optional Babel AST and formatted JS.
- `native/`: native module symbols, ELF metadata, strings and optional full assembly listings.
- `discovery/`: environment variable names (not values), event names, feature markers, dynamically-constructed or apparently unreferenced API routes.
- `fork/`: current `pro` branch SHA, indexed Python declarations, candidate route matches (static hints, **not verified API parity**).
- `runtime/`: opt-in authorized original/fork GET status and redacted response type trees.
- `browser/`: opt-in passive page observations or manual interaction trace.
- `ghidra/`: optional reconstructed pseudocode, logs, and per-module progress.
- `acceptance-test-matrix.json`: API, UI, and remediation per-feature test requirements.
- `REPORT.md`: facts, source limitations and original contract inventory.
- `packages/`: separate ZIP archives for analysis, formatted JS, and optional extracted source/native code.

Stages are marked complete under `stage-markers/`. On restart completed stages are skipped, while `report` and `pack` always rerun to reflect newly completed work. `--refresh` forces recomputation.

To include extracted original code and compiled JS in shareable archives, pass `--pack-source`; to include `.so` binaries, pass `--pack-native`. **Check all archives for proprietary licensing restrictions and confidential information before uploading or redistributing them**. The default analysis archive avoids copying source/binaries. No font files should be shared.

## Essential limits

A binary implementation is not a lossless encoding of the developer's original algorithm, variable names, comments, intended business rules or TypeScript source. `.pyi` and tests document *contracts* and intended outcomes; native binary analysis produces approximate machine-level behavior. To validate exact API results and actual remediation side effects, you need an authorized licensed instance, representative disposable fixtures, and controlled execution. This script deliberately does **not** launch pentests, change records, publish PRs, or attempt to bypass commercial runtime checks. Use the generated acceptance matrix to design explicit, isolated tests for those mutation paths.