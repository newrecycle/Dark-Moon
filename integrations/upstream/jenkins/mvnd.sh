#!/usr/bin/env bash
# Dockerized Maven 3.9.6 + JDK 21 (isolated, reproducible). Usage: ./mvnd.sh <maven args>
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec docker run --rm \
  -v "$DIR":/work \
  -v "$HOME/.m2-darkmoon":/root/.m2 \
  -w /work \
  --network host \
  maven:3.9.6-eclipse-temurin-21 \
  mvn -B -ntp "$@"
