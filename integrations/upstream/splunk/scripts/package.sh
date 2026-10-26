#!/usr/bin/env bash
#
# Build the Splunkbase package: dist/darkmoon-<version>.tar.gz
# Top-level dir = app id (darkmoon). No local/, no junk, no secrets.
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/darkmoon"
VERSION="$(grep -E '^version' "$APP/default/app.conf" | head -1 | sed 's/.*=\s*//')"
OUT="$ROOT/dist/darkmoon-${VERSION}.tar.gz"
mkdir -p "$ROOT/dist"

# Stage a clean copy so we never ship local/, caches or scratch.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -r "$APP" "$STAGE/darkmoon"
find "$STAGE/darkmoon" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$STAGE/darkmoon" -type d -name 'local' -prune -exec rm -rf {} +
find "$STAGE/darkmoon" -type f \( -name '*.pyc' -o -name 'local.meta' -o -name '.DS_Store' \) -delete

tar -C "$STAGE" --owner=0 --group=0 -czf "$OUT" darkmoon
echo "Built $OUT"
tar -tzf "$OUT" | head -20
echo "..."
echo "size: $(du -h "$OUT" | cut -f1)"
