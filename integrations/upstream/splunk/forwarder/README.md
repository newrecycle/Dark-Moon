# darkmoon-to-hec forwarder

A tiny, dependency-free (Python 3 stdlib) sender that pushes **safe** Darkmoon
events to a Splunk HTTP Event Collector. Use it if you are **not** on the
Darkmoon Pro webhook system.

> Use this forwarder for authenticated HEC delivery from this fork. Direct `format=splunk_hec` webhook delivery is unsupported; a signing secret does not supply HEC authentication.

## What it emits

Only allowlisted, scrubbed fields per sourcetype (`SAFE_FIELDS` in the script):
`darkmoon:campaign`, `darkmoon:finding`, `darkmoon:retest`, `darkmoon:pr`.
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

Retries use exponential backoff with jitter; HTTP 400/403 are treated as
non-retryable. Batches are newline-delimited JSON, chunked by `--batch-size`.

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
