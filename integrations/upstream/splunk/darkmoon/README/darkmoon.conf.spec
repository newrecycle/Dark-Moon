[settings]
base_url = <string>
* Base URL of the Darkmoon Pro REST API (e.g. https://darkmoon.internal:8443).
* No trailing slash. The alert action refuses non-https URLs unless verify_tls=0.

verify_tls = <boolean>
* Verify the Darkmoon TLS certificate on outbound calls. Default 1 (recommended).
* Set to 0 only in a trusted, isolated test lab.
