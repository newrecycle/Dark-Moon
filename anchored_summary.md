## Objective
- Fix the toolbox audit/verifier so impacket (and netexec) classify and verify correctly, and make the full verification pass: manifest audit, static suite (`run_tests.py`), and runtime `verify_toolbox.py` (phase8). End state: 0 verification failures.

## Important Details
- `tools/audit_toolbox.py` (lines 92-93): `exact = has(rf"install .*\b{up}=={resolved}\b") or has(rf"git\+https://.*{up}\.git@{resolved}")`. For a git-pinned tool, `resolved_version` must equal the commit in `setup_py.sh` for the audit to mark it `exact_reproducible`.
- `tools/verify_toolbox.py` `concrete(v)` (line 126): a 40-hex string starts with a digit → was treated as a concrete PEP440 version, so a commit-hash `resolved_version` triggered a strict `meta == rv` comparison and produced WRONG-VERSION. Fixed: commit SHAs (7-64 hex) now return `False` (non-concrete → version check skipped; audit proves reproducibility).
- `tools/verify_toolbox.py` metadata comparison (line ~228): `str(meta)==str(rv)` failed for netexec because installed metadata is `1.4.0+0.806e4c73` (PEP440 local suffix) vs pin `v1.4.0`. Fixed: compare **base** versions (strip `+local` suffix and leading `v`).
- `version_assert` field exists in the manifest but is NOT executed by `verify_toolbox.py` (data only); commit-pinned impacket is reported `version unverified` (honest, not a failure).
- Dockerfile bakes `tools/toolbox-manifest.json` (line 355) and `tools/verify_toolbox.py` (line 356) INTO the image; phase8 runs `verify_toolbox.py` inside the container against the baked manifest. Any fix to either requires a rebuild (cache reuse makes it fast, ~6s).
- cmseek is pinned with `--branch v.1.1.3` (dot after v) in `setup_py.sh`; the real CMSeeK tag. Build succeeds → valid tag.

## Work State
### Completed
- `build_manifest.py`: impacket `resolved_version` + `resolved_ref` both = commit `4c09897a8645818e873787f2c79ec1bce90c5777` (was the dev string `0.14.0.dev0+...`); regenerated `toolbox-manifest.json`.
- `verify_toolbox.py`: (1) `concrete()` treats git commit SHAs as non-concrete; (2) metadata comparison matches base versions (strips `+local`); (3) earlier: `is_wrapper` shell-only, support-only empty-exe SKIP (no change needed this round, still in place).
- `setup_py.sh`: bloodhound wrappers → `bloodhound-python`, impacket → git commit (from prior session, intact).
- `run_tests.py` `test_no_silent_failure`: updated 2 stale assertions — `impacket-pin` now checks `git+https://github.com/fortra/impacket.git@4c09897a` (was `impacket==0.12.0`); `cmseek-pin` now checks `--branch v.1.1.3` (was `v1.1.3`).
- Rebuilt image `newrecycle/darkmoon:candidate` and re-ran phase8.

### Active
- None pending. All gates green.

### Blocked
- None.

## Next Move
- All verification gates pass. Optional: commit the changes (build_manifest.py, verify_toolbox.py, run_tests.py) and push. No rebuild needed unless source changes again.
- GPU smoke is skipped on this GPU-less host (gpu_rc=2) — expected; re-run with `docker run --gpus all ...` on a GPU host if desired.

## Relevant Files
- `/home/justin/old-darkmoon/Dark-Moon/tools/build_manifest.py` — impacket record (resolved_version/resolved_ref = commit).
- `/home/justin/old-darkmoon/Dark-Moon/tools/verify_toolbox.py` — `concrete()` + base-version metadata compare.
- `/home/justin/old-darkmoon/Dark-Moon/tools/audit_toolbox.py` — pip/git classification (lines 92-93); run to (re)generate `audit-report.json`.
- `/home/justin/old-darkmoon/Dark-Moon/tools/tests/run_tests.py` — `no-silent-failure` assertions fixed.
- `/home/justin/old-darkmoon/Dark-Moon/setup_py.sh` — impacket git pin (line 45); cmseek `--branch v.1.1.3` (line 269).
- `/home/justin/old-darkmoon/Dark-Moon/Dockerfile` — bakes manifest + verifier (lines 355-356).
- `/home/justin/old-darkmoon/Dark-Moon/tools/audit-report.json`, `tools/toolbox-manifest.json` — generated artifacts.
- `/tmp/phase8.sh`, `/tmp/phase8.log`, `/tmp/build.log` — phase8 runner + logs.

## Verification Results (final)
- audit: total 68, exact 64, floating 1 (lightpanda — accepted nightly exception); impacket = exact_reproducible.
- static suite: 11 groups passed, 0 failed; 13/13 atomic checks.
- runtime verify (phase8): passed 65, failed 0, RESULT PASS (verify_rc=0); gpu_rc=2 (skip-no-gpu).
