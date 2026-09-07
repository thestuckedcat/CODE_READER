#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_PYTHON="${PYTHON:-python3}"
exec "$HOST_PYTHON" "$ROOT/scripts/setup_runtime.py" "$@"
