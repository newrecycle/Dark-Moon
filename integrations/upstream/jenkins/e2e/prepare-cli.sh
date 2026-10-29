#!/usr/bin/env bash
# Build-only bundling of pinned Node dependencies into the HPI CLI.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v npm >/dev/null || { echo "Node/npm 18+ required to build Jenkins HPI" >&2; exit 1; }
node -e 'if (+process.versions.node.split(".")[0] < 18) process.exit(1)'
expected="$(node -p "require('./src/main/resources/darkmoon-client/snapshot.json').sha256")"
actual="$(sha256sum src/main/resources/darkmoon-client/darkmoon-ci.cjs | cut -d' ' -f1)"
[ "$expected" = "$actual" ] || { echo "Pinned Jenkins CLI snapshot checksum mismatch" >&2; exit 1; }
expected_launcher="$(node -p "require('./src/main/resources/darkmoon-client/snapshot.json').launch_adapter_sha256")"
actual_launcher="$(sha256sum cli/oss-launch.cjs | cut -d' ' -f1)"
[ "$expected_launcher" = "$actual_launcher" ] || { echo "Pinned Jenkins launch adapter checksum mismatch" >&2; exit 1; }
npm install --no-audit --no-fund --no-save --no-package-lock zod@3.25.76 esbuild@0.25.12 >&2
mkdir -p target/jenkins-bundled-cli/darkmoon-client
node_modules/.bin/esbuild src/main/resources/darkmoon-client/darkmoon-ci.cjs \
  --bundle --platform=node --format=cjs --target=node18 \
  --outfile=target/jenkins-bundled-cli/darkmoon-client/darkmoon-ci.cjs
node --check target/jenkins-bundled-cli/darkmoon-client/darkmoon-ci.cjs
node target/jenkins-bundled-cli/darkmoon-client/darkmoon-ci.cjs --help >/dev/null
node --test test/oss-launch.test.cjs
