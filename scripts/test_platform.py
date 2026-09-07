#!/usr/bin/env python3
"""Verify the current platform's isolated runtime and behavioral suite."""
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    expected = "windows-x86_64" if os.name == "nt" else "linux-x86_64"
    runtime = root / "runtime" / expected / "runtime.json"
    if not runtime.is_file():
        raise SystemExit("Isolated runtime is missing; run scripts/setup_runtime.py first")
    metadata = json.loads(runtime.read_text(encoding="utf-8"))
    if metadata.get("platform") != expected or not metadata.get("isolated"):
        raise SystemExit("Runtime metadata does not match this platform")
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    doctor = subprocess.run([sys.executable, str(root / "scripts" / "sdk_atlas.py"), "doctor"], check=False)
    tests = subprocess.run([sys.executable, str(root / "tests" / "run_tests.py")], check=False)
    node_path = root / "runtime" / expected / "node" / "node_modules"
    viewer_exit = None
    if node_path.is_dir():
        environment = os.environ.copy()
        environment["NODE_PATH"] = str(node_path)
        with tempfile.TemporaryDirectory(prefix="atlas viewer ") as temporary:
            temporary = Path(temporary)
            html = temporary / "fixture-overview.html"
            generated = subprocess.run([
                sys.executable, str(root / "scripts" / "sdk_atlas.py"), "run",
                "--repo", str(root / "tests" / "fixture"), "--out", str(temporary / "analysis"), "--html", str(html),
            ], env=environment, check=False)
            viewer = subprocess.run(["node", str(root / "tests" / "test_viewer.js"), str(html)], env=environment, check=False) if generated.returncode == 0 else generated
            viewer_exit = viewer.returncode
    result = {
        "platform": expected,
        "host": platform.platform(),
        "doctor_exit": doctor.returncode,
        "tests_exit": tests.returncode,
        "viewer_exit": viewer_exit,
        "status": "passed" if doctor.returncode == 0 and tests.returncode == 0 and viewer_exit in (None, 0) else "failed",
    }
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
