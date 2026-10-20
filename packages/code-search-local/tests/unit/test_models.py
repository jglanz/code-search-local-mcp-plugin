import sys
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from code_search_local import constants
from code_search_local.config import Settings
from code_search_local.models import ModelWorker, SentenceModel, choose_device
from code_search_local.storage import State, atomic_json
from tests import constants as test_constants
from tests.fakes import FakeModel


def torch_stub(
    build=constants.BACKEND_CUDA,
    available=True,
    count=test_constants.SHORT_STARTUP_BUDGET_SECONDS,
    mps=False,
):
    return NS(
        version=NS(
            hip="7.14" if build == constants.BACKEND_ROCM else None,
            cuda="13" if build == constants.BACKEND_CUDA else None,
        ),
        cuda=NS(
            is_available=lambda: available,
            device_count=lambda: count,
            get_device_name=lambda i: f"GPU {i}",
            memory_allocated=lambda device: 123,
            empty_cache=lambda: None,
        ),
        backends=NS(mps=NS(is_available=lambda: mps)),
    )


@pytest.mark.parametrize(
    "build,available,backend,expected",
    [
        (constants.BACKEND_CUDA, True, constants.BACKEND_AUTO, constants.BACKEND_CUDA),
        (constants.BACKEND_ROCM, True, constants.BACKEND_AUTO, constants.BACKEND_ROCM),
        (constants.BACKEND_CPU, False, constants.BACKEND_AUTO, constants.BACKEND_CPU),
        (constants.BACKEND_CUDA, True, constants.BACKEND_CPU, constants.BACKEND_CPU),
        (constants.BACKEND_ROCM, True, constants.BACKEND_ROCM, constants.BACKEND_ROCM),
        (constants.BACKEND_CUDA, True, constants.BACKEND_CUDA, constants.BACKEND_CUDA),
    ],
)
def test_backend_selection(build, available, backend, expected):
    result = choose_device(torch_stub(build, available), backend, 1)
    assert result[constants.KEY_BACKEND] == expected
    if expected in (constants.BACKEND_CUDA, constants.BACKEND_ROCM):
        assert result[constants.KEY_DEVICE] == "cuda:1"
        assert result[constants.KEY_GPU] == "GPU 1"


@pytest.mark.parametrize(
    "torch,backend,index",
    [
        (torch_stub(constants.BACKEND_CUDA), constants.BACKEND_ROCM, 0),
        (torch_stub(constants.BACKEND_ROCM), constants.BACKEND_CUDA, 0),
        (torch_stub(constants.BACKEND_CPU, False), constants.BACKEND_CUDA, 0),
        (torch_stub(constants.BACKEND_CUDA, False), constants.BACKEND_CUDA, 0),
        (torch_stub(constants.BACKEND_CUDA), constants.BACKEND_CUDA, 3),
        (torch_stub(constants.BACKEND_CPU, False), constants.BACKEND_MPS, 0),
    ],
)
def test_explicit_backend_failure_and_opt_in_fallback(torch, backend, index):
    with pytest.raises(RuntimeError):
        choose_device(torch, backend, index)
    result = choose_device(torch, backend, index, True)
    assert (
        result[constants.KEY_BACKEND] == constants.BACKEND_CPU
        and result[constants.KEY_FALLBACK_REASON]
    )


def test_mps_auto_and_explicit():
    for backend in (constants.BACKEND_AUTO, constants.BACKEND_MPS):
        assert (
            choose_device(torch_stub(constants.BACKEND_CPU, False, mps=True), backend)[
                constants.KEY_BACKEND
            ]
            == constants.BACKEND_MPS
        )


@pytest.fixture
def model_dependencies(tmp_path, monkeypatch):
    snapshot = (
        tmp_path
        / constants.MODEL_CACHE_DIRECTORY
        / test_constants.PATH_MODELS_FIXTURE
        / test_constants.PATH_SNAPSHOTS
        / test_constants.PATH_REVISION_123
    )
    snapshot.mkdir(parents=True)
    downloads, constructions = [], []

    def download(model, *, revision, cache_dir, local_files_only=False):
        downloads.append(local_files_only)
        if local_files_only:
            raise FileNotFoundError("cold cache")
        blobs = Path(cache_dir) / test_constants.PATH_MODELS_FIXTURE / test_constants.PATH_BLOBS
        blobs.mkdir(parents=True, exist_ok=True)
        (blobs / test_constants.VALUE_WEIGHTS).write_bytes(b"weights")
        return str(snapshot)

    class Transformer:
        prompts = {
            constants.DOCUMENT_PROMPT_NAME: constants.KEY_DOCUMENT,
            constants.QUERY_PROMPT_NAME: constants.KEY_QUERY,
        }

        def __init__(self, path, **kwargs):
            constructions.append(kwargs)

        def get_embedding_dimension(self):
            return 8

        def encode(self, texts, **kwargs):
            return np.ones((len(texts), 8), dtype=np.float32)

    monkeypatch.setitem(sys.modules, "torch", torch_stub())
    monkeypatch.setitem(sys.modules, "huggingface_hub", NS(snapshot_download=download))
    monkeypatch.setitem(sys.modules, "sentence_transformers", NS(SentenceTransformer=Transformer))
    return snapshot, downloads, constructions, Transformer


def test_download_once_and_local_snapshot_reuse(tmp_path, model_dependencies):
    snapshot, downloads, constructions, cls = model_dependencies
    settings = Settings(storage=str(tmp_path), backend=constants.BACKEND_CUDA)
    counters = []
    model = SentenceModel(settings, lambda **values: counters.append(values))
    assert downloads == [True, False]
    assert model.info[constants.KEY_REVISION] == test_constants.PATH_REVISION_123
    assert model.memory() == 123
    assert model.encode(["test"], constants.KEY_QUERY).shape == (1, 8)
    assert model.encode(["test"], constants.KEY_DOCUMENT).shape == (1, 8)
    model.close()
    model = SentenceModel(settings, lambda **values: counters.append(values))
    assert downloads == [True, False], "A valid pinned snapshot must not recontact the Hub"
    assert all(call[test_constants.KEY_LOCAL_FILES_ONLY] for call in constructions)
    assert any(row.get(test_constants.KEY_DOWNLOADED_FILES) == 1 for row in counters)
    model.close()


def test_offline_missing_model_fails_without_network(tmp_path, model_dependencies):
    _, downloads, _, _ = model_dependencies
    with pytest.raises(RuntimeError, match="offline"):
        SentenceModel(Settings(storage=str(tmp_path), offline=True), lambda **values: None)
    assert downloads == [True]


def test_gpu_runtime_failure_fallback_is_explicit(tmp_path, model_dependencies, monkeypatch):
    _, _, constructions, cls = model_dependencies
    original = cls.__init__

    def init(self, path, **kwargs):
        if kwargs[constants.KEY_DEVICE].startswith(constants.BACKEND_CUDA):
            raise RuntimeError("kernel unsupported")
        original(self, path, **kwargs)

    monkeypatch.setattr(cls, "__init__", init)
    settings = Settings(storage=str(tmp_path), backend=constants.BACKEND_CUDA)
    with pytest.raises(RuntimeError, match="kernel"):
        SentenceModel(settings, lambda **values: None)
    model = SentenceModel(replace(settings, cpu_fallback=True), lambda **values: None)
    assert model.info[constants.KEY_BACKEND] == constants.BACKEND_CPU
    assert model.info[constants.KEY_FALLBACK_REASON] == "kernel unsupported"
    assert model.memory() == 0
    model.close()


def test_worker_fairness_queue_limits_and_cancellation(tmp_path):
    root = tmp_path / test_constants.KEY_STATE
    root.mkdir()
    state = State(root)
    settings = Settings(storage=str(root), watch=False, max_pending_jobs=2)
    entered, release = threading.Event(), threading.Event()
    order = []

    class Slow(FakeModel):
        def encode(self, texts, purpose):
            order.extend(texts)
            if len(order) == 1:
                entered.set()
                assert release.wait(test_constants.THREAD_RELEASE_TIMEOUT_SECONDS)
            return super().encode(texts, purpose)

    worker = ModelWorker(settings, state, Slow)
    try:
        first = worker.submit("A", ["a1"])
        assert entered.wait(test_constants.THREAD_ENTRY_TIMEOUT_SECONDS)
        second = worker.submit("A", ["a2"])
        third = worker.submit("A", ["a3"])
        other = worker.submit("B", ["b1"])
        cancelled = worker.submit("C", ["c1"])
        cancelled.cancel()
        with pytest.raises(RuntimeError, match="full"):
            worker.submit("D", ["d1"])
        release.set()
        for future in (first, second, third, other):
            future.result(5)
        assert order == ["a1", "a2", "b1", "a3"]
        with pytest.raises(ValueError):
            worker.submit("A", purpose="bad")
        assert worker.encode("A", []).shape == (0, 64)
    finally:
        release.set()
        worker.close()
        state.close()
    with pytest.raises(RuntimeError, match="stopping"):
        worker.submit("A")


def test_worker_deduplicates_content_and_validates_output(tmp_path):
    root = tmp_path / test_constants.KEY_STATE
    root.mkdir()
    state = State(root)
    with state.edit() as value:
        value[constants.KEY_PROJECTS][test_constants.KEY_A] = {}

    class Invalid(FakeModel):
        def encode(self, texts, purpose):
            if texts == ["invalid"]:
                return np.array([[float("nan")]])
            return super().encode(texts, purpose)

    worker = ModelWorker(Settings(storage=str(root), model_batch_size=3), state, Invalid)
    try:
        result = worker.encode("A", ["same", "same", "unique"])
        assert np.array_equal(result[0], result[1])
        worker.encode("A", ["same"])
        stats = state.snapshot()[constants.KEY_PROJECTS][test_constants.KEY_A]
        assert stats[constants.KEY_CACHE_HITS] == 2 and stats[constants.KEY_CACHE_MISSES] == 2
        with pytest.raises(ValueError, match="invalid embeddings"):
            worker.encode("A", ["invalid"])
        assert worker.encode("A", ["after error"]).shape == (1, 64)
    finally:
        worker.close()
        state.close()


def test_stale_snapshot_pointer_reacquires(tmp_path, model_dependencies):
    snapshot, downloads, _, _ = model_dependencies
    settings = Settings(storage=str(tmp_path))
    first = SentenceModel(settings, lambda **values: None)
    first.close()
    pointer = next((tmp_path / constants.MODEL_CACHE_DIRECTORY).glob(test_constants.PATH_JSON))
    atomic_json(
        pointer, {constants.KEY_SNAPSHOT: str(tmp_path / test_constants.PATH_DELETED_SNAPSHOT)}
    )
    second = SentenceModel(settings, lambda **values: None)
    second.close()
    assert downloads == [True, False, True, False]


def test_worker_initialization_failure_is_reported(tmp_path, monkeypatch):
    from code_search_local import models

    root = tmp_path / test_constants.KEY_STATE
    root.mkdir()
    state = State(root)

    def fail(*args, **kwargs):
        raise OSError("cannot open cache")

    monkeypatch.setattr(models.sqlite3, "connect", fail)
    with pytest.raises(OSError, match="cannot open cache"):
        ModelWorker(Settings(storage=str(root)), state, FakeModel)
    state.close()


@pytest.mark.parametrize("fallback", [True, False])
def test_inference_failure_respects_cpu_fallback(
    tmp_path, model_dependencies, monkeypatch, fallback
):
    _, _, _, cls = model_dependencies
    counters = []
    model = SentenceModel(
        Settings(storage=str(tmp_path), backend=constants.BACKEND_CUDA, cpu_fallback=fallback),
        lambda **values: counters.append(values),
    )
    moves = []
    monkeypatch.setattr(cls, "to", lambda self, device: moves.append(device), raising=False)

    def encode(self, texts, **kwargs):
        if not moves:
            raise RuntimeError("GPU out of memory")
        return np.ones((len(texts), 8), dtype=np.float32)

    monkeypatch.setattr(cls, "encode", encode)
    try:
        if fallback:
            assert model.encode([constants.KEY_QUERY], constants.KEY_QUERY).shape == (1, 8)
            assert moves == [constants.BACKEND_CPU]
            assert model.info[constants.KEY_BACKEND] == constants.BACKEND_CPU
            assert model.info[constants.KEY_FALLBACK_REASON] == "GPU out of memory"
            assert {test_constants.KEY_FALLBACK_EVENTS: 1} in counters
        else:
            with pytest.raises(RuntimeError, match="out of memory"):
                model.encode([constants.KEY_QUERY], constants.KEY_QUERY)
            assert moves == []
    finally:
        model.close()


def test_interrupted_acquisition_does_not_publish_snapshot_and_can_resume(
    tmp_path, model_dependencies, monkeypatch
):
    snapshot, _, constructions, _ = model_dependencies
    online_attempts = 0
    partial = tmp_path / test_constants.PATH_MODELS_MODELS_FIXTURE_BLOBS_WEIGHTS_INCOMPLETE

    def download(model, *, revision, cache_dir, local_files_only=False):
        nonlocal online_attempts
        if local_files_only:
            raise FileNotFoundError("no complete snapshot")
        online_attempts += 1
        if online_attempts == 1:
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_bytes(b"partial")
            raise ConnectionError("download interrupted")
        assert partial.read_bytes() == b"partial"
        partial.rename(partial.with_suffix(""))
        return str(snapshot)

    monkeypatch.setattr(
        sys.modules[test_constants.KEY_HUGGINGFACE_HUB], "snapshot_download", download
    )
    counters = []
    settings = Settings(storage=str(tmp_path), backend=constants.BACKEND_CPU)
    with pytest.raises(ConnectionError, match=constants.STATUS_INTERRUPTED):
        SentenceModel(settings, lambda **values: counters.append(values))
    assert not list((tmp_path / constants.MODEL_CACHE_DIRECTORY).glob(test_constants.PATH_JSON))
    assert constructions == []
    model = SentenceModel(settings, lambda **values: counters.append(values))
    try:
        assert len(constructions) == 1
        assert sum(item.get(test_constants.KEY_MODEL_DOWNLOADS, 0) for item in counters) == 1
        assert (
            len(list((tmp_path / constants.MODEL_CACHE_DIRECTORY).glob(test_constants.PATH_JSON)))
            == 1
        )
    finally:
        model.close()
