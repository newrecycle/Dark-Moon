# Changelog

## 1.0.0

Initial release of the Darkmoon Security Posture Grafana app.

- App plugin `darkmoon-securityposture-app` with a nested Go backend datasource `darkmoon-securityposture-datasource`.
- Backend query types: `overview`, `campaigns`, `findings`, `targets`, `timeseries`, `pullrequests`, `retest`.
- `CheckHealth` against `/api/v1/system/info` with Pro/OSS edition detection.
- Safe `CallResource` proxy for evidence metadata.
- Redaction enforced in the backend: frames are built only from safe allowlist fields; evidence, descriptions, raw output and tokens are never surfaced.
