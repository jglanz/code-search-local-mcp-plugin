"""Project routing, durable indexing jobs and immutable search snapshots."""

import fnmatch
import hashlib
import json
import logging
import shutil
import threading
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from code_search_local import constants

from .config import canonical_project
from .models import ModelWorker, SentenceModel
from .storage import Generations, ServiceLock, State, utc_now

log = logging.getLogger(__name__)
TERMINAL = {
    constants.STATUS_SUCCEEDED,
    constants.STATUS_FAILED,
    constants.STATUS_CANCELLED,
    constants.STATUS_INTERRUPTED,
}


class Cancelled(Exception):
    pass


def chunk_file(project, relative, expected_hash):
    from .chunking.multi_language_chunker import MultiLanguageChunker

    path = Path(project) / relative
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise RuntimeError(f"File changed while indexing: {relative}; retry indexing")
    if constants.BINARY_NULL_BYTE in content:
        return []
    try:
        text = content.decode(constants.TEXT_ENCODING)
    except UnicodeDecodeError:
        return []
    chunker = MultiLanguageChunker(project)
    parser = chunker.tree_sitter_chunker.get_chunker(str(path))
    # Parse errors propagate. A broken grammar must not silently commit an empty index.
    chunks = chunker._convert_tree_chunks(parser.chunk_code(text), str(path))
    result = []
    for chunk in chunks:
        entry = asdict(chunk)
        entry[constants.KEY_CHUNK_ID] = constants.CHUNK_ID_TEMPLATE.format(
            path=relative,
            start=chunk.start_line,
            end=chunk.end_line,
            kind=chunk.chunk_type,
            name=chunk.name or "",
        )
        entry[constants.KEY_CONTENT_PREVIEW] = chunk.content[: constants.CONTENT_PREVIEW_CHARACTERS]
        result.append(entry)
    return result


def embedding_text(chunk):
    doc = (
        f'"""{chunk[constants.KEY_DOCSTRING][: constants.EMBEDDING_DOCSTRING_CHARACTERS]}"""\n'
        if chunk.get(constants.KEY_DOCSTRING)
        else ""
    )
    content = chunk[constants.KEY_CONTENT]
    budget = constants.EMBEDDING_MAX_CHARACTERS - len(doc)
    if len(content) > budget:
        head = int(budget * constants.EMBEDDING_HEAD_FRACTION)
        content = (
            content[:head]
            + constants.EMBEDDING_TRUNCATION_MARKER
            + content[-(budget - head - len(constants.EMBEDDING_TRUNCATION_MARKER)) :]
        )
    return doc + content


class Engine:
    def __init__(self, settings, *, model_factory=SentenceModel, publish=None, recover=True):
        self.settings = settings
        self.lock = ServiceLock(settings.root)
        try:
            self.state = State(settings.root, publish)
        except Exception:
            self.lock.close()
            raise
        try:
            self.model = ModelWorker(settings, self.state, model_factory)
        except Exception:
            self.state.db.close()
            self.lock.close()
            raise
        self.projects = ThreadPoolExecutor(
            settings.project_workers, thread_name_prefix=constants.PROJECT_THREAD_PREFIX
        )
        self.chunkers = ThreadPoolExecutor(
            settings.chunk_workers, thread_name_prefix=constants.CHUNK_THREAD_PREFIX
        )
        self.guard = threading.RLock()
        self.stores = {}
        self.queues = defaultdict(deque)
        self.futures = {}
        self.cancellations = {}
        self.closed = False
        self.watch_reset = threading.Event()
        self.watch_thread = None
        try:
            self._migrate_legacy()
            pending = []
            with self.state.edit(constants.EVENT_DAEMON_STARTED) as value:
                for job in value[constants.KEY_JOBS].values():
                    if job[constants.KEY_STATUS] not in TERMINAL:
                        job.update(
                            status=constants.STATUS_INTERRUPTED,
                            finished_at=utc_now(),
                            error="Service restarted; a reconciliation job will rescan the project",
                        )
                for project, stats in value[constants.KEY_PROJECTS].items():
                    generation = self._store(project).read()
                    if generation:
                        stats.update(generation[2][constants.KEY_STATS])
                    if (
                        recover
                        and Path(project).is_dir()
                        and stats.get(constants.KEY_WATCH_ENABLED, True)
                    ):
                        pending.append(project)
            for project in pending:
                self.index(
                    project,
                    wait=False,
                    file_patterns=self.state.snapshot(project)[constants.KEY_PROJECTS][project].get(
                        constants.KEY_FILE_PATTERNS
                    ),
                )
            if settings.watch:
                self.watch_thread = threading.Thread(
                    target=self._watch, name=constants.WATCHER_THREAD_NAME, daemon=True
                )
                self.watch_thread.start()
        except Exception:
            self.close()
            raise

    def _migrate_legacy(self):
        """Preserve old indexes; absent model fingerprints require a safe rebuild."""
        for info_path in (self.settings.root / constants.KEY_PROJECTS).glob(
            constants.PATH_PROJECT_INFO_JSON
        ):
            try:
                info = json.loads(info_path.read_text())
            except (ValueError, OSError):
                log.warning("Cannot read legacy project information: %s", info_path)
                continue
            root = (
                info.get(constants.KEY_ROOT_PATH)
                or info.get(constants.KEY_PROJECT_PATH)
                or info.get(constants.KEY_DIRECTORY_PATH)
            )
            if not root:
                continue
            project = canonical_project(root)
            backup = self.settings.root / constants.LEGACY_BACKUP_DIRECTORY / info_path.parent.name
            if not backup.exists():
                shutil.copytree(info_path.parent, backup)
            self._register(project)
            with self.state.edit(constants.EVENT_PROJECT_MIGRATED, project) as value:
                value[constants.KEY_PROJECTS][project][constants.KEY_LEGACY_BACKUP] = str(backup)
                if not value[constants.KEY_PROJECTS][project].get(constants.KEY_GENERATION):
                    value[constants.KEY_PROJECTS][project][constants.KEY_NEEDS_REBUILD] = True

    def _register(self, project):
        with self.guard:
            if project not in self.state.snapshot()[constants.KEY_PROJECTS]:
                with self.state.edit(constants.EVENT_PROJECT_REGISTERED, project) as value:
                    value[constants.KEY_PROJECTS][project] = {
                        constants.KEY_PROJECT_PATH: project,
                        constants.KEY_REGISTERED_AT: utc_now(),
                        constants.KEY_FILES: 0,
                        constants.KEY_CHUNKS: 0,
                        constants.KEY_CACHE_HITS: 0,
                        constants.KEY_CACHE_MISSES: 0,
                        constants.KEY_SEARCHES: 0,
                        constants.KEY_SEARCH_FAILURES: 0,
                        constants.KEY_INDEX_FAILURES: 0,
                        constants.KEY_UPDATES_DETECTED: 0,
                        constants.KEY_GENERATION: None,
                    }
                self.watch_reset.set()

    def _store(self, project):
        with self.guard:
            if project not in self.stores:
                self.stores[project] = Generations(self.settings.root, project)
            return self.stores[project]

    def index(self, project, *, wait=True, incremental=True, file_patterns=None):
        project = canonical_project(project, absolute=True)
        if not Path(project).is_dir():
            raise ValueError(f"Project root is not a directory: {project}")
        with self.guard:
            if self.closed:
                raise RuntimeError("Service is stopping")
            if sum(len(q) for q in self.queues.values()) >= self.settings.max_pending_jobs:
                raise RuntimeError("Index queue is full; retry later")
            self._register(project)
            job_id = uuid.uuid4().hex
            future = self.futures[job_id] = Future()
            self.cancellations[job_id] = threading.Event()
            with self.state.edit(constants.EVENT_JOB_QUEUED, project) as value:
                value[constants.KEY_JOBS][job_id] = {
                    constants.KEY_JOB_ID: job_id,
                    constants.KEY_PROJECT_PATH: project,
                    constants.KEY_STATUS: constants.STATUS_QUEUED,
                    constants.KEY_QUEUED_AT: utc_now(),
                    constants.KEY_FILES_PROCESSED: 0,
                    constants.KEY_INCREMENTAL: incremental,
                    constants.KEY_FILE_PATTERNS: file_patterns,
                    constants.KEY_ERROR: None,
                }
                value[constants.KEY_PROJECTS][project][constants.KEY_FILE_PATTERNS] = file_patterns
                value[constants.KEY_PROJECTS][project][constants.KEY_WATCH_ENABLED] = True
            queue = self.queues[project]
            queue.append(job_id)
            if len(queue) == 1:
                self.projects.submit(self._run, project, job_id)
        if wait:
            future.result()
        return self.job(project, job_id)

    def job(self, project, job_id):
        project = canonical_project(project, absolute=True)
        job = self.state.snapshot(project)[constants.KEY_JOBS].get(job_id)
        if job is None:
            raise KeyError(f"Unknown job for this project: {job_id}")
        return job

    def cancel(self, project, job_id):
        job = self.job(project, job_id)
        with self.guard:
            if job[constants.KEY_STATUS] not in TERMINAL:
                self.cancellations[job_id].set()
        return self.job(project, job_id)

    def _check_cancel(self, job_id):
        if self.cancellations[job_id].is_set():
            raise Cancelled("Indexing was cancelled")

    def _run(self, project, job_id):
        start = time.monotonic()
        persistence_error = None
        try:
            self._check_cancel(job_id)
            with self.state.edit(constants.EVENT_JOB_STARTED, project) as value:
                value[constants.KEY_JOBS][job_id].update(
                    status=constants.STATUS_RUNNING, started_at=utc_now()
                )
            result = self._build(project, job_id)
            with self.state.edit(constants.EVENT_JOB_COMPLETED, project) as value:
                value[constants.KEY_JOBS][job_id].update(
                    status=constants.STATUS_SUCCEEDED, result=result
                )
        except Exception as error:
            if not isinstance(error, Cancelled):
                log.exception("Index job %s failed for %s", job_id, project)
            try:
                with self.state.edit(constants.EVENT_JOB_FAILED, project) as value:
                    value[constants.KEY_JOBS][job_id].update(
                        status=constants.STATUS_CANCELLED
                        if isinstance(error, Cancelled)
                        else constants.STATUS_FAILED,
                        error=str(error),
                    )
                    if not isinstance(error, Cancelled):
                        value[constants.KEY_PROJECTS][project][constants.KEY_INDEX_FAILURES] += 1
            except Exception as error:
                persistence_error = error
                log.exception("Cannot persist failed job %s", job_id)
        finally:
            try:
                with self.state.edit(constants.EVENT_JOB_FINISHED, project) as value:
                    value[constants.KEY_JOBS][job_id].update(
                        finished_at=utc_now(), duration_seconds=time.monotonic() - start
                    )
            except Exception as error:
                persistence_error = error
                log.exception("Cannot persist completed job %s", job_id)
            with self.guard:
                queue = self.queues[project]
                queue.popleft()
                if queue:
                    self.projects.submit(self._run, project, queue[0])
                if persistence_error:
                    self.futures[job_id].set_exception(persistence_error)
                else:
                    self.futures[job_id].set_result(None)

    def _build(self, project, job_id):
        import numpy as np

        from .chunking.multi_language_chunker import MultiLanguageChunker
        from .merkle.merkle_dag import MerkleDAG

        self._check_cancel(job_id)
        job = self.job(project, job_id)
        store = self._store(project)
        previous = store.read()
        dag = MerkleDAG(project, self.settings.max_file_bytes)
        dag.build()
        all_files = dag.get_file_hashes()
        patterns = job[constants.KEY_FILE_PATTERNS]
        snapshot = {
            path: digest
            for path, digest in all_files.items()
            if Path(path).suffix.lower() in MultiLanguageChunker.SUPPORTED_EXTENSIONS
            and (not patterns or any(fnmatch.fnmatch(path, p) for p in patterns))
        }
        old_snapshot = previous[2][constants.KEY_SNAPSHOT] if previous else {}
        added = snapshot.keys() - old_snapshot.keys()
        removed = old_snapshot.keys() - snapshot.keys()
        modified = {
            p for p in snapshot.keys() & old_snapshot.keys() if snapshot[p] != old_snapshot[p]
        }
        changes = {
            constants.KEY_ADDED: len(added),
            constants.KEY_MODIFIED: len(modified),
            constants.KEY_DELETED: len(removed),
        }
        info = self.model.info(project)
        fingerprint = {
            key: info[key]
            for key in (
                constants.KEY_MODEL,
                constants.KEY_REVISION,
                constants.KEY_DIMENSION,
                constants.KEY_ENCODING,
            )
        }
        compatible = (
            previous is not None
            and previous[2][constants.KEY_FINGERPRINT] == fingerprint
            and job[constants.KEY_INCREMENTAL]
        )
        changed = added | modified if compatible else snapshot.keys()
        unchanged = snapshot.keys() - changed
        chunks, vectors = [], []
        if compatible:
            for i, chunk in enumerate(previous[1]):
                if chunk[constants.KEY_RELATIVE_PATH] in unchanged:
                    chunks.append(chunk)
                    vectors.append(previous[0].reconstruct(i))
        reused_chunks = len(chunks)
        # Only a bounded number of file tasks exist at a time, shared by all projects.
        paths = iter(sorted(changed))
        pending = deque()
        while True:
            self._check_cancel(job_id)
            while len(pending) < self.settings.chunk_workers:
                path = next(paths, None)
                if path is None:
                    break
                pending.append(self.chunkers.submit(chunk_file, project, path, snapshot[path]))
            if not pending:
                break
            new_chunks = pending.popleft().result()
            if new_chunks:
                encoded = self.model.encode(project, [embedding_text(c) for c in new_chunks])
                vectors.extend(encoded)
                chunks.extend(new_chunks)
            with self.state.edit(constants.EVENT_JOB_PROGRESS, project) as value:
                value[constants.KEY_JOBS][job_id][constants.KEY_FILES_PROCESSED] += 1
                value[constants.KEY_JOBS][job_id][constants.KEY_FILES_TOTAL] = len(changed)
        self._check_cancel(job_id)
        indexed_files = len({c[constants.KEY_RELATIVE_PATH] for c in chunks})
        stats = {
            constants.KEY_FILES: indexed_files,
            constants.KEY_FILES_SCANNED: len(all_files),
            constants.KEY_FILES_SUPPORTED: len(snapshot),
            constants.KEY_FILES_SKIPPED: len(all_files) - indexed_files,
            constants.KEY_CHUNKS: len(chunks),
            constants.KEY_SOURCE_BYTES: sum(dag.nodes[p].size for p in snapshot),
            constants.KEY_INDEXED_AT: utc_now(),
            constants.KEY_CHANGES: changes,
            constants.KEY_REUSED_CHUNKS: reused_chunks,
            constants.KEY_MODEL: self.model.info(project),
            constants.KEY_MERKLE_ROOT: dag.get_root_hash(),
            constants.KEY_NEEDS_REBUILD: False,
        }
        array = np.asarray(vectors, dtype=np.float32).reshape((-1, info[constants.KEY_DIMENSION]))
        # Serialize cancellation with publication. No cancelled job can publish afterward.
        stats = store.publish(
            chunks,
            array,
            snapshot,
            stats,
            fingerprint,
            before_publish=lambda _: self._check_cancel(job_id),
            publication_lock=self.guard,
        )
        with self.state.edit(constants.EVENT_INDEX_COMMITTED, project) as value:
            value[constants.KEY_PROJECTS][project].update(stats)
            value[constants.KEY_PROJECTS][project][constants.KEY_UPDATES_DETECTED] += sum(
                changes.values()
            )
        return stats

    def search(self, project, query, *, k=constants.DEFAULT_SEARCH_RESULTS, filters=None):
        import faiss
        import numpy as np

        project = canonical_project(project, absolute=True)
        self.state.snapshot(project)
        if not query.strip() or not 1 <= k <= constants.MAX_SEARCH_RESULTS:
            raise ValueError("query must be nonempty and k must be between 1 and 100")
        start = time.monotonic()
        failed = False
        try:
            generation = self._store(project).read()
            if generation is None:
                raise ValueError("Project has no committed index yet; wait for its indexing job")
            index, chunks, info = generation
            if not chunks:
                return {
                    constants.KEY_PROJECT_PATH: project,
                    constants.KEY_GENERATION: info[constants.KEY_STATS][constants.KEY_GENERATION],
                    constants.KEY_RESULTS: [],
                }
            model_info = self.model.info(project)
            if info[constants.KEY_FINGERPRINT] != {
                key: model_info[key] for key in info[constants.KEY_FINGERPRINT]
            }:
                raise ValueError("Index model changed; reindex this project before searching")
            vector = np.ascontiguousarray(
                self.model.encode(project, [query], constants.KEY_QUERY), dtype=np.float32
            )
            faiss.normalize_L2(vector)
            scores, ordinals = index.search(
                vector, index.ntotal if filters else min(k, index.ntotal)
            )
            results = []
            for score, ordinal in zip(scores[0], ordinals[0]):
                if ordinal < 0:
                    continue
                chunk = chunks[ordinal]
                if filters and any(
                    not fnmatch.fnmatch(str(chunk.get(key, "")), str(pattern))
                    for key, pattern in filters.items()
                ):
                    continue
                results.append({**chunk, constants.KEY_SCORE: float(score)})
                if len(results) == k:
                    break
            return {
                constants.KEY_PROJECT_PATH: project,
                constants.KEY_GENERATION: info[constants.KEY_STATS][constants.KEY_GENERATION],
                constants.KEY_RESULTS: results,
            }
        except Exception:
            failed = True
            raise
        finally:
            elapsed = time.monotonic() - start
            with self.state.edit(constants.EVENT_SEARCH_COMPLETED, project) as value:
                stats = value[constants.KEY_PROJECTS][project]
                stats[constants.KEY_SEARCHES] += 1
                stats[constants.KEY_SEARCH_FAILURES] += int(failed)
                stats[constants.KEY_SEARCH_SECONDS] = (
                    stats.get(constants.KEY_SEARCH_SECONDS, 0) + elapsed
                )
                stats[constants.KEY_LAST_SEARCH_SECONDS] = elapsed

    def similar(self, project, chunk_id, k=constants.DEFAULT_SIMILAR_RESULTS):
        import numpy as np

        project = canonical_project(project, absolute=True)
        self.state.snapshot(project)
        if not 1 <= k <= constants.MAX_SEARCH_RESULTS:
            raise ValueError("k must be between 1 and 100")
        generation = self._store(project).read()
        if generation is None:
            raise ValueError("Project has no committed index")
        index, chunks, info = generation
        ordinal = next(
            (i for i, chunk in enumerate(chunks) if chunk[constants.KEY_CHUNK_ID] == chunk_id), None
        )
        if ordinal is None:
            raise KeyError(f"Unknown chunk in this project: {chunk_id}")
        scores, matches = index.search(
            np.asarray([index.reconstruct(ordinal)]), min(k + 1, len(chunks))
        )
        return {
            constants.KEY_PROJECT_PATH: project,
            constants.KEY_GENERATION: info[constants.KEY_STATS][constants.KEY_GENERATION],
            constants.KEY_RESULTS: [
                {**chunks[i], constants.KEY_SCORE: float(score)}
                for score, i in zip(scores[0], matches[0])
                if i != ordinal
            ][:k],
        }

    def clear(self, project):
        import numpy as np

        project = canonical_project(project, absolute=True)
        self.state.snapshot(project)
        with self.guard:
            if self.queues[project]:
                raise RuntimeError(
                    "Project is indexing; cancel or wait for its active jobs before clearing"
                )
            store = self._store(project)
            previous = store.read()
            stats = {
                constants.KEY_FILES: 0,
                constants.KEY_FILES_SCANNED: 0,
                constants.KEY_FILES_SUPPORTED: 0,
                constants.KEY_FILES_SKIPPED: 0,
                constants.KEY_CHUNKS: 0,
                constants.KEY_SOURCE_BYTES: 0,
                constants.KEY_CLEARED_AT: utc_now(),
                constants.KEY_WATCH_ENABLED: False,
            }
            if previous:
                stats = store.publish(
                    [],
                    np.empty((0, previous[0].d), dtype=np.float32),
                    {},
                    {**previous[2][constants.KEY_STATS], **stats},
                    previous[2][constants.KEY_FINGERPRINT],
                )
            with self.state.edit(constants.EVENT_INDEX_CLEARED, project) as value:
                value[constants.KEY_PROJECTS][project].update(stats)
            self.watch_reset.set()
            return self.state.snapshot(project)

    def _watch(self):
        from watchfiles import watch

        while not self.closed:
            self.watch_reset.clear()
            roots = [
                p
                for p, stats in self.state.snapshot()[constants.KEY_PROJECTS].items()
                if Path(p).is_dir() and stats.get(constants.KEY_WATCH_ENABLED, True)
            ]
            if not roots:
                self.watch_reset.wait(constants.WATCH_IDLE_WAIT_SECONDS)
                continue
            try:
                reconcile = True
                for changes in watch(
                    *roots,
                    stop_event=self.watch_reset,
                    debounce=constants.WATCH_DEBOUNCE_MILLISECONDS,
                    step=constants.WATCH_STEP_MILLISECONDS,
                    yield_on_timeout=True,
                    rust_timeout=constants.WATCH_TIMEOUT_MILLISECONDS,
                ):
                    touched = {
                        root
                        for _, path in changes
                        for root in roots
                        if Path(path).is_relative_to(root)
                    }
                    if reconcile:
                        # The listener is established before this rescan, closing the registration gap.
                        touched.update(roots)
                        reconcile = False
                    for root in touched:
                        with self.guard:
                            # Keep one pending reconciliation behind the currently running job.
                            if (
                                len(self.queues[root]) < constants.WATCH_RECONCILIATION_QUEUE_LIMIT
                                and not self.closed
                            ):
                                patterns = self.state.snapshot(root)[constants.KEY_PROJECTS][
                                    root
                                ].get(constants.KEY_FILE_PATTERNS)
                                self.index(root, wait=False, file_patterns=patterns)
            except (OSError, RuntimeError):
                log.exception("Watcher failed; reconciling registered roots")
                self.watch_reset.wait(constants.WATCH_IDLE_WAIT_SECONDS)
                for root in roots:
                    if not self.closed and Path(root).is_dir():
                        self.index(
                            root,
                            wait=False,
                            file_patterns=self.state.snapshot(root)[constants.KEY_PROJECTS][
                                root
                            ].get(constants.KEY_FILE_PATTERNS),
                        )

    def close(self):
        with self.guard:
            self.closed = True
            self.watch_reset.set()
            for cancel in self.cancellations.values():
                cancel.set()
        if self.watch_thread:
            self.watch_thread.join()
        # Queued same-project tasks submit their successor; wait before shutting down the pool.
        for future in list(self.futures.values()):
            try:
                future.result()
            except Exception:
                log.exception("Indexing failed during shutdown")
        self.projects.shutdown()
        self.chunkers.shutdown()
        try:
            self.model.close()
        finally:
            try:
                self.state.close()
            finally:
                self.lock.close()
