# Commercial Pro static parity audit

This directory holds **originally authored analysis** of a pinned commercial Pro container and the independent `pro` fork. It does **not** contain copies of vendor commercial source, compiled bundles, native binaries or large decompiler pseudocode. Audit outputs and fork implementation are deliberately separated.

## Current audit (2026-10-27)

- [Evidence review and next implementation tests](2026-10-27/DARKMOON_AUDIT_REVIEW.md)
- [Static API discrepancy crosswalk (13 entries)](2026-10-27/verified-static-api-gaps.csv)
- [Angular component inventory](2026-10-27/angular-components.csv)
- [Ghidra function-coverage by native module](2026-10-27/ghidra-function-coverage.csv)
- [Packaged test file overlap](2026-10-27/packaged-test-overlap.csv)
- [126-test function crosswalk](2026-10-27/original-test-function-crosswalk.csv)
- [Machine-readable verified extraction counts and explicit exclusions](2026-10-27/review-summary.json)
- [Full 52-declaration method/path inventory](../handoff/actual-pro-endpoint-crosswalk-2026-10-27.md)
- [28-item implementation backlog](../handoff/actual-pro-parity-ledger-2026-10-27.md)
- [Pinned image and security considerations](../handoff/actual-pro-image-baseline-2026-10-27.md)
- [Reproducible audit script](../../tools/pro-audit/darkmoon_pro_forensic_audit.py) and [execution guide](../../tools/pro-audit/README.md)

### Verification and provenance

The evidence comes from user-supplied, locally extracted image `ascit/opencode-darkmoon-pro@sha256:48248382877ec1fd7362d2268656956268129d5ea565befab3a24436ea2fc907`; fork snapshot at `84c9d360df5eefc059ed26eae4d6a1fc97c4603e`. The official packaged tests were **not run** against the commercial distribution. No authorized commercial runtime response snapshots were recorded. 52 counts decorator declarations (including aliases); 126 counts genuine packaged tests; 76 acceptance entries are proposed, not executed. Ghidra's 46,276/46,290 successful low-level decompilations are **not** recovery of that percentage of original Python logic.

### Exclusions from this public repository

The original 169 MB upload also contained proprietary distribution artifacts (`.so`, `.pyi`, compiled Angular JS, source tests), large native disassembly/Ghidra pseudocode, duplicate packages, and a fork checkout. Those are not republished here. Original private audit material stays with the uploader. The generated report and CSV summaries are sufficient to carry forward known parity issues and triage follow-up; they do **not** constitute an exhaustive source archive. No execution or live API verification occurred during this documentation commit.

Security improvements in the independent fork (authentication, credential masking, sandbox restrictions, report protection) must not be weakened merely to imitate vendor behavior.
