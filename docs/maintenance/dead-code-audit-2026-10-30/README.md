**Follow-up:** [High-pass review](HIGH-PASS.md) supersedes the deferred queue below.

# Repository cleanup audit — 30 October 2026

Baseline: `d691fdc2780628e8927587bb208f358e1a2e7a15` on `pro`.
This is the requested medium-effort static audit, with ambiguous dynamic-loading,
framework, and cross-package removal decisions explicitly deferred. Nothing is
committed or pushed. The previously staged ten-file cleanup remains proposed.

## Coverage and interpretation

`files.csv` accounts for every file tracked at the baseline, including proposed
removals, with category, size, digest, textual references and a disposition.
`dependencies.csv` covers declarations in all six Node manifests, both Python
requirements files, the Go module and the Maven POM, including build, peer,
managed and indirect declarations. `install-sites.csv` inventories tool/dependency
installation commands in scripts, Dockerfiles and workflows. Multiline shell
commands, downloaded tool inventories, OS packages and framework-managed graphs
need their native resolution; an installation-site row does not independently
validate every transitive package. Lockfiles are retained as reproducibility
inputs, not pruned by text search.

`duplicates.csv` lists identical nonempty tracked content. Package-local fixtures,
icons, license files and SDK archives can intentionally duplicate content.
`symbol-candidates.csv` identifies Python definitions occurring only once in
tracked text. Decorated functions, methods, host hooks and public APIs can be
called without another literal occurrence of their name.

These are conservative reference scans. A `retain` decision means an explicit
reference or known repository role was found, not proof that every statement is
reachable. A `defer` decision is a high-pass queue, not proof of dead code.
Filename matches and package/tool-name matches are heuristic and can include
comments or unrelated files. No dependency or symbol is removed from those
signals alone. Java/Go/TypeScript symbol reachability, exports and compiler
elimination are not proven by the Python symbol scan; their unreferenced-symbol
removal decisions are deferred to the high pass.

## Proposed removals

- Five superseded OpenCode overrides: `conf/tui/{app.tsx,index.ts,index.tsx,logo.tsx,ui.ts}`.
  Dockerfile.opencode explicitly replaced full-file overrides with the single
  retained `conf/tui/logo.ts` data module. No other build/script references these
  five override paths. This avoids resurrecting stale upstream implementations.
- Both `vendor/darkmoon-client-0.1.0.tgz` files under Action/VS Code. Their manifests
  and lockfiles select `darkmoon_ai-client-0.2.1-darkmoon.1.tgz`; current archives
  remain intact. SOURCES.json records the retired archives as exclusions.
- `mcp/.env`, byte-identical to `.env.example`. The installer already copies the
  example when needed. No credentials were present in that duplicate template.
- Unreferenced `docs/pics/logo_black.png` and `logo_white.png`.

Total: ten tracked files, 415,519 bytes. No application function, security gate,
fixture, supported integration, active archive or dependency declaration changed.
Disposable Python caches were removed; the working virtual environment and
operator runtime settings were retained.

## Deferred high-pass decisions

Start with rows labeled `defer`, then review exported APIs and implicit consumers
in rows conservatively retained. In particular:

- `python-dotenv` has no direct `dotenv`/`load_dotenv` import in repository source.
  FastMCP/environment handling and transitive requirements need review before
  removing an explicit installation contract.
- Node dependencies without direct textual evidence may be resolved by lint,
  webpack, TypeScript, Jest, host plugin tooling or peer contracts. Do not remove
  them merely because source imports are absent.
- Maven parent/BOM/plugin dependencies and indirect Go modules need native
  dependency-graph analysis; Jenkins/Grafana registrations are implicit consumers.
- Public exports, methods, reflection/decorators, dynamic imports, plugin entry
  points and distribution-only assets require the requested high pass.
- Duplicate package-local assets and fixtures need packaging/consumer review.
- Build and assessment-tool installation commands are intentional external
  capabilities. Absence of a literal call in this repository is not disuse.

This pass does not assert that all dead code is eliminated. It completes tree
and manifest accounting and the unambiguous removal review; the deliberately
skipped reachability/graph decisions remain open.

## Validation

During preparation of this exact cleanup (before this audit's report-only files):

- MCP tests and community core: 172 tests and 4 subtests passed.
- Shared SDK built successfully. The initial archive check lacked generated
  `dist/index.cjs`; after building, both retained Action/VS Code archives passed
  provenance/version/SDK/CLI content checks. No failed initial check is counted
  as a pass.
- Distribution inventory: all eight retained source imports and license files
  checked; all workflow YAML parsed.
- `git diff --check` passed.

No additional application or dependency removals were found safe enough for this
pass. Full native Java/Go/TypeScript integration suites and model/forge gates were
not rerun for these report-only additions. Existing acceptance gaps remain open.
