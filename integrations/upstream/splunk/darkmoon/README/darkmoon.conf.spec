[settings]
base_url = <string>
* Base URL of the Darkmoon Pro REST API (e.g. https://darkmoon.internal:8443).
* No trailing slash. The alert action refuses non-https URLs unless verify_tls=0.

verify_tls = <boolean>
* Verify the Darkmoon TLS certificate on outbound calls. Default 1 (recommended).
* Set to 0 only in a trusted, isolated test lab.

credential_realm = <string>
* Opaque storage/passwords generation reference created by the setup page.
* Format darkmoon- followed by 32 lowercase hexadecimal characters. Not a secret.
* Empty preserves named empty-realm legacy credentials; no arbitrary first-key fallback.
* Each new token is saved to a new realm before the base URL/reference are updated.
* Do not copy a reference between unrelated connections or delete generations in use.
