# darkmoon-to-hec forwarder

A dependency-free Python sender for authenticated Splunk HEC delivery from
this fork. It forwards allowlisted metadata snapshots, not proof of live
state transitions or deployed fixes.

> Use this forwarder for authenticated HEC delivery from this fork. Direct `format=splunk_hec` webhook delivery is unsupported; a signing secret does not supply HEC authentication.

## What it emits

Only allowlisted, scrubbed fields per sourcetype (`SAFE_FIELDS` in the script):
`darkmoon:campaign`, `darkmoon:finding`, `darkmoon:retest`, `darkmoon:pr`
and `darkmoon:remediation` (local proposals).
Evidence, secrets, credentials, tokens, descriptions and request/response bodies
are dropped by construction, and every string is scrubbed for token-like patterns.

## Usage

Poll the Pro REST API and ship to HEC:

```bash
export DARKMOON_TOKEN=...        # Pro bearer
export SPLUNK_HEC_TOKEN=...      # HEC token
python3 darkmoon-to-hec.py \
  --rest-url https://darkmoon.internal:8443 \
  --hec-url https://splunk.internal:8088/services/collector/event
```

Ship from a JSON export (same shape as REST `data` arrays):

```bash
python3 darkmoon-to-hec.py \
  --export darkmoon-export.json \
  --hec-url https://splunk:8088/services/collector/event \
  --hec-token "$SPLUNK_HEC_TOKEN"
```

Dry-run — print the exact HEC envelopes without sending (great for review/CI):

```bash
python3 darkmoon-to-hec.py --export sample.json --stdout
```

### Export file shape

```json
{
  "campaigns":       [ { "campaign_id": "...", "status": "completed", "stats": {...}, ... } ],
  "vulnerabilities": [ { "finding_id": "...", "severity": "high", "status": "exploited", ... } ],
  "retests":         [ { "retest_id": "...", "finding_id": "...", "verdict": "fixed", ... } ],
  "pull_requests":   [ { "pr_id": "...", "state": "open", ... } ]
}
```

## Flags

`--rest-url` / `--export` (input, one required), `--token`, `--hec-url` /
`--stdout` (output, one required), `--hec-token`, `--batch-size` (default 100),
`--insecure` (disable TLS verification — **lab only**).

Verified HTTPS is required before REST/HEC requests are constructed. Explicit
`--insecure` permits HTTP/unverified TLS only in a controlled lab. Embedded
userinfo, query/fragment delimiters, invalid ports, backslashes, whitespace and
control characters in configured URLs are rejected. Redirects are not followed.

Retries use bounded exponential backoff. Redirects and permanent 4xx (except
429) and explicit HEC application refusal/malformed admission are not retried.
A successful HEC response needs integer `code: 0`. Earlier batches or uncertain
transport retries may already be admitted when a later operation fails.
Batches are newline-delimited JSON, chunked by `--batch-size`. Indexer ACK
is unsupported; neither successful admission nor a content hash implies
exactly-once indexing.

## Fork implementation update

The forwarder now maps REST record IDs into campaign/finding/PR identities,
accepts typed scalar metadata and finite numeric counts, and distinguishes local
proposals (`darkmoon:remediation`) from published PRs. Running or unknown retests
are not labelled completed. Snapshot content fingerprints are included for
consumer deduplication; repeated snapshots and ambiguous transport retries can
still duplicate ingestion. This is not exactly-once delivery.

REST read/shape failures stop the batch instead of substituting empty arrays.
HEC delivery requires HTTP success plus JSON `code: 0`; rejection is an error,
and indexer ACK mode is explicitly unsupported. Redirects are refused. The
alert action resolves an allowlisted host to one saved REST target before a
retest, keeps launch acceptance separate from completion, and serializes its
rolling quota across processes with atomic state writes.

Verification of these changes is deferred to the later test pass.

## Retest and snapshot consumer wiring — 28 October 2026

REST mode now reads `/campaigns`, `/vulnerabilities`, `/pull-requests`, `/retest`
and `/targets` under `/api/v1`. Every read must succeed with a typed data array;
missing retest support is an explicit error rather than an empty dashboard.
Optional export `targets` metadata joins through exact saved target IDs; hosts
are not inferred by title or partial ID. Target rows do not become separate
HEC events. All input arrays are prepared before any HEC batch is sent.

Aggregate retests emit a lifecycle snapshot even when comparisons are empty,
plus one comparison snapshot per typed finding row. `findings`/`verdicts`
aliases must agree. Exact run/base/new campaign/target/current-finding references
remain available; `not_observed` is preserved and is not a proof of repair.
Legacy flat retest exports still work. Completed aggregate retests need an
explicit comparison array. Campaign-qualified `finding_key` values keep repeated
finding IDs separate, including base/new findings in a comparison.

PR/local-proposal exports preserve bounded typed finding-ID arrays. PR records
retain their local record identity even when the SCM reference is numeric.
The dashboard has separate local-proposal and retest lifecycle views, and
per-finding comparisons do not require an optional title to exist. Searches
select the latest indexed observation before mutable-field filters and use
campaign-qualified finding identities. Simple XML string tokens use `|s`.
The selected source-time window is not complete retained-workspace coverage.

The source reconciliation includes fixes from independent commits `7b26130`
and `a1a3454`: strict transport admission, URL/HEC-host sanitization, UTC naive
timestamps, bounded batch/retry settings and non-retried semantic refusal.
Their tests/workflows remain on their original branches for the verification
worker to reconcile; old tests expect three REST collections, while this
implementation intentionally reads five. No combined test/native result is
claimed. See `docs/handoff/splunk-forwarder-integration-2026-10-28.md`.

### Bounded REST pagination

The forwarder reads all five collections before sending any HEC event. It accepts
legacy unpaged envelopes only when they do not advertise omitted rows. Paged
responses must provide consistent offset/limit/total/has_more/next_offset metadata;
next requests are constructed locally, never taken from a server-provided URL.
Missing pages, overlapping identities, changing totals and truncated/capped feeds
fail the poll. Limits are 1,000 pages, 100,000 rows and 32 MiB per collection.
Finding identities include the campaign, so identical IDs in different campaigns
remain distinct. These checks detect common live-offset changes; they do not
provide transactional snapshot isolation against concurrent source edits.

Reusable severity/open-finding macros now select each identity's latest indexed
observation before filtering mutable fields. Historical open states cannot
resurrect a later remediated finding through those macros.
