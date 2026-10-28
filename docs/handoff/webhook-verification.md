# Webhook delivery verification scope (28 October 2026)

Source-side verification added for the fork's signed synthetic delivery contract.
The network boundary tests replace DNS, HTTPSConnection and TCP dialing with
mocks: no external webhook is sent. The Python suite exercises the real loopback
REST handler and transactional store, including administrator authorization,
masked list/detail/registration, bodyless/empty test admission, forbidden
overrides, missing/disabled/deleted hooks, queue caps, per-hook persisted cooldown,
unique replay IDs, signing, selected-hook delivery, bounded retry failure and
generic delivery metadata. It also inspects DNS-result pinning, HTTPS-only rules,
TLS context hostname verification, private/mixed DNS result rejection, exact
internal-host allowlist, 302 status (not redirected), and 4 KiB response reads.

The n8n receiver contract checks v1/v2 HMAC with synthetic event receipt
admission and duplicate suppression, plus no workflow data on valid test
events, and rejects malformed test purpose. These tests use in-memory
receipt mocks; native receiver restart is a separate test boundary.

The existing native n8n host CI workflow runs within Docker --network none.
Its previous passing lifecycle evidence predates the new synthetic tests.
Transport mocks cannot prove a real TLS handshake, server certificate behavior,
OS DNS resolver behavior, full worker/deletion races, or actual network delivery.
Native host, offline CI and real transport evidence must be recorded separately
when available; no commercial vendor-wire parity is claimed.
