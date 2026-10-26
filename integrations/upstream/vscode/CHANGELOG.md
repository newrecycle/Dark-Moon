# Changelog

All notable changes to the Darkmoon VS Code extension are documented here.

## Unreleased
- One-time, non-intrusive GitHub star CTA: after Darkmoon first delivers real
  findings in VS Code (never on activation, on empty results, or in demo/fixtures
  mode), a single dismissible notification invites starring the open source
  project. Shown at most once (persisted in `globalState`); no target, host or
  finding data is read or stored. Opt out with the new `darkmoon.growthCta.enabled`
  setting or the `DARKMOON_DISABLE_GROWTH_CTA` environment variable.
- Marketplace metadata: add `homepage` and broaden `categories` to Testing and
  Linters alongside Other.

## 0.1.3 - 2026-09-25
- Marketplace listing: publication status in the README.

## 0.1.2 - 2026-09-24
- Marketplace listing: Darkmoon ecosystem block (install links, website, star CTA).

## 0.1.1 - 2026-09-24
- Marketplace listing: screenshots render with absolute URLs.

## 0.1.0 - 2026-09-24
- Initial release: Campaigns tree, Vulnerabilities table (filter/sort/search),
  finding detail, Reports preview, launch-campaign and refresh commands.
- Cross-edition via @darkmoon_ai/client (OSS CLI + Pro REST) with capability
  degradation. Redaction-safe reports and findings. Secrets in SecretStorage.
- Bundled demo data (`darkmoon.dev.useFixtures`) uses synthetic *Demo Shop*
  fixtures only — no real hosts, credentials, tokens or evidence ship in the VSIX.
- Licensed under MIT.
