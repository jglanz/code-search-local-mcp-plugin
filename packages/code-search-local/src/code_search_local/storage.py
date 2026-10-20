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
from collections import Counter
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from code_search_local import constants

# Search analytics a project starts with; older persisted projects read as these values.
SEARCH_ANALYTICS_DEFAULTS = {
    constants.KEY_SEARCH_RELEVANCE_HITS: 0,
    constants.KEY_SEARCH_RELEVANCE_MISSES: 0,
    constants.KEY_SEARCH_RESULT_HITS: 0,
    constants.KEY_SEARCH_RESULT_MISSES: 0,
    constants.KEY_SEARCH_ZERO_RESULTS: 0,
    constants.KEY_QUERY_CACHE_HITS: 0,
    constants.KEY_QUERY_CACHE_MISSES: 0,
    constants.KEY_LAST_SEARCH_AT: None,
    constants.KEY_LAST_SEARCH_TOP_SCORE: None,
}
# (ratio, hits, misses): each ratio is hits / (hits + misses), or 0.0 before any event.
HIT_RATIOS = (
    (constants.KEY_CACHE_HIT_RATIO, constants.KEY_CACHE_HITS, constants.KEY_CACHE_MISSES),
    (
        constants.KEY_SEARCH_RELEVANCE_HIT_RATIO,
        constants.KEY_SEARCH_RELEVANCE_HITS,
        constants.KEY_SEARCH_RELEVANCE_MISSES,
    ),
    (
        constants.KEY_SEARCH_RESULT_HIT_RATIO,
        constants.KEY_SEARCH_RESULT_HITS,
        constants.KEY_SEARCH_RESULT_MISSES,
    ),
    (
        constants.KEY_QUERY_CACHE_HIT_RATIO,
        constants.KEY_QUERY_CACHE_HITS,
        constants.KEY_QUERY_CACHE_MISSES,
    ),
)
TOTAL_COUNTERS = (
    constants.KEY_FILES,
    constants.KEY_CHUNKS,
    constants.KEY_SEARCHES,
    constants.KEY_SEARCH_FAILURES,
    constants.KEY_SEARCH_RELEVANCE_HITS,
    constants.KEY_SEARCH_RELEVANCE_MISSES,
    constants.KEY_SEARCH_RESULT_HITS,
    constants.KEY_SEARCH_RESULT_MISSES,
    constants.KEY_SEARCH_ZERO_RESULTS,
    constants.KEY_QUERY_CACHE_HITS,
    constants.KEY_QUERY_CACHE_MISSES,
    constants.KEY_CACHE_HITS,
    constants.KEY_CACHE_MISSES,
)
# Column order of SQL_READ_SEARCH_PATHS and of SQL_READ_TOP_SEARCH_PATHS after its project.
SEARCH_PATH_COLUMNS = (
    constants.KEY_PATH,
    constants.KEY_APPEARANCES,
    constants.KEY_HITS,
    constants.KEY_TOP_RANKED,
    constants.KEY_CHUNK_APPEARANCES,
    constants.KEY_BEST_SCORE,
    constants.KEY_LAST_SEEN_AT,
)
# Analytics of a committed path that no search has returned yet.
UNSEEN_SEARCH_PATH = {
    constants.KEY_APPEARANCES: 0,
    constants.KEY_HITS: 0,
    constants.KEY_MISSES: 0,
    constants.KEY_HIT_RATIO: 0.0,
    constants.KEY_TOP_RANKED: 0,
    constants.KEY_CHUNK_APPEARANCES: 0,
    constants.KEY_BEST_SCORE: None,
    constants.KEY_LAST_SEEN_AT: None,
}


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
    """Transactional counters, registry, durable jobs and per-path search history.

    Safe across threads.
    """

    def __init__(self, root: Path, publish=None):
        self.path = root / constants.PATH_STATE_SQLITE3
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute(constants.SQL_ENABLE_WAL)
        self.db.execute(constants.SQL_FULL_SYNC)
        self.db.execute(constants.SQL_CREATE_STATE)
        self.db.execute(constants.SQL_CREATE_SEARCH_PATHS)
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

    def record_search_paths(self, project, results, threshold, seen_at):
        """Fold one search's ranked results into per-path rows.

        Call inside ``edit``: the rows then commit, or roll back, in the same SQLite
        transaction as the search counters.
        """
        paths = {}
        for rank, result in enumerate(results):
            score = result[constants.KEY_SCORE]
            path = result[constants.KEY_RELATIVE_PATH]
            hit, top_ranked, chunks, best = paths.get(path, (False, False, 0, score))
            paths[path] = (
                hit or score >= threshold,
                top_ranked or rank == 0,
                chunks + 1,
                max(best, score),
            )
        with self.lock:
            self.db.executemany(
                constants.SQL_UPSERT_SEARCH_PATH,
                (
                    (project, path, int(hit), int(top_ranked), chunks, best, seen_at)
                    for path, (hit, top_ranked, chunks, best) in paths.items()
                ),
            )

    def search_paths(self, project):
        """Every recorded path of one project, ordered by path, including deleted files."""
        with self.lock:
            return [
                search_path_row(row)
                for row in self.db.execute(constants.SQL_READ_SEARCH_PATHS, (project,))
            ]

    def snapshot(self, project=None):
        with self.lock:
            return select_stats(
                json.loads(json.dumps(self.value)), project, read_top_search_paths(self.db, project)
            )

    def close(self):
        try:
            with self.edit(constants.EVENT_DAEMON_STOPPED) as value:
                value[constants.KEY_ONLINE] = False
                value[constants.KEY_SHARED][constants.KEY_MODEL_RESIDENT] = False
        finally:
            self.db.close()


def increment(counters, key, amount=1):
    """Add to a counter that state persisted by an older version may not contain yet."""
    counters[key] = counters.get(key, 0) + amount


def hit_ratio(hits, misses):
    return hits / (hits + misses) if hits + misses else 0.0


def add_hit_ratios(counters):
    for name, hits, misses in HIT_RATIOS:
        counters[name] = hit_ratio(counters.get(hits, 0), counters.get(misses, 0))


def search_path_row(row):
    """Name one stored path row's columns and derive its misses and hit ratio."""
    value = dict(zip(SEARCH_PATH_COLUMNS, row))
    value[constants.KEY_MISSES] = value[constants.KEY_APPEARANCES] - value[constants.KEY_HITS]
    value[constants.KEY_HIT_RATIO] = hit_ratio(
        value[constants.KEY_HITS], value[constants.KEY_MISSES]
    )
    return value


def read_top_search_paths(db, project=None):
    """Map project roots to their most often returned paths; ``None`` reads every project."""
    paths = {}
    for root, *row in db.execute(
        constants.SQL_READ_TOP_SEARCH_PATHS, (project, project, constants.TOP_PATHS_LIMIT)
    ):
        paths.setdefault(root, []).append(search_path_row(row))
    return paths


def select_stats(value, project=None, paths=None):
    """Derive ratios, totals and top paths from a detached snapshot without any I/O.

    ``paths`` maps project roots to path rows ordered by appearances. Totals always cover
    every registered project, including projects excluded by the ``project`` filter.
    """
    projects = value[constants.KEY_PROJECTS]
    totals = {constants.KEY_PROJECTS: len(projects)}
    for key in TOTAL_COUNTERS:
        totals[key] = sum(stats.get(key, 0) for stats in projects.values())
    add_hit_ratios(totals)
    value[constants.KEY_TOTALS] = totals
    if project is not None:
        if project not in projects:
            raise KeyError(f"Project is not registered: {project}")
        value[constants.KEY_PROJECTS] = {project: projects[project]}
        value[constants.KEY_JOBS] = {
            key: job
            for key, job in value[constants.KEY_JOBS].items()
            if job[constants.KEY_PROJECT_PATH] == project
        }
    paths = paths or {}
    for root, stats in value[constants.KEY_PROJECTS].items():
        for key, default in SEARCH_ANALYTICS_DEFAULTS.items():
            stats.setdefault(key, default)
        stats[constants.KEY_PROJECT_ID] = project_id(root)
        add_hit_ratios(stats)
        stats[constants.KEY_TOP_PATHS] = paths.get(root, [])[: constants.TOP_PATHS_LIMIT]
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
        # Databases written before per-path statistics existed have no path table.
        paths = (
            read_top_search_paths(db, project)
            if db.execute(constants.SQL_SEARCH_PATHS_TABLE_EXISTS).fetchone()
            else {}
        )
        return select_stats(value, project, paths)
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
        self.cached_counts = None

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
            self.cached_counts = None
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
                self.cached_counts = None
            return self.cached

    def read_with_chunk_counts(self):
        """Return the committed generation and its chunks per relative path, or ``None``.

        Counts are derived once per generation and dropped together with its cached copy.
        """
        with self.guard:
            generation = self.read()
            if generation is None:
                return None
            if self.cached_counts is None:
                self.cached_counts = Counter(
                    chunk[constants.KEY_RELATIVE_PATH] for chunk in generation[1]
                )
            return generation, self.cached_counts

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
