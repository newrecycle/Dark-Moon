# `scan` component

Runs `darkmoon-ci` and publishes a GitLab **Code Quality** report (and optionally
a **SAST** report) from the findings.

```yaml
include:
  - component: $CI_SERVER_FQDN/<your-namespace>/darkmoon/scan@1.0.0
    inputs:
      target: "https://staging.example.com"
      fail-on: high
```

See the [repository README](../../README.md) for the full input list, secrets,
non-blocking mode, runner requirements, and the frozen [`CONTRACT.md`](../../CONTRACT.md).
