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

## Synthetic webhook test event (28 October, implementation-only)

`POST /api/v1/webhooks/{webhook_id}/test` is administrator-only and accepts no
body or an empty JSON object. It does not accept destination, headers, secrets,
event type or payload overrides. Missing/deleted hooks return 404; disabled or
missing-signing-key hooks return 409. An atomic store transaction enforces a
60-second persisted per-hook cooldown, at most three pending tests per hook and
1,000 pending deliveries globally; excess requests return 429/Retry-After.
Each accepted request uses distinct event and delivery IDs. Deletion clears
receipt/cooldown state and cancels pending deliveries.

The worker signs and sends this minimal envelope (IDs and timestamps vary):
```json
{
  "id": "evt_test_<random>",
  "event": "webhook.test",
  "timestamp": "<UTC ISO-8601>",
  "ts": "<UTC ISO-8601>",
  "contract_version": "1",
  "synthetic": true,
  "data": {"synthetic": true, "purpose": "delivery_validation"},
  "delivery_id": "delivery_<random>"
}
```
The test is queued only to the selected hook, even when its production
event filter excludes `webhook.test`. It never uses the broadcast emitter
or generates a false campaign, finding or remediation lifecycle record.
The normal delivery worker provides v1/v2 HMAC signing, bounded retries and
backoff, DNS-result pinning, verified TLS hostname, HTTPS-only requests,
no redirects and bounded response reads. The HTTP 202 API response includes
`data: {accepted: true, delivery_id, event_id, status: "pending"}`:
**acceptance is not delivery success**. Inspect the existing deliveries
endpoint for `pending`, `delivered`, `failed`, or `cancelled`. Only a 2xx
transport response supports delivered status. Errors are generic.

The n8n receiver validates both signatures and performs producer-backed,
transactional receipt admission for test IDs, then acknowledges without
running a workflow. Repeat/retry IDs are suppressed within the same finite
24-hour at-most-once *admission* window, not exactly-once processing.

**Deferred verification:** no tests, live transport, native host, external
requests or vendor runtime execution. Later check registration reuse,
deactivation/deletion and in-flight races, cooldown/retry concurrency and
persistence, internal hostname allowlists, mixed DNS answers, DNS pinning,
TLS SNI/hostname checks, redirect refusal, 4 KiB response bounds and generic
failure output with isolated approved fixtures. Commercial wire parity unknown.
