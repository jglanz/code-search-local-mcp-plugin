import sys
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from code_search_local.config import Settings
from code_search_local.models import ModelWorker, SentenceModel, choose_device
from code_search_local.storage import State, atomic_json
from tests.fakes import FakeModel


def torch_stub(build="cuda", available=True, count=2, mps=False):
    return NS(
        version=NS(hip="7.14" if build == "rocm" else None, cuda="13" if build == "cuda" else None),
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
        ("cuda", True, "auto", "cuda"),
        ("rocm", True, "auto", "rocm"),
        ("cpu", False, "auto", "cpu"),
        ("cuda", True, "cpu", "cpu"),
        ("rocm", True, "rocm", "rocm"),
        ("cuda", True, "cuda", "cuda"),
    ],
)
def test_backend_selection(build, available, backend, expected):
    result = choose_device(torch_stub(build, available), backend, 1)
    assert result["backend"] == expected
    if expected in ("cuda", "rocm"):
        assert result["device"] == "cuda:1"
        assert result["gpu"] == "GPU 1"


@pytest.mark.parametrize(
    "torch,backend,index",
    [
        (torch_stub("cuda"), "rocm", 0),
        (torch_stub("rocm"), "cuda", 0),
        (torch_stub("cpu", False), "cuda", 0),
        (torch_stub("cuda", False), "cuda", 0),
        (torch_stub("cuda"), "cuda", 3),
        (torch_stub("cpu", False), "mps", 0),
    ],
)
def test_explicit_backend_failure_and_opt_in_fallback(torch, backend, index):
    with pytest.raises(RuntimeError):
        choose_device(torch, backend, index)
    result = choose_device(torch, backend, index, True)
    assert result["backend"] == "cpu" and result["fallback_reason"]


def test_mps_auto_and_explicit():
    for backend in ("auto", "mps"):
        assert choose_device(torch_stub("cpu", False, mps=True), backend)["backend"] == "mps"


@pytest.fixture
def model_dependencies(tmp_path, monkeypatch):
    snapshot = tmp_path / "models" / "models--fixture" / "snapshots" / "revision-123"
    snapshot.mkdir(parents=True)
    downloads, constructions = [], []

    def download(model, *, revision, cache_dir, local_files_only=False):
        downloads.append(local_files_only)
        if local_files_only:
            raise FileNotFoundError("cold cache")
        blobs = Path(cache_dir) / "models--fixture" / "blobs"
        blobs.mkdir(parents=True, exist_ok=True)
        (blobs / "weights").write_bytes(b"weights")
        return str(snapshot)

    class Transformer:
        prompts = {"Retrieval-document": "document", "InstructionRetrieval": "query"}

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
    settings = Settings(storage=str(tmp_path), backend="cuda")
    counters = []
    model = SentenceModel(settings, lambda **values: counters.append(values))
    assert downloads == [True, False]
    assert model.info["revision"] == "revision-123"
    assert model.memory() == 123
    assert model.encode(["test"], "query").shape == (1, 8)
    assert model.encode(["test"], "document").shape == (1, 8)
    model.close()
    model = SentenceModel(settings, lambda **values: counters.append(values))
    assert downloads == [True, False], "A valid pinned snapshot must not recontact the Hub"
    assert all(call["local_files_only"] for call in constructions)
    assert any(row.get("downloaded_files") == 1 for row in counters)
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
        if kwargs["device"].startswith("cuda"):
            raise RuntimeError("kernel unsupported")
        original(self, path, **kwargs)

    monkeypatch.setattr(cls, "__init__", init)
    settings = Settings(storage=str(tmp_path), backend="cuda")
    with pytest.raises(RuntimeError, match="kernel"):
        SentenceModel(settings, lambda **values: None)
    model = SentenceModel(replace(settings, cpu_fallback=True), lambda **values: None)
    assert model.info["backend"] == "cpu"
    assert model.info["fallback_reason"] == "kernel unsupported"
    assert model.memory() == 0
    model.close()


def test_worker_fairness_queue_limits_and_cancellation(tmp_path):
    root = tmp_path / "state"
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
                assert release.wait(10)
            return super().encode(texts, purpose)

    worker = ModelWorker(settings, state, Slow)
    try:
        first = worker.submit("A", ["a1"])
        assert entered.wait(5)
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
    root = tmp_path / "state"
    root.mkdir()
    state = State(root)
    with state.edit() as value:
        value["projects"]["A"] = {}

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
        stats = state.snapshot()["projects"]["A"]
        assert stats["cache_hits"] == 2 and stats["cache_misses"] == 2
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
    pointer = next((tmp_path / "models").glob("*.json"))
    atomic_json(pointer, {"snapshot": str(tmp_path / "deleted-snapshot")})
    second = SentenceModel(settings, lambda **values: None)
    second.close()
    assert downloads == [True, False, True, False]


def test_worker_initialization_failure_is_reported(tmp_path, monkeypatch):
    from code_search_local import models

    root = tmp_path / "state"
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
        Settings(storage=str(tmp_path), backend="cuda", cpu_fallback=fallback),
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
            assert model.encode(["query"], "query").shape == (1, 8)
            assert moves == ["cpu"]
            assert model.info["backend"] == "cpu"
            assert model.info["fallback_reason"] == "GPU out of memory"
            assert {"fallback_events": 1} in counters
        else:
            with pytest.raises(RuntimeError, match="out of memory"):
                model.encode(["query"], "query")
            assert moves == []
    finally:
        model.close()


def test_interrupted_acquisition_does_not_publish_snapshot_and_can_resume(
    tmp_path, model_dependencies, monkeypatch
):
    snapshot, _, constructions, _ = model_dependencies
    online_attempts = 0
    partial = tmp_path / "models/models--fixture/blobs/weights.incomplete"

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

    monkeypatch.setattr(sys.modules["huggingface_hub"], "snapshot_download", download)
    counters = []
    settings = Settings(storage=str(tmp_path), backend="cpu")
    with pytest.raises(ConnectionError, match="interrupted"):
        SentenceModel(settings, lambda **values: counters.append(values))
    assert not list((tmp_path / "models").glob("*.json"))
    assert constructions == []
    model = SentenceModel(settings, lambda **values: counters.append(values))
    try:
        assert len(constructions) == 1
        assert sum(item.get("model_downloads", 0) for item in counters) == 1
        assert len(list((tmp_path / "models").glob("*.json"))) == 1
    finally:
        model.close()
