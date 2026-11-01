# Webhook retry and restart acceptance — 1 November 2026

API10 now has an actual fork-runtime failure-exhaustion checkpoint. A disposable
HTTPS receiver on owned loopback returned 503 for every request. TLS verification,
normal runtime workers, production retry policy and the clock were unchanged.

The same delivery reached five attempts and terminal `failed` with HTTP 503.
Observed intervals were **20.82, 40.24, 80.51 and 160.31 seconds**. Every callback
passed both body-HMAC and V2-HMAC checks, and delivery/event identity remained
stable across retries.

After attempt one, the runtime was stopped and restarted against its persisted
state. The pending attempt count and test-admission cooldown survived; a repeat
test request returned 429. The remaining attempts followed normal backoff.
After exhaustion, a second restart retained the five-attempt terminal result
and did not redeliver during the subsequent observation. The hook was then
deleted and the owned runtime/receiver stopped.

This closes the previously unexecuted **fork failure exhaustion and restart**
checkpoint for this scenario. The earlier reference failure observation remains
separate: its test route exhausted five synchronous attempts before responding,
whereas the fork admits asynchronously and exposes delivery status. Admission
responses are not interchangeable delivery results.

Sanitized derived callback metadata, HTTP outcomes and capture hashes are
retained outside Git. Credentials, certificates, signing keys and raw session
material are excluded. This does not close all event families, concurrent-hook
behavior, downstream consumer/replay matrices or full API10 parity. No scan,
model, external recipient or publication was involved.
