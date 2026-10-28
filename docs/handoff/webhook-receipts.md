# Durable receiver admission (n8n integration extension)

Real n8n 2.45.4 execution in network-disabled CI exposed a duplicate after
process restart: the webhook path's workflow-static receipt mutation did not
survive as an authoritative receipt journal. Poll cursor restart passed. This
fix gives webhook admission its own producer-backed, transactional state rather
than treating the in-memory receiver test as durability proof.

`POST /api/v1/webhooks/{id}/events/claim` is a **fork extension**, not a recovered
commercial route. It requires an authenticated administrator, an existing,
enabled registration and an exact JSON body `{ "event_id": "..." }`. Event IDs
are 1–200 letters, digits, underscores or hyphens. Extra fields/payloads are
rejected. Responses contain only webhook ID, event ID and boolean `claimed`.

- First admission is `claimed: true`; concurrent/repeated admission is false.
- The store transaction checks registration state and records admission together.
- A fresh store/service instance reads the same journal; receiver process
  restart does not reset it.
- Entries expire after 24 hours. Each registration permits 5,000 fresh receipts.
  Capacity returns 429 and Retry-After without evicting fresh receipts. Existing
  duplicates still return false at capacity. Expired entries are reclaimed.
- Deletion clears its registration journal. Disabled/missing registrations fail
  closed. Journal state contains IDs and timestamps, never evidence, request
  bodies, signatures, tokens or signing secrets.

The n8n receiver validates both HMAC versions, timestamp, event identity and safe
projection before calling admission with its existing encrypted API credential.
Only `claimed: true` emits workflow data. Duplicate admission responds 200;
unavailable or malformed admission responds 503 and emits no workflow. The
client never falls back to a volatile receipt cache. Native signing secrets
remain in encrypted credentials rather than workflow exports.

This is **at-most-once admission within a finite retention window**. Admission
precedes workflow enqueue/processing; a crash after admission or downstream
failure can require operator recovery. It does not guarantee exactly-once
workflow effects, indefinite replay protection, or automatic recovery of failed
workflow executions. The underlying producer's retries remain bounded.

Six Python tests cover concurrent callers, registration isolation, a new
store/service instance, role/anonymous/schema errors, disabled/deleted hooks,
secret absence and capacity/expiry behavior. Existing n8n tests and adversarial
contract checks are rerun. The native lifecycle fixture now models persistent
producer receipts across n8n restart and still requires the final replay and
deactivation assertions to pass. All native execution stays inside Docker
`--network none`; no third-party delivery or vendor runtime is involved.
