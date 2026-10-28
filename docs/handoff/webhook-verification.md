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

## Verified GitHub Actions evidence

The dedicated offline run
[40665290927](https://github.com/newrecycle/Dark-Moon/actions/runs/40665290927)
passed **21 Python tests** across webhook API, signed delivery, rate limiting,
durable receiver receipts, mocked DNS/TLS boundaries and two real local TLS
handshakes. Its **n8n-receiver job also passed** the compiled n8n package's unit
tests, signed synthetic receiver/replay checks, and all 12 adversarial
integration contracts.

The two real TLS checks use an ephemeral CA and generated server certificates
on 127.0.0.1, with test DNS constrained to loopback. A matching certificate
hostname/SNI succeeds and a 302 response is not followed; a certificate from
the same CA with a mismatched hostname is rejected before sending HTTP content.
No external webhook destination is contacted.

The earlier
[40664769668](https://github.com/newrecycle/Dark-Moon/actions/runs/40664769668)
passed 19 webhook Python tests before the added real TLS cases. The general
[regression gate](https://github.com/newrecycle/Dark-Moon/actions/runs/40664545263)
and [browser gate](https://github.com/newrecycle/Dark-Moon/actions/runs/40664545273)
passed. A separate
[campaign regression run](https://github.com/newrecycle/Dark-Moon/actions/runs/40664769472)
reported 390 passing tests and 66 subtests, but one unrelated scheduler
compatibility test failed. That suite is not described as green.

## Still deferred or separate

The native n8n host lifecycle runs in an isolated Docker --network none
workflow and must be assessed independently from the passing compiled
package-level tests. The in-memory n8n receipt contract does not prove
cross-process native host restart behavior. The TLS fixture is a local
handshake proof, not verification of arbitrary external CA chains, DNS
resolver behavior in production, or in-flight deletion races. No actual
external webhook was sent and no commercial vendor-wire equivalence is
claimed. Direct splunk_hec transport remains unsupported.
