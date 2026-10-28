# Finding navigation and pages (F01)

Finding views now compose severity, status, category, campaign and target filters
with metadata search. The dashboard continuation adds project, MITRE technique
and active/excluded triage filters; see [the metric contract](dashboard-posture.md). Search covers ID, title, endpoint, category, campaign ID
and target ID, without scanning raw evidence. Sort supports severity, CVSS,
title, status, campaign ID and target ID in either direction. Campaign/finding
IDs break ties consistently, independent of storage order. Missing CVSS values
stay last; zero remains a real score.

The view renders 5/10/25/50/100 rows per page (50 by default). Changing filters,
search, sort or size returns to page one. Empty views show zero matches; pages
beyond the current result set clamp to the last available page. Matching and
workspace totals are both shown. Finding-title buttons support keyboard detail
opening, and the existing table can scroll horizontally on small screens.

## Navigation state

The fragment contains `q`, `severity`, `status`, `category`, `campaign_id`,
`target_id`, `project_id`, `mitre_attack_id`, `triage`, `sort`, `size` and `page`, omitting defaults. Browser history retains
filter and page transitions. The sidebar restores the last finding view during
the current visit; a URL survives reload and a fresh login. Closing a finding
dialog retains the view. No credentials are put in these URLs. Operators should
remember that their own search text can appear in browser history/shared URLs.

## REST contract

`GET /api/v1/vulnerabilities` supports the existing exact filters (including
`project_id`) plus `mitre_attack_id`, `triage=active|excluded`, `q`, `sort`,
`limit` and `offset`. Example:

```text
/api/v1/vulnerabilities?severity=high&status=confirmed&sort=cvss_desc&limit=25&offset=25
```

The envelope contains `data`, the filtered `total` before paging, `offset`,
`limit` and `sort`. Limits must be 1–500, offsets nonnegative integers, and search
at most 500 characters. Invalid controls return 400. Existing callers that omit
`limit` retain all matching records. List results still use the established
safe finding projection; raw evidence is not added.

The WebUI currently filters its loaded workspace snapshot and bounds table DOM
size. This improves rendering and navigation without claiming that snapshot
transfer or backend JSON loading is streamed/cursor-based.

## Validation

275 combined tests and 17 subtests passed, including API authentication, safe
projection, composed queries, zero/missing CVSS, deterministic ties, malformed
controls, exact page denominators and a 20,000-record dataset. A production JS
query test checks URL round-tripping and the same ordering/page boundaries.
Chromium acceptance covers composed controls, navigation restoration, browser
Back, distinct adjacent pages, empty results, clear, keyboard detail opening and
390px/1440px layouts. Screenshots were visually inspected. Browser CI retains
the `finding-filters` captures alongside the graph-path captures.
