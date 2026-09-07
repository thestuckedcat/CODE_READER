"""Content-addressed artifacts and crash-safe single-writer checkpoints."""
import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path

from ..domain.contracts import SCHEMA_VERSION, TOOL_VERSION

VERSION = TOOL_VERSION
SCHEMA = SCHEMA_VERSION


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encoded(value)).hexdigest()


def filehash(path):
    try:
        return digest(Path(path).read_bytes())
    except OSError:
        return None


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def write(path, data):
    atomic(path, encoded(data))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def envelope(kind, payload, task="python", inputs="", origin="python"):
    return {
        "schema_version": SCHEMA,
        "record_kind": kind,
        "record_id": digest([kind, payload]),
        "payload": payload,
        "provenance": {
            "producer_kind": origin,
            "producer_version": VERSION,
            "task_id": task,
            "input_hash": inputs,
            "configuration_id": None,
            "evidence_ids": [],
        },
    }


def payload(path):
    return read(path)["payload"]


class Store:
    """Artifact repository used by application services through a small API."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "index.sqlite", timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(
            """CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, receipt TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);"""
        )
        self.run_id = uuid.uuid4().hex
        self.run = self.root / "runs" / self.run_id
        self.run.mkdir(parents=True)
        self.entries = []

    def put(self, name, data, scope="run", origin="python", inputs=""):
        if name.endswith(".jsonl"):
            raw = b"".join(encoded(envelope(name[:-6], item, scope, inputs, origin)) + b"\n" for item in data)
        else:
            raw = encoded(envelope(name.rsplit(".", 1)[0], data, scope, inputs, origin))
        artifact_hash = digest(raw)
        path = self.root / "objects" / artifact_hash[:2] / (artifact_hash + Path(name).suffix)
        if not path.exists():
            atomic(path, raw)
        entry = {
            "logical_name": name,
            "scope_key": scope,
            "relative_path": str(path.relative_to(self.root)),
            "sha256": artifact_hash,
            "bytes": len(raw),
        }
        self.entries.append(entry)
        write(self.run / "artifacts.json", envelope("artifacts", {"run_id": self.run_id, "entries": self.entries}))
        return entry

    def get(self, entry):
        path = self.root / entry["relative_path"]
        raw = path.read_bytes()
        if digest(raw) != entry["sha256"]:
            raise ValueError("Artifact hash mismatch: " + str(path))
        if path.suffix == ".jsonl":
            return [json.loads(line)["payload"] for line in raw.splitlines()]
        return json.loads(raw)["payload"]

    def cache_get(self, key):
        row = self.db.execute("SELECT receipt FROM cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache_put(self, key, receipt):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (key, json.dumps(receipt)))
        self.put("checkpoint.json", {"task_key": key, "receipt": receipt, "status": "succeeded"}, key)

    def meta(self, key, default=None):
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def setmeta(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, json.dumps(value)))

    def close(self):
        self.db.close()


class Lock:
    """OS advisory lock; released on process death, never stale-file deletion."""

    def __init__(self, root):
        self.path = Path(root) / "writer.lock"

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        self.file.write(b"0")
        self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("Another writer is running for this output directory")
        return self

    def __exit__(self, *args):
        self.file.close()
