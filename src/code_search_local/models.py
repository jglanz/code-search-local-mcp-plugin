"""One fair, bounded model worker; no client or project owns a model."""

import hashlib
import json
import logging
import sqlite3
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path

from .storage import atomic_json

log = logging.getLogger(__name__)


def choose_device(torch, backend, gpu_index=0, fallback=False):
    """HIP exposes torch.cuda; the build tag distinguishes AMD from NVIDIA."""
    actual = "rocm" if torch.version.hip else "cuda"
    if backend == "cpu":
        return {"backend": "cpu", "device": "cpu", "gpu": None, "fallback_reason": None}
    if backend == "auto":
        backend = (
            actual
            if torch.cuda.is_available()
            else (
                "mps"
                if hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
                else "cpu"
            )
        )
        return choose_device(torch, backend, gpu_index, fallback)
    error = None
    if backend == "mps":
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return {"backend": "mps", "device": "mps", "gpu": "Apple MPS", "fallback_reason": None}
        error = "MPS is unavailable"
    elif actual != backend:
        error = f"Requested {backend}, but installed PyTorch is a {actual if torch.version.cuda or torch.version.hip else 'CPU'} build"
    elif not torch.cuda.is_available() or gpu_index >= torch.cuda.device_count():
        error = f"{backend} GPU {gpu_index} is unavailable"
    else:
        return {
            "backend": backend,
            "device": f"cuda:{gpu_index}",
            "gpu": torch.cuda.get_device_name(gpu_index),
            "gpu_index": gpu_index,
            "fallback_reason": None,
        }
    if not fallback:
        raise RuntimeError(error)
    return {"backend": "cpu", "device": "cpu", "gpu": None, "fallback_reason": error}


class SentenceModel:
    """Constructed, used, and closed exclusively on the model thread."""

    def __init__(self, settings, report):
        import torch
        from huggingface_hub import snapshot_download
        from sentence_transformers import SentenceTransformer

        self.torch = torch
        self.settings = settings
        self.report = report
        self.info = choose_device(
            torch, settings.backend, settings.gpu_index, settings.allow_fallback
        )
        if settings.backend == "auto" and self.info["backend"] == "cpu":
            self.info["fallback_reason"] = "No usable accelerator in the selected PyTorch runtime"
        if self.info["fallback_reason"]:
            report(fallback_events=1)
        model_cache = settings.root / "models"
        key = hashlib.sha256(f"{settings.model}@{settings.revision}".encode()).hexdigest()
        pointer = model_cache / f"{key}.json"
        snapshot = None
        if pointer.exists():
            saved = json.loads(pointer.read_text())
            if Path(saved["snapshot"]).is_dir():
                snapshot = saved["snapshot"]
        if snapshot is None:
            # Try the shared Hub cache first. Offline mode never performs an HTTP request.
            try:
                snapshot = snapshot_download(
                    settings.model,
                    revision=settings.revision,
                    cache_dir=str(model_cache),
                    local_files_only=True,
                )
            except Exception:
                if settings.offline:
                    raise RuntimeError(
                        "Model is not cached; offline mode forbids downloading"
                    ) from None
                before = self._blobs(model_cache)
                report(model_acquisitions=1)
                snapshot = snapshot_download(
                    settings.model, revision=settings.revision, cache_dir=str(model_cache)
                )
                after = self._blobs(model_cache)
                new = after.keys() - before.keys()
                report(
                    model_downloads=1,
                    downloaded_files=len(new),
                    downloaded_bytes=sum(after[path] for path in new),
                )
            atomic_json(pointer, {"snapshot": str(snapshot)})
        self.info.update(
            model=settings.model,
            requested_revision=settings.revision,
            revision=Path(snapshot).name,
            requested_backend=settings.backend,
        )
        try:
            self.model = SentenceTransformer(
                snapshot, device=self.info["device"], local_files_only=True, trust_remote_code=False
            )
            # Force kernel initialization now: setup must not silently enable a broken GPU runtime.
            self.model.encode(["code search backend validation"], show_progress_bar=False)
        except Exception as error:
            if self.info["backend"] == "cpu" or not settings.allow_fallback:
                raise
            self.info.update(backend="cpu", device="cpu", gpu=None, fallback_reason=str(error))
            report(fallback_events=1)
            self.model = SentenceTransformer(
                snapshot, device="cpu", local_files_only=True, trust_remote_code=False
            )
            self.model.encode(["code search backend validation"], show_progress_bar=False)
        self.info["dimension"] = self.model.get_embedding_dimension()
        self.info["encoding"] = {"normalize": True, "max_chars": 6000, "format_version": 1}
        report(model_loads=1)

    @staticmethod
    def _blobs(root):
        return {
            str(path): path.stat().st_size
            for path in root.glob("models--*/blobs/*")
            if path.is_file() and not path.name.endswith(".incomplete")
        }

    def encode(self, texts, purpose):
        prompts = getattr(self.model, "prompts", {})
        preferred = "Retrieval-document" if purpose == "document" else "InstructionRetrieval"
        prompt = preferred if preferred in prompts else (purpose if purpose in prompts else None)
        kwargs = dict(
            prompt_name=prompt,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        try:
            return self.model.encode(texts, **kwargs)
        except RuntimeError as error:
            if self.info["backend"] == "cpu" or not self.settings.allow_fallback:
                raise
            self.model.to("cpu")
            self.info.update(backend="cpu", device="cpu", gpu=None, fallback_reason=str(error))
            self.report(fallback_events=1)
            if self.torch.cuda.is_available():
                self.torch.cuda.empty_cache()
            return self.model.encode(texts, **kwargs)

    def memory(self):
        if self.info["backend"] in ("cuda", "rocm"):
            return self.torch.cuda.memory_allocated(self.info["device"])
        return 0

    def close(self):
        del self.model
        if self.info["backend"] in ("cuda", "rocm"):
            self.torch.cuda.empty_cache()


@dataclass
class Request:
    future: Future
    project: str
    texts: list[str] | None
    purpose: str


class ModelWorker:
    def __init__(self, settings, state, factory=SentenceModel):
        self.settings, self.state, self.factory = settings, state, factory
        self.condition = threading.Condition()
        self.queues = OrderedDict()
        self.stopping = False
        self.pending = 0
        self.model = None
        self.ready = Future()
        self.thread = threading.Thread(target=self._run, name="code-search-model", daemon=True)
        self.thread.start()
        self.ready.result()

    def submit(self, project, texts=None, purpose="document"):
        if purpose not in ("document", "query"):
            raise ValueError("Invalid embedding purpose")
        future = Future()
        with self.condition:
            if self.stopping:
                raise RuntimeError("Model worker is stopping")
            if self.pending >= self.settings.max_pending_jobs * 2:
                raise RuntimeError("Model queue is full; retry later")
            self.queues.setdefault(project, deque()).append(
                Request(future, project, texts, purpose)
            )
            self.pending += 1
            self.condition.notify()
        return future

    def info(self, project):
        return self.submit(project).result()

    def encode(self, project, texts, purpose="document"):
        import numpy as np

        batches = []
        size = self.settings.model_batch_size
        for start in range(0, len(texts), size):
            batches.append(self.submit(project, texts[start : start + size], purpose).result())
        if not batches:
            return np.empty((0, self.info(project)["dimension"]), dtype="float32")
        return np.concatenate(batches)

    def _report(self, **counters):
        with self.state.edit("model.changed") as value:
            shared = value["shared"]
            for key, count in counters.items():
                shared[key] = shared.get(key, 0) + count

    def _run(self):
        db = None
        try:
            db = sqlite3.connect(self.settings.root / "embedding-cache.sqlite3")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector BLOB NOT NULL)"
            )
        except Exception as error:
            if db is not None:
                db.close()
            self.ready.set_exception(error)
            return
        self.ready.set_result(None)
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.queues or self.stopping)
                    if not self.queues:
                        break
                    project, queue = self.queues.popitem(last=False)
                    request = queue.popleft()
                    if queue:
                        self.queues[project] = queue
                    self.pending -= 1
                if not request.future.set_running_or_notify_cancel():
                    continue
                try:
                    if self.model is None:
                        self.model = self.factory(self.settings, self._report)
                        with self.state.edit("model.loaded") as value:
                            value["shared"]["model"] = dict(self.model.info)
                            value["shared"]["model_resident"] = True
                    result = (
                        dict(self.model.info)
                        if request.texts is None
                        else self._encode(db, request)
                    )
                    request.future.set_result(result)
                except Exception as error:
                    log.exception("Model request failed")
                    request.future.set_exception(error)
        finally:
            if self.model is not None:
                self.model.close()
                self.model = None
            db.close()

    def _encode(self, db, request):
        import numpy as np

        # Hardware does not define embedding identity, but dtype/encoding settings do.
        identity = {k: self.model.info[k] for k in ("model", "revision", "encoding", "dimension")}
        fingerprint = json.dumps(identity, sort_keys=True)
        keys = [
            hashlib.sha256(f"{fingerprint}:{request.purpose}:{text}".encode()).hexdigest()
            for text in request.texts
        ]
        vectors = {}
        hits = 0
        missing = {}
        for key, text in zip(keys, request.texts):
            row = db.execute("SELECT vector FROM embeddings WHERE key=?", (key,)).fetchone()
            if row:
                vectors[key] = np.frombuffer(row[0], dtype=np.float32).copy()
                hits += 1
            elif key in missing:
                hits += 1
            else:
                missing[key] = text
        if missing:
            start = time.monotonic()
            encoded = np.asarray(
                self.model.encode(list(missing.values()), request.purpose), dtype=np.float32
            )
            if (
                encoded.shape != (len(missing), self.model.info["dimension"])
                or not np.isfinite(encoded).all()
            ):
                raise ValueError("Model produced invalid embeddings")
            for key, vector in zip(missing, encoded):
                vectors[key] = vector
                db.execute(
                    "INSERT OR REPLACE INTO embeddings VALUES (?,?)", (key, vector.tobytes())
                )
            db.commit()
            self._report(
                inference_batches=1,
                inference_seconds=time.monotonic() - start,
                embedded_texts=len(missing),
            )
        with self.state.edit("cache.changed", request.project) as value:
            project = value["projects"].get(request.project)
            if project is not None:
                project["cache_hits"] = project.get("cache_hits", 0) + hits
                project["cache_misses"] = project.get("cache_misses", 0) + len(missing)
                project["active_model"] = dict(self.model.info)
            value["shared"]["model"] = dict(self.model.info)
            value["shared"]["gpu_memory_bytes"] = self.model.memory()
            value["shared"]["max_concurrent_inference"] = 1
        return np.stack([vectors[key] for key in keys])

    def close(self):
        with self.condition:
            self.stopping = True
            self.condition.notify_all()
        self.thread.join()
