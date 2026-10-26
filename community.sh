#!/usr/bin/env bash
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export DARKMOON_DATA_DIR="${DARKMOON_DATA_DIR:-${TASK_REPO}/darkmoon-settings}"
export DARKMOON_REPORTS_DIR="${DARKMOON_REPORTS_DIR:-${TASK_REPO}/reports}"
export PYTHONPATH="${TASK_REPO}/mcp${PYTHONPATH:+:${PYTHONPATH}}"
exec "${DARKMOON_PYTHON:-python3}" -m community.server --repo "$TASK_REPO" "$@"
