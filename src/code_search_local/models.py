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

from code_search_local import constants

from .storage import atomic_json

log = logging.getLogger(__name__)


def choose_device(torch, backend, gpu_index=0, fallback=False):
    """HIP exposes torch.cuda; the build tag distinguishes AMD from NVIDIA."""
    actual = constants.BACKEND_ROCM if torch.version.hip else constants.BACKEND_CUDA
    if backend == constants.BACKEND_CPU:
        return {
            constants.KEY_BACKEND: constants.BACKEND_CPU,
            constants.KEY_DEVICE: constants.BACKEND_CPU,
            constants.KEY_GPU: None,
            constants.KEY_FALLBACK_REASON: None,
        }
    if backend == constants.BACKEND_AUTO:
        backend = (
            actual
            if torch.cuda.is_available()
            else (
                constants.BACKEND_MPS
                if hasattr(torch.backends, constants.BACKEND_MPS)
                and torch.backends.mps.is_available()
                else constants.BACKEND_CPU
            )
        )
        return choose_device(torch, backend, gpu_index, fallback)
    error = None
    if backend == constants.BACKEND_MPS:
        if hasattr(torch.backends, constants.BACKEND_MPS) and torch.backends.mps.is_available():
            return {
                constants.KEY_BACKEND: constants.BACKEND_MPS,
                constants.KEY_DEVICE: constants.BACKEND_MPS,
                constants.KEY_GPU: "Apple MPS",
                constants.KEY_FALLBACK_REASON: None,
            }
        error = "MPS is unavailable"
    elif actual != backend:
        error = f"Requested {backend}, but installed PyTorch is a {actual if torch.version.cuda or torch.version.hip else constants.DEVICE_LABEL_CPU} build"
    elif not torch.cuda.is_available() or gpu_index >= torch.cuda.device_count():
        error = f"{backend} GPU {gpu_index} is unavailable"
    else:
        return {
            constants.KEY_BACKEND: backend,
            constants.KEY_DEVICE: constants.TORCH_GPU_DEVICE_TEMPLATE.format(index=gpu_index),
            constants.KEY_GPU: torch.cuda.get_device_name(gpu_index),
            constants.KEY_GPU_INDEX: gpu_index,
            constants.KEY_FALLBACK_REASON: None,
        }
    if not fallback:
        raise RuntimeError(error)
    return {
        constants.KEY_BACKEND: constants.BACKEND_CPU,
        constants.KEY_DEVICE: constants.BACKEND_CPU,
        constants.KEY_GPU: None,
        constants.KEY_FALLBACK_REASON: error,
    }


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
        if (
            settings.backend == constants.BACKEND_AUTO
            and self.info[constants.KEY_BACKEND] == constants.BACKEND_CPU
        ):
            self.info[constants.KEY_FALLBACK_REASON] = (
                "No usable accelerator in the selected PyTorch runtime"
            )
        if self.info[constants.KEY_FALLBACK_REASON]:
            report(fallback_events=1)
        model_cache = settings.root / constants.MODEL_CACHE_DIRECTORY
        key = hashlib.sha256(f"{settings.model}@{settings.revision}".encode()).hexdigest()
        pointer = model_cache / constants.MODEL_POINTER_FILENAME_TEMPLATE.format(key=key)
        snapshot = None
        if pointer.exists():
            saved = json.loads(pointer.read_text())
            if Path(saved[constants.KEY_SNAPSHOT]).is_dir():
                snapshot = saved[constants.KEY_SNAPSHOT]
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
            atomic_json(pointer, {constants.KEY_SNAPSHOT: str(snapshot)})
        self.info.update(
            model=settings.model,
            requested_revision=settings.revision,
            revision=Path(snapshot).name,
            requested_backend=settings.backend,
        )
        try:
            self.model = SentenceTransformer(
                snapshot,
                device=self.info[constants.KEY_DEVICE],
                local_files_only=True,
                trust_remote_code=False,
            )
            # Force kernel initialization now: setup must not silently enable a broken GPU runtime.
            self.model.encode(["code search backend validation"], show_progress_bar=False)
        except Exception as error:
            if (
                self.info[constants.KEY_BACKEND] == constants.BACKEND_CPU
                or not settings.allow_fallback
            ):
                raise
            self.info.update(
                backend=constants.BACKEND_CPU,
                device=constants.BACKEND_CPU,
                gpu=None,
                fallback_reason=str(error),
            )
            report(fallback_events=1)
            self.model = SentenceTransformer(
                snapshot,
                device=constants.BACKEND_CPU,
                local_files_only=True,
                trust_remote_code=False,
            )
            self.model.encode(["code search backend validation"], show_progress_bar=False)
        self.info[constants.KEY_DIMENSION] = self.model.get_embedding_dimension()
        self.info[constants.KEY_ENCODING] = {
            constants.KEY_NORMALIZE: True,
            constants.KEY_MAX_CHARS: constants.EMBEDDING_MAX_CHARACTERS,
            constants.KEY_FORMAT_VERSION: constants.EMBEDDING_FORMAT_VERSION,
        }
        report(model_loads=1)

    @staticmethod
    def _blobs(root):
        return {
            str(path): path.stat().st_size
            for path in root.glob(constants.PATH_MODELS_BLOBS)
            if path.is_file() and not path.name.endswith(constants.PATH_INCOMPLETE)
        }

    def encode(self, texts, purpose):
        prompts = getattr(self.model, constants.KEY_PROMPTS, {})
        preferred = (
            constants.DOCUMENT_PROMPT_NAME
            if purpose == constants.KEY_DOCUMENT
            else constants.QUERY_PROMPT_NAME
        )
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
            if (
                self.info[constants.KEY_BACKEND] == constants.BACKEND_CPU
                or not self.settings.allow_fallback
            ):
                raise
            self.model.to(constants.BACKEND_CPU)
            self.info.update(
                backend=constants.BACKEND_CPU,
                device=constants.BACKEND_CPU,
                gpu=None,
                fallback_reason=str(error),
            )
            self.report(fallback_events=1)
            if self.torch.cuda.is_available():
                self.torch.cuda.empty_cache()
            return self.model.encode(texts, **kwargs)

    def memory(self):
        if self.info[constants.KEY_BACKEND] in (constants.BACKEND_CUDA, constants.BACKEND_ROCM):
            return self.torch.cuda.memory_allocated(self.info[constants.KEY_DEVICE])
        return 0

    def close(self):
        del self.model
        if self.info[constants.KEY_BACKEND] in (constants.BACKEND_CUDA, constants.BACKEND_ROCM):
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
        self.thread = threading.Thread(
            target=self._run, name=constants.MODEL_THREAD_NAME, daemon=True
        )
        self.thread.start()
        self.ready.result()

    def submit(self, project, texts=None, purpose=constants.KEY_DOCUMENT):
        if purpose not in (constants.KEY_DOCUMENT, constants.KEY_QUERY):
            raise ValueError("Invalid embedding purpose")
        future = Future()
        with self.condition:
            if self.stopping:
                raise RuntimeError("Model worker is stopping")
            if (
                self.pending
                >= self.settings.max_pending_jobs * constants.MODEL_QUEUE_CAPACITY_MULTIPLIER
            ):
                raise RuntimeError("Model queue is full; retry later")
            self.queues.setdefault(project, deque()).append(
                Request(future, project, texts, purpose)
            )
            self.pending += 1
            self.condition.notify()
        return future

    def info(self, project):
        return self.submit(project).result()

    def encode(self, project, texts, purpose=constants.KEY_DOCUMENT):
        import numpy as np

        batches = []
        size = self.settings.model_batch_size
        for start in range(0, len(texts), size):
            batches.append(self.submit(project, texts[start : start + size], purpose).result())
        if not batches:
            return np.empty(
                (0, self.info(project)[constants.KEY_DIMENSION]), dtype=constants.VECTOR_DTYPE
            )
        return np.concatenate(batches)

    def _report(self, **counters):
        with self.state.edit(constants.EVENT_MODEL_CHANGED) as value:
            shared = value[constants.KEY_SHARED]
            for key, count in counters.items():
                shared[key] = shared.get(key, 0) + count

    def _run(self):
        db = None
        try:
            db = sqlite3.connect(self.settings.root / constants.PATH_EMBEDDING_CACHE_SQLITE3)
            db.execute(constants.SQL_ENABLE_WAL)
            db.execute(constants.SQL_CREATE_EMBEDDINGS)
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
                        with self.state.edit(constants.EVENT_MODEL_LOADED) as value:
                            value[constants.KEY_SHARED][constants.KEY_MODEL] = dict(self.model.info)
                            value[constants.KEY_SHARED][constants.KEY_MODEL_RESIDENT] = True
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
        identity = {
            k: self.model.info[k]
            for k in (
                constants.KEY_MODEL,
                constants.KEY_REVISION,
                constants.KEY_ENCODING,
                constants.KEY_DIMENSION,
            )
        }
        fingerprint = json.dumps(identity, sort_keys=True)
        keys = [
            hashlib.sha256(
                constants.EMBEDDING_CACHE_KEY_TEMPLATE.format(
                    fingerprint=fingerprint, purpose=request.purpose, text=text
                ).encode()
            ).hexdigest()
            for text in request.texts
        ]
        vectors = {}
        hits = 0
        missing = {}
        for key, text in zip(keys, request.texts):
            row = db.execute(constants.SQL_READ_EMBEDDING, (key,)).fetchone()
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
                encoded.shape != (len(missing), self.model.info[constants.KEY_DIMENSION])
                or not np.isfinite(encoded).all()
            ):
                raise ValueError("Model produced invalid embeddings")
            for key, vector in zip(missing, encoded):
                vectors[key] = vector
                db.execute(constants.SQL_SAVE_EMBEDDING, (key, vector.tobytes()))
            db.commit()
            self._report(
                inference_batches=1,
                inference_seconds=time.monotonic() - start,
                embedded_texts=len(missing),
            )
        with self.state.edit(constants.EVENT_CACHE_CHANGED, request.project) as value:
            project = value[constants.KEY_PROJECTS].get(request.project)
            if project is not None:
                project[constants.KEY_CACHE_HITS] = project.get(constants.KEY_CACHE_HITS, 0) + hits
                project[constants.KEY_CACHE_MISSES] = project.get(
                    constants.KEY_CACHE_MISSES, 0
                ) + len(missing)
                project[constants.KEY_ACTIVE_MODEL] = dict(self.model.info)
            value[constants.KEY_SHARED][constants.KEY_MODEL] = dict(self.model.info)
            value[constants.KEY_SHARED][constants.KEY_GPU_MEMORY_BYTES] = self.model.memory()
            value[constants.KEY_SHARED][constants.KEY_MAX_CONCURRENT_INFERENCE] = 1
        return np.stack([vectors[key] for key in keys])

    def close(self):
        with self.condition:
            self.stopping = True
            self.condition.notify_all()
        self.thread.join()
