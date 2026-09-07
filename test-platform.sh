#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/runtime/linux-x86_64/venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then echo 'Run setup.sh first.' >&2; exit 2; fi
exec "$PYTHON" "$ROOT/scripts/test_platform.py"
