#!/usr/bin/env bash
#
# smoke_gpu_hash.sh — GPU hashing smoke test for the DarkMoon candidate image.
#
# Proves the GPU-accelerated hash-cracking path actually works inside a container
# that has GPU access. Run it INSIDE the built image with GPU attached, e.g.:
#
#   docker run --gpus all --rm <darkmoon-candidate-image> \
#       tools/tests/smoke_gpu_hash.sh
#
# (Typically invoked from a disposable verification container built from the
#  candidate, never against a running production container.)
#
# What it verifies:
#   1. hashcat is installed and runnable.
#   2. hashcat enumerates at least one GPU OpenCL/CUDA device (not just CPU).
#   3. A real, tiny GPU crack succeeds on that device (known MD5 -> plaintext).
#
# Exit codes:
#   0  GPU hashing verified working
#   1  hashcat missing, or present but the GPU is not usable (real failure)
#   2  No GPU device present in this environment (SKIP — not a code defect;
#      re-run on a GPU host with `docker run --gpus all`)
#
set -uo pipefail

HASHCAT="$(command -v hashcat || true)"
if [ -z "$HASHCAT" ]; then
  echo "FAIL: hashcat not found on PATH"
  exit 1
fi

echo "== hashcat version =="
hashcat --version || { echo "FAIL: hashcat --version failed"; exit 1; }

echo
echo "== device enumeration (hashcat -I) =="
INFO="$(hashcat -I 2>&1)" || true
echo "$INFO"

# Collect GPU (non-CPU) device ids from the enumeration output.
# Device lines look like:  * Device #1: NVIDIA GeForce RTX ..., ...
# CPU-only backends (pocl) are flagged "skipped (CPU)" and excluded.
GPU_IDS="$(printf '%s\n' "$INFO" \
  | grep -E '^\s*\*\s*Device #[0-9]+:' \
  | grep -viE 'cpu|skipped \(cpu\)' \
  | grep -oE 'Device #[0-9]+' \
  | grep -oE '[0-9]+')"

if [ -z "$GPU_IDS" ]; then
  echo
  echo "SKIP: no GPU OpenCL/CUDA device detected (only CPU / none present)."
  echo "      This is expected on GPU-less hosts. Re-run with: docker run --gpus all ..."
  exit 2
fi

echo
echo "== GPU device(s) detected: $(echo "$GPU_IDS" | tr '\n' ' ') =="

# Use the first GPU device for the micro-crack.
GPU_ID="$(echo "$GPU_IDS" | head -1)"

# Deterministic, instant crack target:
#   md5("password") = 5f4dcc3b5aa765d61d8327deb882cf99
HASH="5f4dcc3b5aa765d61d8327deb882cf99"
PLAIN="password"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
printf '%s\n' "$HASH" > "$TMP/h.txt"
printf '%s\n' "$PLAIN" > "$TMP/w.txt"

echo
echo "== micro-crack on GPU device #$GPU_ID (md5 of '$PLAIN') =="
OUT="$(hashcat -m 0 -a 0 "$TMP/h.txt" "$TMP/w.txt" \
        -d "$GPU_ID" --force --potfile-disable -O 2>&1)" || true
echo "$OUT"

if printf '%s\n' "$OUT" | grep -q "$PLAIN"; then
  echo
  echo "PASS: GPU hashing verified — device #$GPU_ID cracked the test hash."
  exit 0
else
  echo
  echo "FAIL: GPU device #$GPU_ID present but micro-crack did not recover '$PLAIN'."
  echo "      Inspect OpenCL/CUDA attach on the host (drivers, --gpus, NVIDIA_DRIVER_CAPABILITIES)."
  exit 1
fi
