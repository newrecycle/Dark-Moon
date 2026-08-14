#!/usr/bin/env bash
#
# verify-toolbox.sh — manifest-driven toolbox verifier (Phase 6 refactor).
#
# Reads the canonical inventory (tools/toolbox-manifest.json) — NOT a regex of
# executor.py — and proves every required runtime record is present, probes
# cleanly under a hard timeout, asserts its pinned version, and has its required
# data directories. Host-only and blocked-but-installed records are reported
# distinctly and never fail the image.
#
# Usage:
#   tools/verify-toolbox.sh                 # probe local PATH (inside a container)
#   tools/verify-toolbox.sh --json         # machine-readable output
#   tools/verify-toolbox.sh --manifest P   # override inventory path
#   tools/verify-toolbox.sh --gpu          # also run the GPU hashing smoke test
#                                          # (needs a GPU host: docker run --gpus all)
#
# Exit code: 0 = all required runtime records pass; 1 = at least one failure.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="${MANIFEST:-$HERE/toolbox-manifest.json}"
PY="$(command -v python3 || echo /opt/darkmoon/python/bin/python3)"

# Split out the --gpu switch; forward everything else to the Python verifier.
GPU=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --gpu) GPU=1 ;;
    *)     ARGS+=("$a") ;;
  esac
done

[ -f "$MANIFEST" ] || { echo "ERROR: inventory not found at $MANIFEST"; exit 1; }
[ -x "$PY" ] || PY=python3

"$PY" "$HERE/verify_toolbox.py" --manifest "$MANIFEST" "${ARGS[@]}"
rc=$?

if [ "$GPU" -eq 1 ]; then
  SMK="$HERE/tests/smoke_gpu_hash.sh"
  if [ -x "$SMK" ]; then
    echo
    echo "== GPU hashing smoke test =="
    "$SMK"
    src=$?
    # The smoke test exits 2 (SKIP) when no GPU is present — that does not fail
    # the overall verification; only a real failure (1) does.
    if [ "$src" -eq 1 ]; then rc=1; fi
  else
    echo "WARN: $SMK not found; skipping GPU smoke test" >&2
  fi
fi

exit $rc
