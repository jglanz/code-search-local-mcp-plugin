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

from code_search_local import constants


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sync_dir(path: Path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def atomic_writer(path, *, mode, prefix, directory_mode=None):
    """Flush a private temporary file and publish it only after a successful write."""
    options = {} if directory_mode is None else {constants.KEY_MODE: directory_mode}
    path.parent.mkdir(parents=True, exist_ok=True, **options)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=prefix)
    try:
        with os.fdopen(fd, constants.FILE_MODE_WRITE) as stream:
            os.fchmod(stream.fileno(), mode)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_dir(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def atomic_text(path, content):
    with atomic_writer(
        path, mode=constants.PRIVATE_FILE_MODE, prefix=constants.PATH_CODE_SEARCH_LOCAL
    ) as stream:
        stream.write(content)


def atomic_json(path: Path, value, *, mode: int = constants.PRIVATE_FILE_MODE):
    with atomic_writer(
        path,
        mode=mode,
        prefix=constants.ATOMIC_TEMP_PREFIX_TEMPLATE.format(name=path.name),
        directory_mode=constants.PRIVATE_DIRECTORY_MODE,
    ) as stream:
        json.dump(value, stream, indent=constants.JSON_INDENT, sort_keys=True, allow_nan=False)
        stream.write("\n")


class ServiceLock:
    def __init__(self, root: Path, name=constants.PATH_SERVICE_LOCK):
        root.mkdir(parents=True, exist_ok=True, mode=constants.PRIVATE_DIRECTORY_MODE)
        self.stream = (root / name).open(constants.FILE_MODE_APPEND_READ)
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
        self.path = root / constants.PATH_STATE_SQLITE3
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute(constants.SQL_ENABLE_WAL)
        self.db.execute(constants.SQL_FULL_SYNC)
        self.db.execute(constants.SQL_CREATE_STATE)
        rows = dict(self.db.execute(constants.SQL_READ_STATE))
        self.value = (
            json.loads(rows[constants.KEY_SNAPSHOT])
            if constants.KEY_SNAPSHOT in rows
            else {
                constants.KEY_SCHEMA_VERSION: constants.STATE_SCHEMA_VERSION,
                constants.KEY_PROJECTS: {},
                constants.KEY_JOBS: {},
                constants.KEY_SHARED: {},
            }
        )
        self.value.update(daemon_id=uuid.uuid4().hex, sequence=0, started_at=utc_now(), online=True)
        self.value[constants.KEY_SHARED][constants.KEY_MODEL_RESIDENT] = False
        self.publish = publish
        self._save()

    def _save(self):
        self.db.execute(constants.SQL_SAVE_STATE, (json.dumps(self.value),))
        self.db.commit()

    @contextmanager
    def edit(self, event=constants.EVENT_STATS_CHANGED, project=None):
        with self.lock:
            previous = deepcopy(self.value)
            try:
                yield self.value
                self.value[constants.KEY_SEQUENCE] += 1
                self._save()
            except BaseException:
                self.db.rollback()
                self.value = previous
                raise
            if self.publish:
                self.publish(
                    {
                        constants.KEY_TYPE: event,
                        constants.KEY_PROJECT_PATH: project,
                        constants.KEY_DAEMON_ID: self.value[constants.KEY_DAEMON_ID],
                        constants.KEY_SEQUENCE: self.value[constants.KEY_SEQUENCE],
                    }
                )

    def snapshot(self, project=None):
        with self.lock:
            return select_stats(json.loads(json.dumps(self.value)), project)

    def close(self):
        try:
            with self.edit(constants.EVENT_DAEMON_STOPPED) as value:
                value[constants.KEY_ONLINE] = False
                value[constants.KEY_SHARED][constants.KEY_MODEL_RESIDENT] = False
        finally:
            self.db.close()


def select_stats(value, project=None):
    if project is not None:
        if project not in value[constants.KEY_PROJECTS]:
            raise KeyError(f"Project is not registered: {project}")
        value[constants.KEY_PROJECTS] = {project: value[constants.KEY_PROJECTS][project]}
        value[constants.KEY_JOBS] = {
            key: job
            for key, job in value[constants.KEY_JOBS].items()
            if job[constants.KEY_PROJECT_PATH] == project
        }
    for stats in value[constants.KEY_PROJECTS].values():
        hits, misses = (
            stats.get(constants.KEY_CACHE_HITS, 0),
            stats.get(constants.KEY_CACHE_MISSES, 0),
        )
        stats[constants.KEY_CACHE_HIT_RATIO] = hits / (hits + misses) if hits + misses else 0.0
    return value


def offline_stats(root: Path, project=None):
    db = sqlite3.connect(
        constants.DATABASE_READONLY_URI_TEMPLATE.format(
            uri=(root / constants.PATH_STATE_SQLITE3).as_uri()
        ),
        uri=True,
    )
    try:
        row = db.execute(constants.SQL_READ_SNAPSHOT).fetchone()
        value = json.loads(row[0])
        value[constants.KEY_ONLINE] = False
        return select_stats(value, project)
    finally:
        db.close()


class Generations:
    def __init__(self, root: Path, project: str):
        self.root = root / constants.KEY_PROJECTS / project_id(project)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / constants.PATH_CURRENT_JSON
        self.guard = threading.RLock()
        self.cached = None
        self.cached_path = None

    def current(self):
        if not self.manifest.exists():
            return None
        name = json.loads(self.manifest.read_text())[constants.KEY_GENERATION]
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

        name = constants.GENERATION_PREFIX + uuid.uuid4().hex
        target = self.root / name
        target.mkdir()
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        index = faiss.IndexFlatIP(vectors.shape[1])
        if len(vectors):
            faiss.normalize_L2(vectors)
            index.add(vectors)
        faiss.write_index(index, str(target / constants.PATH_INDEX_FAISS))
        db = sqlite3.connect(target / constants.PATH_CHUNKS_SQLITE3)
        try:
            db.execute(constants.SQL_CREATE_CHUNKS)
            db.executemany(
                constants.SQL_INSERT_CHUNKS,
                ((i, json.dumps(c)) for i, c in enumerate(chunks)),
            )
            db.commit()
        finally:
            db.close()
        stats = {
            **stats,
            constants.KEY_GENERATION: name,
            constants.KEY_INDEX_BYTES: (target / constants.PATH_INDEX_FAISS).stat().st_size
            + (target / constants.PATH_CHUNKS_SQLITE3).stat().st_size,
        }
        atomic_json(
            target / constants.PATH_GENERATION_JSON,
            {
                constants.KEY_SNAPSHOT: snapshot,
                constants.KEY_STATS: stats,
                constants.KEY_FINGERPRINT: fingerprint,
            },
        )
        for path in target.iterdir():
            with path.open(constants.FILE_MODE_READ_BINARY) as stream:
                os.fsync(stream.fileno())
        sync_dir(target)
        with self.guard, publication_lock or nullcontext():
            if before_publish:
                before_publish(target)
            previous = self.current()
            atomic_json(self.manifest, {constants.KEY_GENERATION: name})
            self.cached = None
            self.cached_path = None
            # Readers have fully loaded immutable snapshots before releasing this lock.
            # Keep the previous generation as a rollback copy, and reclaim older staging data.
            for path in self.root.glob(constants.GENERATION_GLOB):
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

        index = faiss.read_index(str(path / constants.PATH_INDEX_FAISS))
        db = sqlite3.connect(
            constants.DATABASE_READONLY_URI_TEMPLATE.format(
                uri=(path / constants.PATH_CHUNKS_SQLITE3).as_uri()
            ),
            uri=True,
        )
        try:
            chunks = [json.loads(row[0]) for row in db.execute(constants.SQL_READ_CHUNKS)]
        finally:
            db.close()
        info = json.loads((path / constants.PATH_GENERATION_JSON).read_text())
        if index.ntotal != len(chunks):
            raise ValueError("Generation has inconsistent chunk and vector counts")
        return index, chunks, info
