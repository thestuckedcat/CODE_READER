#!/usr/bin/env python3
"""Create an SDK Code Atlas runtime without modifying the host Python."""
import argparse
import base64
import hashlib
import json
import os
import platform
import subprocess
import shutil
import tarfile
import urllib.request
import venv
import zipfile
from io import BytesIO
from pathlib import Path


def platform_key():
    machine = platform.machine().lower()
    if machine not in ("amd64", "x86_64"):
        raise SystemExit("Only x86_64/AMD64 runtimes are currently supported")
    return "windows-x86_64" if os.name == "nt" else "linux-x86_64"


def bootstrap_uv(runtime):
    """Install a pinned uv wheel locally when Debian lacks ensurepip/python3-venv."""
    version = "0.12.8"
    metadata = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/uv/{version}/json", timeout=60))
    candidates = [item for item in metadata["urls"] if item["filename"].endswith("x86_64.whl") and "manylinux" in item["filename"]]
    if not candidates:
        raise RuntimeError("Pinned uv Linux wheel is unavailable")
    item = candidates[0]
    payload = urllib.request.urlopen(item["url"], timeout=180).read()
    if hashlib.sha256(payload).hexdigest() != item["digests"]["sha256"]:
        raise RuntimeError("uv wheel hash mismatch")
    destination = runtime / "bootstrap-uv"
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        archive.extractall(destination)
    binaries = [path for path in destination.rglob("uv") if path.is_file()]
    if not binaries:
        raise RuntimeError("uv executable not found in pinned wheel")
    binary = binaries[0]
    binary.chmod(binary.stat().st_mode | 0o700)
    return binary


def bootstrap_npm(runtime):
    """Download a pinned npm CLI locally when Node is present without npm."""
    version = "11.12.0"
    metadata = json.load(urllib.request.urlopen(f"https://registry.npmjs.org/npm/{version}", timeout=60))
    payload = urllib.request.urlopen(metadata["dist"]["tarball"], timeout=180).read()
    algorithm, expected = metadata["dist"]["integrity"].split("-", 1)
    if algorithm != "sha512" or base64.b64encode(hashlib.sha512(payload).digest()).decode() != expected:
        raise RuntimeError("npm package integrity mismatch")
    destination = runtime / "bootstrap-npm"
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise RuntimeError("unsafe npm archive path")
        archive.extractall(destination)
    return destination / "package" / "bin" / "npm-cli.js"


def create_environment(runtime, environment):
    try:
        venv.EnvBuilder(with_pip=True, clear=False).create(environment)
        return None
    except (subprocess.CalledProcessError, SystemExit, OSError):
        if os.name == "nt":
            raise
    # Minimal Ubuntu/WSL installations omit ensurepip. uv and its managed Python
    # stay below runtime/ and do not require apt, sudo, or user-site mutation.
    if environment.exists():
        shutil.rmtree(environment)
    uv = bootstrap_uv(runtime)
    isolated = os.environ.copy()
    isolated["UV_CACHE_DIR"] = str(runtime / "uv-cache")
    isolated["UV_PYTHON_INSTALL_DIR"] = str(runtime / "python-managed")
    subprocess.run([str(uv), "python", "install", "3.12"], check=True, env=isolated)
    subprocess.run([str(uv), "venv", "--python", "3.12", str(environment)], check=True, env=isolated)
    return str(uv)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", help="Optional local directory used with --no-index")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    runtime = root / "runtime" / platform_key()
    environment = runtime / "venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    uv = None
    metadata_path = runtime / "runtime.json"
    if metadata_path.is_file():
        previous = json.loads(metadata_path.read_text(encoding="utf-8"))
        bootstrap = previous.get("bootstrap", "")
        if bootstrap.startswith("uv:") and Path(bootstrap[3:]).is_file():
            uv = bootstrap[3:]
    if uv:
        usable = python.is_file() and subprocess.run([str(python), "-c", "import clang.cindex"], capture_output=True).returncode == 0
    else:
        usable = python.is_file() and subprocess.run([str(python), "-m", "pip", "--version"], capture_output=True).returncode == 0
    if not usable:
        runtime.mkdir(parents=True, exist_ok=True)
        if environment.exists():
            shutil.rmtree(environment)
        uv = create_environment(runtime, environment)
    requirement = root / "requirements.txt"
    if uv:
        command = [uv, "pip", "install", "--python", str(python), "-r", str(requirement)]
        isolated = os.environ.copy()
        isolated["UV_CACHE_DIR"] = str(runtime / "uv-cache")
        isolated["UV_PYTHON_INSTALL_DIR"] = str(runtime / "python-managed")
        if args.wheelhouse:
            command += ["--no-index", "--find-links", str(Path(args.wheelhouse).resolve())]
        subprocess.run(command, check=True, env=isolated)
    else:
        command = [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirement)]
        if args.wheelhouse:
            command += ["--no-index", "--find-links", str(Path(args.wheelhouse).resolve())]
        subprocess.run(command, check=True)
    npm = shutil.which("npm")
    node = shutil.which("node")
    node_runtime = runtime / "node"
    viewer_dependency = "unavailable"
    if (node_runtime / "node_modules" / "linkedom").is_dir():
        viewer_dependency = str(node_runtime / "node_modules")
    else:
        if node and not npm:
            npm = str(bootstrap_npm(runtime))
        if npm:
            npm_command = [npm] if Path(npm).suffix.lower() not in (".js", ".cjs") else [node, npm]
            subprocess.run(npm_command + ["install", "--prefix", str(node_runtime), "--no-save", "linkedom@0.18.12"], check=True)
            viewer_dependency = str(node_runtime / "node_modules")
    probe = subprocess.run(
        [str(python), "-c", "import clang.cindex,json,sys; clang.cindex.Index.create(); print(json.dumps({'python':sys.version,'executable':sys.executable}))"],
        check=True, capture_output=True, text=True,
    )
    metadata = {
        "platform": platform_key(),
        "requirements_sha256": hashlib.sha256(requirement.read_bytes()).hexdigest(),
        "probe": json.loads(probe.stdout),
        "isolated": True,
        "viewer_dependency": viewer_dependency,
        "bootstrap": "uv:" + uv if uv else "stdlib-venv",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
