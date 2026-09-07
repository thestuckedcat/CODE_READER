#!/usr/bin/env python3
"""Stable executable shim; CLI behavior lives in atlas.interfaces.cli."""
import sys
from pathlib import Path

package = Path(__file__).resolve().parent.parent
if (package / "runtime" / "site").is_dir():
    sys.path.insert(0, str(package / "runtime" / "site"))

from atlas.interfaces.cli import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("ERROR: " + str(error), file=sys.stderr)
        raise SystemExit(2)
