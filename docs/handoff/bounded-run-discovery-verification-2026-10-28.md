# Bounded run discovery — verification evidence (28 October 2026)

## Scope and provenance

- Implementation anchor: `ba173baba5197874fefe0f73ecbad7c8f24da360`.
- Source and UI verification commit: [`5ddf6a70`](https://github.com/newrecycle/Dark-Moon/commit/5ddf6a70a185a4f9ec85b0099c76d8e09140b509).
- Focused verification gate and disabled-next-button fix: [`c5c2d778`](https://github.com/newrecycle/Dark-Moon/commit/c5c2d7783d6c8e2ade18d537b24fe0642c970959).
- Final browser assertion correction: [`875a3e6f`](https://github.com/newrecycle/Dark-Moon/commit/875a3e6f214b54ba8b363aa9e57e8403a4f49a79).
- This verifies the independent fork with synthetic queue records and a localhost browser fixture. No assessment worker, external target, vendor binary, deployment, webhook delivery or native integration host ran.

## Verified contract

- Active default 50 entries; accepted limit 1–100 and offset 0–100000; HTTP 400 for unknown, duplicated, blank, negative or malformed query values.
- Exact total for more than 100 active records among all terminal states; descending `(created_at,id)` sorting including ties, boundaries, partial and empty pages, `has_more`, `next_offset` and `paging_limit_reached` at the offset ceiling.
- Cancelling is a derived state of running jobs; run IDs remain separate from campaign IDs; public projections exclude spec, env, argv, credentials, exception/error text, paths and process output.
- Heap-selected history pages match full-sort reference across state/campaign/run filters. Log metadata is probed only for returned history records.
- Dashboard validates the full pagination envelope, deduplicates across and within collections, preserves independent active/history cursors, aborts superseded loads, ignores stale results, recovers pages after record-count contraction, displays accurate counts, and resets offsets on account lock.
- Existing restricted log reads, symlink/hardlink defenses and admin-only raw SSE remain covered by the unchanged focused regressions.

## Exact commands used by passing GitHub workflows

```sh
python -m py_compile mcp/community/run_views.py mcp/community/api.py mcp/community/jobs.py mcp/community/store.py mcp/community/server.py mcp/community/service.py tests/community/test_run_discovery.py tests/community/test_run_discovery_scale.py tests/community/test_pro_contract_aliases.py
node --check mcp/community/static/app.js
PYTHONPATH=mcp PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests/community -p 'test_run_discovery.py' -v
PYTHONPATH=mcp PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests/community -p 'test_run_discovery_scale.py' -v
PYTHONPATH=mcp PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests/community -p 'test_pro_contract_aliases.py' -v
PYTHONPATH=mcp python -m pytest mcp/tests tests/community -q
node tests/community/graph_navigation.cjs
node tests/community/finding_query.cjs
node tests/community/headless_flags.cjs
node tests/community/browser_acceptance.cjs
```

## Observed CI

- [Run-discovery verification](https://github.com/newrecycle/Dark-Moon/actions/runs/40725049063): **success**, 11 existing run/log tests + 5 new high-cardinality tests + 10 method alias tests; Python compilation and JS syntax checks passed.
- [Community regressions](https://github.com/newrecycle/Dark-Moon/actions/runs/40725049085): **success**. The earlier equivalent full gate [40724770362](https://github.com/newrecycle/Dark-Moon/actions/runs/40724770362) reported **420 passed, 209 subtests passed**; the later gate includes the UI correction and passed.
- [Browser acceptance](https://github.com/newrecycle/Dark-Moon/actions/runs/40725297223): **success** in installed Playwright Chromium; exercises new independent pagers, correct count labels, deduplication, offset recovery, inconsistent metadata, stale loads and lock, in addition to preexisting local UI acceptance.
- Two earlier browser attempts failed on **test/UI selector presentation**: first, a disabled Next control incorrectly reused offset zero, making its locator ambiguous; second, the new test incorrectly expected a disabled control to be absent. Both were corrected and the final browser gate passed.

## Incremental selection-memory measurement

Test command: `python -m unittest discover -s tests/community -p 'test_run_discovery_scale.py' -v` on the hosted Python 3.11 runner. `tracemalloc` starts **after** constructing the synthetic input; these figures only measure transient `_page` selection allocations:

| Query depth and total input | Measured peak additional allocations |
| --- | ---: |
| 50-row page of 2,500 jobs | 10,112 bytes |
| 50-row page of 110,500 jobs | 3,720 bytes |
| 100-row page at offset 100,000 of 110,500 jobs | 16,812,336 bytes (about 16.0 MiB) |

These are run-specific allocation measurements, not universal memory ceilings. The JSON-backed store still reads and materializes the whole state before selection. Heap selection retains up to `offset + limit` references, so the maximum supported offset is materially more expensive than first-page reads. No stable cursor/snapshot contract is claimed: pages are live offsets and concurrent insertions/status changes can shift records between requests. No licensed commercial Pro wire or runtime parity has been established.
