# Bounded finding-history verification — 2026-10-28

Source implementation checkpoint: [`b8f5bf5`](https://github.com/newrecycle/Dark-Moon/commit/b8f5bf589bc9c700e25747d7fb9f85333e2ec78b).

Correction and focused test checkpoint: [`e6b604c`](https://github.com/newrecycle/Dark-Moon/commit/e6b604c54f541e21a3b8f7d09849a7ef82a76a86). Built on the latest `pro` available at publication, preserving newer Grafana commits.

## Verified fork contract and fixes

- The bounded `load_finding_history(target_id=...,limit=...,offset=...)` scan matches reference full-sort `(recorded_at,id)` order despite out-of-order append timestamps, ties and interleaved targets. Unpaged internal reads remain append ordered, including original stored fields. Public pages explicitly project only ten allowed keys.
- Every persisted event is checked before target filtering, page selection or early return. Corrupt headers, unsupported version and invalid timestamps, blank rows, malformed JSON, nonobject rows, invalid UTF-8, huge integers, deep nesting, JSON NaN/Infinity, nonterminated lines, invalid identities/metadata and escaped lone Unicode surrogates cause `FindingHistoryUnavailable` and HTTP 500, including when corruption is outside the target or page. Valid arbitrary extension fields remain excluded from public output.
- The byte limit is **65536 bytes including the newline**; an exactly sized synthetic row reads successfully, 65537 bytes and incomplete final lines are rejected. The HTTP limit is 1–500 (default 100); offset is 0–100000 (default 0), and requests beyond the ceiling reject with HTTP 400. Empty pages retain exact totals and page metadata.
- `record_finding_event` now validates Unicode encoding and JSON serializability before writing. It rejects invalid identity, source, project/status metadata and malformed surrogate strings without appending. Unicode text remains valid; the append remains flushed and `fsync`ed. Initialization does not backfill older snapshots.
- 32 thread-generated and 36 independent child-process events are validated after the readers and writers finish (68 distinct IDs across two targets), and a second init/restart check preserves the journal and event count.

## Commands executed by GitHub Actions (offline)

```bash
python -m py_compile mcp/api/json_storage.py mcp/api/live_push.py mcp/community/finding_lifecycle.py mcp/community/api.py mcp/community/service.py tests/community/test_finding_lifecycle.py tests/community/test_finding_history_bounded.py
node --check mcp/community/static/app.js
node --check tests/community/browser_acceptance.cjs
PYTHONPATH=mcp python -m pytest tests/community/test_finding_lifecycle.py -v
PYTHONPATH=mcp python -m pytest tests/community/test_finding_history_bounded.py -v -s
# Existing campaign isolation gate:
PYTHONPATH=mcp python -m pytest mcp/tests tests/community -q
node tests/community/campaign_binding.cjs
node tests/community/graph_navigation.cjs
node tests/community/finding_query.cjs
```

## Direct CI observations

[Finding lifecycle verification run 40724658834](https://github.com/newrecycle/Dark-Moon/actions/runs/40724658834): **success**. Syntax checks passed, existing lifecycle suite **10 passed in 5.42 s**; new bounded suite **12 passed, 43 subtests passed in 8.04 s**. All tests use synthetic, local-only state; no licensed vendor or scanner invoked.

Retained-memory benchmark (Python `tracemalloc`, reader call only; exact GitHub-hosted runner measurements):

| Measurement | Observed |
| --- | ---: |
| Synthetic journal events | 25,000 |
| Journal file size | 6,775,086 bytes |
| Selected page | Target `t1`, limit 50, offset 400 |
| Scan wall time | 1.744 seconds |
| Peak traced Python allocation | 452,980 bytes |
| Measured lock wait when held by another thread | 0.1506 seconds |

The memory measurement is the peak Python allocation *traced during the reader call*, **not total process RSS**, nor a bound on the entire process. Test bounds: peak traced allocation below 20 MiB and wall time below 30 seconds on this fixture.

[Campaign isolation regression run 40724658845](https://github.com/newrecycle/Dark-Moon/actions/runs/40724658845) on the same checkpoint exercises the full offline `mcp/tests` and `tests/community` suites, plus native campaign-binding and finding-query JavaScript checks. The run outcome should be consulted directly before claiming full-regression success.

## Limitations

This is **not indexed access**. Every history page scans and validates the entire JSONL file while holding the same cross-thread/process `_file_lock`; total scan work and writer contention therefore grow with journal length. Bounded paging retains at most offset+limit projected events, up to 100500 at the maximum accepted pagination parameters. The large-journal test measured an offset of 400, not worst-case retention at 100000. Live offset pages can shift across appends; no cross-page snapshot is promised. Finding snapshot mutation and journal append are separate filesystem transactions and **not crash-atomic**. Unpaged internal calls intentionally materialize full append order. There is no reconstructed backfill, external integration, provider assessment, licensed commercial runtime comparison, or native vendor test.
