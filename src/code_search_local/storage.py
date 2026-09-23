"""Durable local state and immutable index generations.

Only the manifest replacement publishes a generation. Readers never open staging
files, and unfinished generations are harmless after a process crash.
"""

import fcntl
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import threading
import uuid
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sync_dir(path: Path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, value, *, mode: int = 0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), mode)
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_dir(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


class ServiceLock:
    def __init__(self, root: Path, name="service.lock"):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.stream = (root / name).open("a+")
        try:
            fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.stream.close()
            raise RuntimeError(f"A code-search-local service already owns {root}") from None

    def close(self):
        if not self.stream.closed:
            fcntl.flock(self.stream, fcntl.LOCK_UN)
            self.stream.close()


def project_id(root: str) -> str:
    return hashlib.sha256(root.encode()).hexdigest()


class State:
    """Transactional counters, registry and durable jobs. Safe across threads."""

    def __init__(self, root: Path, publish=None):
        self.path = root / "state.sqlite3"
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        rows = dict(self.db.execute("SELECT key,value FROM state"))
        self.value = (
            json.loads(rows["snapshot"])
            if "snapshot" in rows
            else {
                "schema_version": 1,
                "projects": {},
                "jobs": {},
                "shared": {},
            }
        )
        self.value.update(daemon_id=uuid.uuid4().hex, sequence=0, started_at=utc_now(), online=True)
        self.value["shared"]["model_resident"] = False
        self.publish = publish
        self._save()

    def _save(self):
        self.db.execute(
            "INSERT OR REPLACE INTO state VALUES ('snapshot', ?)", (json.dumps(self.value),)
        )
        self.db.commit()

    @contextmanager
    def edit(self, event="stats.changed", project=None):
        with self.lock:
            previous = deepcopy(self.value)
            try:
                yield self.value
                self.value["sequence"] += 1
                self._save()
            except BaseException:
                self.db.rollback()
                self.value = previous
                raise
            if self.publish:
                self.publish(
                    {
                        "type": event,
                        "project_path": project,
                        "daemon_id": self.value["daemon_id"],
                        "sequence": self.value["sequence"],
                    }
                )

    def snapshot(self, project=None):
        with self.lock:
            return select_stats(json.loads(json.dumps(self.value)), project)

    def close(self):
        try:
            with self.edit("daemon.stopped") as value:
                value["online"] = False
                value["shared"]["model_resident"] = False
        finally:
            self.db.close()


def select_stats(value, project=None):
    if project is not None:
        if project not in value["projects"]:
            raise KeyError(f"Project is not registered: {project}")
        value["projects"] = {project: value["projects"][project]}
        value["jobs"] = {
            key: job for key, job in value["jobs"].items() if job["project_path"] == project
        }
    for stats in value["projects"].values():
        hits, misses = stats.get("cache_hits", 0), stats.get("cache_misses", 0)
        stats["cache_hit_ratio"] = hits / (hits + misses) if hits + misses else 0.0
    return value


def offline_stats(root: Path, project=None):
    db = sqlite3.connect(f"{(root / 'state.sqlite3').as_uri()}?mode=ro", uri=True)
    try:
        row = db.execute("SELECT value FROM state WHERE key='snapshot'").fetchone()
        value = json.loads(row[0])
        value["online"] = False
        return select_stats(value, project)
    finally:
        db.close()


class Generations:
    def __init__(self, root: Path, project: str):
        self.root = root / "projects" / project_id(project)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "current.json"
        self.guard = threading.RLock()
        self.cached = None
        self.cached_path = None

    def current(self):
        if not self.manifest.exists():
            return None
        name = json.loads(self.manifest.read_text())["generation"]
        if Path(name).name != name:
            raise ValueError("Invalid generation manifest")
        return self.root / name

    def publish(
        self,
        chunks,
        vectors,
        snapshot,
        stats,
        fingerprint,
        *,
        before_publish=None,
        publication_lock=None,
    ):
        import faiss
        import numpy as np

        name = "gen-" + uuid.uuid4().hex
        target = self.root / name
        target.mkdir()
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        index = faiss.IndexFlatIP(vectors.shape[1])
        if len(vectors):
            faiss.normalize_L2(vectors)
            index.add(vectors)
        faiss.write_index(index, str(target / "index.faiss"))
        db = sqlite3.connect(target / "chunks.sqlite3")
        try:
            db.execute("CREATE TABLE chunks (ordinal INTEGER PRIMARY KEY, data TEXT NOT NULL)")
            db.executemany(
                "INSERT INTO chunks VALUES (?,?)",
                ((i, json.dumps(c)) for i, c in enumerate(chunks)),
            )
            db.commit()
        finally:
            db.close()
        stats = {
            **stats,
            "generation": name,
            "index_bytes": (target / "index.faiss").stat().st_size
            + (target / "chunks.sqlite3").stat().st_size,
        }
        atomic_json(
            target / "generation.json",
            {"snapshot": snapshot, "stats": stats, "fingerprint": fingerprint},
        )
        for path in target.iterdir():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        sync_dir(target)
        with self.guard, publication_lock or nullcontext():
            if before_publish:
                before_publish(target)
            previous = self.current()
            atomic_json(self.manifest, {"generation": name})
            self.cached = None
            self.cached_path = None
            # Readers have fully loaded immutable snapshots before releasing this lock.
            # Keep the previous generation as a rollback copy, and reclaim older staging data.
            for path in self.root.glob("gen-*"):
                if path not in (target, previous):
                    try:
                        shutil.rmtree(path)
                    except OSError:
                        logging.getLogger(__name__).warning(
                            "Cannot reclaim old generation %s", path
                        )
        return stats

    def read(self):
        with self.guard:
            path = self.current()
            if path is None:
                return None
            if path != self.cached_path:
                self.cached = self._read(path)
                self.cached_path = path
            return self.cached

    def _read(self, path):
        import faiss

        index = faiss.read_index(str(path / "index.faiss"))
        db = sqlite3.connect(f"{(path / 'chunks.sqlite3').as_uri()}?mode=ro", uri=True)
        try:
            chunks = [
                json.loads(row[0]) for row in db.execute("SELECT data FROM chunks ORDER BY ordinal")
            ]
        finally:
            db.close()
        info = json.loads((path / "generation.json").read_text())
        if index.ntotal != len(chunks):
            raise ValueError("Generation has inconsistent chunk and vector counts")
        return index, chunks, info
