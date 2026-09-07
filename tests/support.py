"""Cross-platform source-test launcher, independent of release packaging."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_cli():
    return [sys.executable, str(ROOT / "scripts" / "sdk_atlas.py")]
