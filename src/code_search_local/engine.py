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

from .config import canonical_project
from .models import ModelWorker, SentenceModel
from .storage import Generations, ServiceLock, State, utc_now

log = logging.getLogger(__name__)
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


class Cancelled(Exception):
    pass


def chunk_file(project, relative, expected_hash):
    from .chunking.multi_language_chunker import MultiLanguageChunker

    path = Path(project) / relative
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise RuntimeError(f"File changed while indexing: {relative}; retry indexing")
    if b"\0" in content:
        return []
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return []
    chunker = MultiLanguageChunker(project)
    parser = chunker.tree_sitter_chunker.get_chunker(str(path))
    # Parse errors propagate. A broken grammar must not silently commit an empty index.
    chunks = chunker._convert_tree_chunks(parser.chunk_code(text), str(path))
    result = []
    for chunk in chunks:
        entry = asdict(chunk)
        entry["chunk_id"] = (
            f"{relative}:{chunk.start_line}-{chunk.end_line}:{chunk.chunk_type}:{chunk.name or ''}"
        )
        entry["content_preview"] = chunk.content[:400]
        result.append(entry)
    return result


def embedding_text(chunk):
    doc = f'"""{chunk["docstring"][:300]}"""\n' if chunk.get("docstring") else ""
    content = chunk["content"]
    budget = 6000 - len(doc)
    if len(content) > budget:
        head = int(budget * 0.7)
        content = content[:head] + "\n...\n" + content[-(budget - head - 5) :]
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
            settings.project_workers, thread_name_prefix="index-project"
        )
        self.chunkers = ThreadPoolExecutor(settings.chunk_workers, thread_name_prefix="chunk-file")
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
            with self.state.edit("daemon.started") as value:
                for job in value["jobs"].values():
                    if job["status"] not in TERMINAL:
                        job.update(
                            status="interrupted",
                            finished_at=utc_now(),
                            error="Service restarted; a reconciliation job will rescan the project",
                        )
                for project, stats in value["projects"].items():
                    generation = self._store(project).read()
                    if generation:
                        stats.update(generation[2]["stats"])
                    if recover and Path(project).is_dir() and stats.get("watch_enabled", True):
                        pending.append(project)
            for project in pending:
                self.index(
                    project,
                    wait=False,
                    file_patterns=self.state.snapshot(project)["projects"][project].get(
                        "file_patterns"
                    ),
                )
            if settings.watch:
                self.watch_thread = threading.Thread(
                    target=self._watch, name="project-watcher", daemon=True
                )
                self.watch_thread.start()
        except Exception:
            self.close()
            raise

    def _migrate_legacy(self):
        """Preserve old indexes; absent model fingerprints require a safe rebuild."""
        for info_path in (self.settings.root / "projects").glob("*/project_info.json"):
            try:
                info = json.loads(info_path.read_text())
            except (ValueError, OSError):
                log.warning("Cannot read legacy project information: %s", info_path)
                continue
            root = info.get("root_path") or info.get("project_path") or info.get("directory_path")
            if not root:
                continue
            project = canonical_project(root)
            backup = self.settings.root / "legacy-backups" / info_path.parent.name
            if not backup.exists():
                shutil.copytree(info_path.parent, backup)
            self._register(project)
            with self.state.edit("project.migrated", project) as value:
                value["projects"][project]["legacy_backup"] = str(backup)
                if not value["projects"][project].get("generation"):
                    value["projects"][project]["needs_rebuild"] = True

    def _register(self, project):
        with self.guard:
            if project not in self.state.snapshot()["projects"]:
                with self.state.edit("project.registered", project) as value:
                    value["projects"][project] = {
                        "project_path": project,
                        "registered_at": utc_now(),
                        "files": 0,
                        "chunks": 0,
                        "cache_hits": 0,
                        "cache_misses": 0,
                        "searches": 0,
                        "search_failures": 0,
                        "index_failures": 0,
                        "updates_detected": 0,
                        "generation": None,
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
            with self.state.edit("job.queued", project) as value:
                value["jobs"][job_id] = {
                    "job_id": job_id,
                    "project_path": project,
                    "status": "queued",
                    "queued_at": utc_now(),
                    "files_processed": 0,
                    "incremental": incremental,
                    "file_patterns": file_patterns,
                    "error": None,
                }
                value["projects"][project]["file_patterns"] = file_patterns
                value["projects"][project]["watch_enabled"] = True
            queue = self.queues[project]
            queue.append(job_id)
            if len(queue) == 1:
                self.projects.submit(self._run, project, job_id)
        if wait:
            future.result()
        return self.job(project, job_id)

    def job(self, project, job_id):
        project = canonical_project(project, absolute=True)
        job = self.state.snapshot(project)["jobs"].get(job_id)
        if job is None:
            raise KeyError(f"Unknown job for this project: {job_id}")
        return job

    def cancel(self, project, job_id):
        job = self.job(project, job_id)
        with self.guard:
            if job["status"] not in TERMINAL:
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
            with self.state.edit("job.started", project) as value:
                value["jobs"][job_id].update(status="running", started_at=utc_now())
            result = self._build(project, job_id)
            with self.state.edit("job.completed", project) as value:
                value["jobs"][job_id].update(status="succeeded", result=result)
        except Exception as error:
            if not isinstance(error, Cancelled):
                log.exception("Index job %s failed for %s", job_id, project)
            try:
                with self.state.edit("job.failed", project) as value:
                    value["jobs"][job_id].update(
                        status="cancelled" if isinstance(error, Cancelled) else "failed",
                        error=str(error),
                    )
                    if not isinstance(error, Cancelled):
                        value["projects"][project]["index_failures"] += 1
            except Exception as error:
                persistence_error = error
                log.exception("Cannot persist failed job %s", job_id)
        finally:
            try:
                with self.state.edit("job.finished", project) as value:
                    value["jobs"][job_id].update(
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
        dag.ignore_patterns.add(".omc")
        dag.build()
        all_files = dag.get_file_hashes()
        patterns = job["file_patterns"]
        snapshot = {
            path: digest
            for path, digest in all_files.items()
            if Path(path).suffix.lower() in MultiLanguageChunker.SUPPORTED_EXTENSIONS
            and (not patterns or any(fnmatch.fnmatch(path, p) for p in patterns))
        }
        old_snapshot = previous[2]["snapshot"] if previous else {}
        added = snapshot.keys() - old_snapshot.keys()
        removed = old_snapshot.keys() - snapshot.keys()
        modified = {
            p for p in snapshot.keys() & old_snapshot.keys() if snapshot[p] != old_snapshot[p]
        }
        changes = {"added": len(added), "modified": len(modified), "deleted": len(removed)}
        info = self.model.info(project)
        fingerprint = {key: info[key] for key in ("model", "revision", "dimension", "encoding")}
        compatible = (
            previous is not None
            and previous[2]["fingerprint"] == fingerprint
            and job["incremental"]
        )
        changed = added | modified if compatible else snapshot.keys()
        unchanged = snapshot.keys() - changed
        chunks, vectors = [], []
        if compatible:
            for i, chunk in enumerate(previous[1]):
                if chunk["relative_path"] in unchanged:
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
            with self.state.edit("job.progress", project) as value:
                value["jobs"][job_id]["files_processed"] += 1
                value["jobs"][job_id]["files_total"] = len(changed)
        self._check_cancel(job_id)
        indexed_files = len({c["relative_path"] for c in chunks})
        stats = {
            "files": indexed_files,
            "files_scanned": len(all_files),
            "files_supported": len(snapshot),
            "files_skipped": len(all_files) - indexed_files,
            "chunks": len(chunks),
            "source_bytes": sum(dag.nodes[p].size for p in snapshot),
            "indexed_at": utc_now(),
            "changes": changes,
            "reused_chunks": reused_chunks,
            "model": self.model.info(project),
            "merkle_root": dag.get_root_hash(),
            "needs_rebuild": False,
        }
        array = np.asarray(vectors, dtype=np.float32).reshape((-1, info["dimension"]))
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
        with self.state.edit("index.committed", project) as value:
            value["projects"][project].update(stats)
            value["projects"][project]["updates_detected"] += sum(changes.values())
        return stats

    def search(self, project, query, *, k=10, filters=None):
        import faiss
        import numpy as np

        project = canonical_project(project, absolute=True)
        self.state.snapshot(project)
        if not query.strip() or not 1 <= k <= 100:
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
                    "project_path": project,
                    "generation": info["stats"]["generation"],
                    "results": [],
                }
            model_info = self.model.info(project)
            if info["fingerprint"] != {key: model_info[key] for key in info["fingerprint"]}:
                raise ValueError("Index model changed; reindex this project before searching")
            vector = np.ascontiguousarray(
                self.model.encode(project, [query], "query"), dtype=np.float32
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
                results.append({**chunk, "score": float(score)})
                if len(results) == k:
                    break
            return {
                "project_path": project,
                "generation": info["stats"]["generation"],
                "results": results,
            }
        except Exception:
            failed = True
            raise
        finally:
            elapsed = time.monotonic() - start
            with self.state.edit("search.completed", project) as value:
                stats = value["projects"][project]
                stats["searches"] += 1
                stats["search_failures"] += int(failed)
                stats["search_seconds"] = stats.get("search_seconds", 0) + elapsed
                stats["last_search_seconds"] = elapsed

    def similar(self, project, chunk_id, k=5):
        import numpy as np

        project = canonical_project(project, absolute=True)
        self.state.snapshot(project)
        if not 1 <= k <= 100:
            raise ValueError("k must be between 1 and 100")
        generation = self._store(project).read()
        if generation is None:
            raise ValueError("Project has no committed index")
        index, chunks, info = generation
        ordinal = next((i for i, chunk in enumerate(chunks) if chunk["chunk_id"] == chunk_id), None)
        if ordinal is None:
            raise KeyError(f"Unknown chunk in this project: {chunk_id}")
        scores, matches = index.search(
            np.asarray([index.reconstruct(ordinal)]), min(k + 1, len(chunks))
        )
        return {
            "project_path": project,
            "generation": info["stats"]["generation"],
            "results": [
                {**chunks[i], "score": float(score)}
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
                "files": 0,
                "files_scanned": 0,
                "files_supported": 0,
                "files_skipped": 0,
                "chunks": 0,
                "source_bytes": 0,
                "cleared_at": utc_now(),
                "watch_enabled": False,
            }
            if previous:
                stats = store.publish(
                    [],
                    np.empty((0, previous[0].d), dtype=np.float32),
                    {},
                    {**previous[2]["stats"], **stats},
                    previous[2]["fingerprint"],
                )
            with self.state.edit("index.cleared", project) as value:
                value["projects"][project].update(stats)
            self.watch_reset.set()
            return self.state.snapshot(project)

    def _watch(self):
        from watchfiles import watch

        while not self.closed:
            self.watch_reset.clear()
            roots = [
                p
                for p, stats in self.state.snapshot()["projects"].items()
                if Path(p).is_dir() and stats.get("watch_enabled", True)
            ]
            if not roots:
                self.watch_reset.wait(1)
                continue
            try:
                reconcile = True
                for changes in watch(
                    *roots,
                    stop_event=self.watch_reset,
                    debounce=500,
                    step=100,
                    yield_on_timeout=True,
                    rust_timeout=1000,
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
                            if len(self.queues[root]) < 2 and not self.closed:
                                patterns = self.state.snapshot(root)["projects"][root].get(
                                    "file_patterns"
                                )
                                self.index(root, wait=False, file_patterns=patterns)
            except (OSError, RuntimeError):
                log.exception("Watcher failed; reconciling registered roots")
                self.watch_reset.wait(1)
                for root in roots:
                    if not self.closed and Path(root).is_dir():
                        self.index(
                            root,
                            wait=False,
                            file_patterns=self.state.snapshot(root)["projects"][root].get(
                                "file_patterns"
                            ),
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
