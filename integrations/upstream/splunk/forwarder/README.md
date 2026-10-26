# darkmoon-to-hec forwarder

A tiny, dependency-free (Python 3 stdlib) sender that pushes **safe** Darkmoon
events to a Splunk HTTP Event Collector. Use it if you are **not** on the
Darkmoon Pro webhook system.

> Pro users can skip this entirely: point a Darkmoon webhook (`format=splunk_hec`)
> at your HEC endpoint and the Darkmoon dispatcher formats the events for you.

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
