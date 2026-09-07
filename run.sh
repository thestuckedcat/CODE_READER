#!/bin/sh
set -eu
ATLAS_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$(uname -s):$(uname -m)" in
  Linux:x86_64) ATLAS_PLATFORM=linux-x86_64 ;;
  *) echo 'Unsupported bundled runtime: requires Linux glibc x86_64. Use run.ps1 on Windows x64.' >&2; exit 2 ;;
esac
ATLAS_PY="$ATLAS_DIR/runtime/$ATLAS_PLATFORM/venv/bin/python"
if [ ! -f "$ATLAS_PY" ]; then ATLAS_PY="$ATLAS_DIR/runtime/$ATLAS_PLATFORM/python/bin/python3.12"; fi
if [ ! -f "$ATLAS_PY" ]; then echo 'Isolated runtime missing; run setup.sh first.' >&2; exit 2; fi
# ZIP extractors may discard Unix executable bits.
chmod u+x "$ATLAS_PY" 2>/dev/null || true
export PATH="$(dirname "$ATLAS_PY"):$PATH"
if [ -d "$ATLAS_DIR/runtime/$ATLAS_PLATFORM/site" ]; then
  chmod u+x "$ATLAS_DIR/runtime/$ATLAS_PLATFORM/site/cmake/data/bin/cmake" "$ATLAS_DIR/runtime/$ATLAS_PLATFORM/site/ninja/data/bin/ninja" 2>/dev/null || true
  export PYTHONPATH="$ATLAS_DIR/runtime/$ATLAS_PLATFORM/site${PYTHONPATH:+:$PYTHONPATH}"
  export PATH="$ATLAS_DIR/runtime/$ATLAS_PLATFORM/site/cmake/data/bin:$ATLAS_DIR/runtime/$ATLAS_PLATFORM/site/ninja/data/bin:$ATLAS_DIR/runtime/$ATLAS_PLATFORM/site/ninja:$PATH"
fi
exec "$ATLAS_PY" "$ATLAS_DIR/scripts/sdk_atlas.py" "$@"
