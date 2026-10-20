import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from code_search_local import constants
from code_search_local.config import Settings
from code_search_local.engine import Engine
from code_search_local.storage import Generations, ServiceLock, offline_stats
from tests import constants as test_constants
from tests.fakes import FakeModel


@pytest.fixture
def settings(tmp_path):
    return Settings(
        storage=str(tmp_path / test_constants.KEY_STATE), watch=False, model_batch_size=2
    )


@pytest.fixture
def roots(tmp_path):
    result = []
    for name in ("alpha", "beta"):
        root = tmp_path / name
        root.mkdir()
        (root / test_constants.PATH_COMMON_PY).write_text(
            "def shared_cache():\n    return 'shared'\n"
        )
        (root / f"{name}.py").write_text(f"def {name}_secret():\n    return '{name}'\n")
        result.append(str(root))
    return result


@pytest.fixture
def engine(settings):
    value = Engine(settings, model_factory=FakeModel)
    yield value
    value.close()


def test_two_projects_share_one_model_and_keep_indexes(engine, roots):
    with ThreadPoolExecutor(2) as pool:
        jobs = list(pool.map(engine.index, roots))
    assert all(job[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED for job in jobs)
    stats = engine.state.snapshot()
    assert stats[constants.KEY_SHARED][test_constants.KEY_MODEL_LOADS] == 1
    assert stats[constants.KEY_SHARED][test_constants.KEY_MODEL_ACQUISITIONS] == 1
    assert stats[constants.KEY_SHARED][constants.KEY_MAX_CONCURRENT_INFERENCE] == 1
    assert sum(p[constants.KEY_CACHE_HITS] for p in stats[constants.KEY_PROJECTS].values()) >= 1
    for root in roots:
        results = engine.search(root, Path(root).name)[constants.KEY_RESULTS]
        assert results
        assert all(
            result[test_constants.KEY_FILE_PATH].startswith(root + "/") for result in results
        )
        assert (
            engine.job(root, jobs[roots.index(root)][constants.KEY_JOB_ID])[constants.KEY_STATUS]
            == constants.STATUS_SUCCEEDED
        )
    with pytest.raises(KeyError):
        engine.job(roots[0], jobs[1][constants.KEY_JOB_ID])


def test_incremental_add_modify_delete_and_filters(engine, roots):
    root = Path(roots[0])
    assert engine.index(str(root))[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED
    (root / test_constants.PATH_ALPHA_PY).unlink()
    (root / test_constants.PATH_COMMON_PY).write_text("def modified():\n    return 'modified'\n")
    (root / test_constants.PATH_NEW_PY).write_text("def added():\n    return 'added'\n")
    job = engine.index(str(root))
    assert job[test_constants.KEY_RESULT][constants.KEY_CHANGES] == {
        constants.KEY_ADDED: 1,
        constants.KEY_DELETED: 1,
        constants.KEY_MODIFIED: 1,
    }
    results = engine.search(
        str(root), constants.KEY_FUNCTION, filters={constants.KEY_RELATIVE_PATH: "new.py"}
    )[constants.KEY_RESULTS]
    assert len(results) == 1
    assert results[0][constants.KEY_NAME] == constants.KEY_ADDED
    for path in root.glob(test_constants.PATH_PY):
        path.unlink()
    assert engine.index(str(root))[test_constants.KEY_RESULT][constants.KEY_CHUNKS] == 0
    assert engine.search(str(root), "anything")[constants.KEY_RESULTS] == []


def test_restart_recovery_preserves_generations(settings, roots):
    first = Engine(settings, model_factory=FakeModel)
    assert first.index(roots[0])[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED
    generation = first.state.snapshot()[constants.KEY_PROJECTS][roots[0]][constants.KEY_GENERATION]
    with first.state.edit() as value:
        value[constants.KEY_JOBS][test_constants.KEY_CRASHED] = {
            constants.KEY_PROJECT_PATH: roots[0],
            constants.KEY_JOB_ID: "crashed",
            constants.KEY_STATUS: constants.STATUS_RUNNING,
        }
    first.close()
    second = Engine(settings, model_factory=FakeModel, recover=False)
    try:
        assert second.job(roots[0], "crashed")[constants.KEY_STATUS] == constants.STATUS_INTERRUPTED
        assert second.search(roots[0], "alpha")[constants.KEY_GENERATION] == generation
        assert second.index(roots[0])[test_constants.KEY_RESULT][constants.KEY_REUSED_CHUNKS] == 2
    finally:
        second.close()
    stats = offline_stats(settings.root, roots[0])
    assert not stats[constants.KEY_ONLINE]
    assert stats[constants.KEY_PROJECTS][roots[0]][constants.KEY_CHUNKS] == 2


def test_failed_publish_keeps_previous_generation(engine, roots, monkeypatch):
    engine.index(roots[0])
    previous = Generations(engine.settings.root, roots[0]).current()
    (Path(roots[0]) / test_constants.PATH_NEW_PY).write_text("def novel(): return 42\n")
    import code_search_local.storage as storage

    original = storage.atomic_json

    def crash(path, value, **kwargs):
        if path.name == constants.PATH_CURRENT_JSON:
            raise OSError("simulated crash before manifest replacement")
        return original(path, value, **kwargs)

    monkeypatch.setattr(storage, "atomic_json", crash)
    assert engine.index(roots[0])[constants.KEY_STATUS] == constants.STATUS_FAILED
    assert Generations(engine.settings.root, roots[0]).current() == previous
    assert len(engine.search(roots[0], "alpha")[constants.KEY_RESULTS]) == 2


def test_same_project_serialization_and_cancellation(settings, roots):
    entered, release = threading.Event(), threading.Event()

    class SlowModel(FakeModel):
        def encode(self, texts, purpose):
            entered.set()
            assert release.wait(test_constants.THREAD_RELEASE_TIMEOUT_SECONDS)
            return super().encode(texts, purpose)

    engine = Engine(settings, model_factory=SlowModel)
    try:
        first = engine.index(roots[0], wait=False)
        assert entered.wait(test_constants.THREAD_ENTRY_TIMEOUT_SECONDS)
        second = engine.index(roots[0], wait=False)
        assert second[constants.KEY_STATUS] == constants.STATUS_QUEUED
        engine.cancel(roots[0], second[constants.KEY_JOB_ID])
        release.set()
        engine.futures[first[constants.KEY_JOB_ID]].result(10)
        engine.futures[second[constants.KEY_JOB_ID]].result(10)
        assert (
            engine.job(roots[0], first[constants.KEY_JOB_ID])[constants.KEY_STATUS]
            == constants.STATUS_SUCCEEDED
        )
        assert (
            engine.job(roots[0], second[constants.KEY_JOB_ID])[constants.KEY_STATUS]
            == constants.STATUS_CANCELLED
        )
    finally:
        release.set()
        engine.close()


def test_invalid_paths_and_singleton(engine, roots):
    with pytest.raises(RuntimeError, match="already owns"):
        ServiceLock(engine.settings.root)
    with pytest.raises(ValueError, match="absolute"):
        engine.index("relative")
    with pytest.raises(ValueError, match="not a directory"):
        engine.index(roots[0] + "/missing")
    with pytest.raises(KeyError):
        engine.search(roots[0], "test")
    engine.index(roots[0])
    with pytest.raises(ValueError):
        engine.search(roots[0], "", k=0)


def test_patterns_ignore_binary_symlinks(engine, roots):
    root = Path(roots[0])
    (root / test_constants.PATH_CLAUDE_CONTEXT_IGNORE).write_text("alpha.py\n")
    (root / test_constants.PATH_BINARY_PY).write_bytes(b"\0\x00\xff")
    (root / test_constants.PATH_EXTERNAL_PY).symlink_to(
        Path(roots[1]) / test_constants.PATH_BETA_PY
    )
    (root / test_constants.PATH_LOOP).symlink_to(root, target_is_directory=True)
    (root / test_constants.PATH_IGNORED_TXT).write_text("not code")
    result = engine.index(str(root), file_patterns=["*.py"])
    assert result[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED
    assert result[test_constants.KEY_RESULT][constants.KEY_CHUNKS] == 1
    assert result[test_constants.KEY_RESULT][constants.KEY_FILES_SKIPPED] >= 2


def test_model_change_requires_rebuild(settings, roots):
    first = Engine(settings, model_factory=FakeModel)
    first.index(roots[0])
    first.close()
    second = Engine(
        replace(settings, model="different/model"), model_factory=FakeModel, recover=False
    )
    try:
        with pytest.raises(ValueError, match="model changed"):
            second.search(roots[0], "alpha")
        assert second.index(roots[0])[test_constants.KEY_RESULT][constants.KEY_REUSED_CHUNKS] == 0
        assert second.search(roots[0], "alpha")[constants.KEY_RESULTS]
    finally:
        second.close()


def test_clear_and_similar_are_scoped(engine, roots):
    engine.index(roots[0])
    engine.index(roots[1])
    hit = engine.search(roots[0], "alpha")[constants.KEY_RESULTS][0]
    similar = engine.similar(roots[0], hit[constants.KEY_CHUNK_ID])
    assert len(similar[constants.KEY_RESULTS]) == 1
    assert all(
        row[constants.KEY_CHUNK_ID] != hit[constants.KEY_CHUNK_ID]
        for row in similar[constants.KEY_RESULTS]
    )
    with pytest.raises(KeyError):
        engine.similar(roots[0], "missing")
    with pytest.raises(ValueError):
        engine.similar(roots[0], hit[constants.KEY_CHUNK_ID], 0)
    engine.clear(roots[0])
    assert engine.search(roots[0], "alpha")[constants.KEY_RESULTS] == []
    assert engine.search(roots[1], "beta")[constants.KEY_RESULTS]
    assert not engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][
        constants.KEY_WATCH_ENABLED
    ]
    assert engine.index(roots[0])[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED
    assert engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][constants.KEY_WATCH_ENABLED]


def test_queue_bounds_cancellation_and_search_during_update(settings, roots, monkeypatch):
    from code_search_local.storage import Generations

    entered, release = threading.Event(), threading.Event()

    class PausingModel(FakeModel):
        def encode(self, texts, purpose):
            if purpose == constants.KEY_DOCUMENT and any(
                test_constants.VALUE_UPDATED in text for text in texts
            ):
                entered.set()
                assert release.wait(test_constants.THREAD_RELEASE_TIMEOUT_SECONDS)
            return super().encode(texts, purpose)

    engine = Engine(replace(settings, max_pending_jobs=1), model_factory=PausingModel)
    try:
        engine.index(roots[0])
        old = engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][constants.KEY_GENERATION]
        (Path(roots[0]) / test_constants.PATH_ALPHA_PY).write_text("def updated(): return 2\n")
        job = engine.index(roots[0], wait=False)
        assert entered.wait(test_constants.THREAD_ENTRY_TIMEOUT_SECONDS)
        with pytest.raises(RuntimeError, match="queue is full"):
            engine.index(roots[1], wait=False)
        with pytest.raises(RuntimeError, match="indexing"):
            engine.clear(roots[0])
        captured = threading.Event()
        original = Generations.read

        def read(store):
            result = original(store)
            if threading.current_thread().name.startswith("search-fixture"):
                captured.set()
            return result

        monkeypatch.setattr(Generations, "read", read)
        with ThreadPoolExecutor(1, thread_name_prefix="search-fixture") as pool:
            search = pool.submit(engine.search, roots[0], "alpha")
            assert captured.wait(test_constants.THREAD_ENTRY_TIMEOUT_SECONDS)
            release.set()
            assert search.result(10)[constants.KEY_GENERATION] == old
        engine.futures[job[constants.KEY_JOB_ID]].result(10)
        assert (
            engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][constants.KEY_GENERATION]
            != old
        )
        engine.closed = True
        with pytest.raises(RuntimeError, match="stopping"):
            engine.index(roots[0])
        engine.closed = False
    finally:
        release.set()
        engine.close()


def test_running_cancellation_keeps_committed_index(settings, roots):
    entered, release = threading.Event(), threading.Event()

    class Pausing(FakeModel):
        def encode(self, texts, purpose):
            if any(test_constants.VALUE_NEWCODE in text for text in texts):
                entered.set()
                assert release.wait(test_constants.THREAD_RELEASE_TIMEOUT_SECONDS)
            return super().encode(texts, purpose)

    engine = Engine(settings, model_factory=Pausing)
    try:
        engine.index(roots[0])
        before = engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][constants.KEY_GENERATION]
        (Path(roots[0]) / test_constants.PATH_NEW_PY).write_text("def newcode(): return 3\n")
        job = engine.index(roots[0], wait=False)
        assert entered.wait(test_constants.THREAD_ENTRY_TIMEOUT_SECONDS)
        engine.cancel(roots[0], job[constants.KEY_JOB_ID])
        release.set()
        engine.futures[job[constants.KEY_JOB_ID]].result(10)
        assert (
            engine.job(roots[0], job[constants.KEY_JOB_ID])[constants.KEY_STATUS]
            == constants.STATUS_CANCELLED
        )
        assert (
            engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][constants.KEY_GENERATION]
            == before
        )
    finally:
        release.set()
        engine.close()


def test_legacy_backup_and_startup_reconciliation(settings, roots):
    old = settings.root / constants.KEY_PROJECTS / test_constants.PATH_OLD
    old.mkdir(parents=True)
    (old / test_constants.PATH_PROJECT_INFO_JSON).write_text(
        json.dumps({constants.KEY_PROJECT_PATH: roots[0]})
    )
    (old / test_constants.PATH_CODE_INDEX).write_bytes(b"legacy contents")
    bad = settings.root / constants.KEY_PROJECTS / test_constants.PATH_BAD
    bad.mkdir()
    (bad / test_constants.PATH_PROJECT_INFO_JSON).write_text("{")
    missing = settings.root / constants.KEY_PROJECTS / test_constants.PATH_MISSING
    missing.mkdir()
    (missing / test_constants.PATH_PROJECT_INFO_JSON).write_text("{}")
    engine = Engine(settings, model_factory=FakeModel)
    try:
        for future in list(engine.futures.values()):
            future.result(10)
        stats = engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]]
        assert not stats[constants.KEY_NEEDS_REBUILD]
        assert (
            Path(stats[constants.KEY_LEGACY_BACKUP]) / test_constants.PATH_CODE_INDEX
        ).read_bytes() == b"legacy contents"
        assert engine.search(roots[0], "alpha")[constants.KEY_RESULTS]
    finally:
        engine.close()
    engine = Engine(settings, model_factory=FakeModel, recover=False)
    try:
        assert not engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][
            constants.KEY_NEEDS_REBUILD
        ]
    finally:
        engine.close()


def test_watch_detects_updates_and_respects_clear(settings, roots):
    engine = Engine(replace(settings, watch=True), model_factory=FakeModel)
    try:
        engine.index(roots[0])
        (Path(roots[0]) / test_constants.PATH_NEW_PY).write_text("def watched(): return 5\n")
        deadline = time.monotonic() + test_constants.WATCH_RECONCILIATION_TIMEOUT_SECONDS
        while engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][constants.KEY_FILES] != 3:
            assert time.monotonic() < deadline
            time.sleep(test_constants.HEALTH_POLL_SECONDS)
        for future in list(engine.futures.values()):
            future.result(10)
        engine.clear(roots[0])
        assert engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][constants.KEY_FILES] == 0
    finally:
        engine.close()


def test_chunk_races_invalid_encoding_and_embedding_limits(tmp_path):
    import hashlib

    from code_search_local.engine import chunk_file, embedding_text

    path = tmp_path / test_constants.PATH_FILE_PY
    path.write_bytes(b"\xff")
    assert chunk_file(str(tmp_path), "file.py", hashlib.sha256(b"\xff").hexdigest()) == []
    with pytest.raises(RuntimeError, match="changed while indexing"):
        chunk_file(str(tmp_path), "file.py", "wrong")
    assert (
        len(
            embedding_text(
                {
                    constants.KEY_CONTENT: "head" + ("x" * 10000) + "tail",
                    constants.KEY_DOCSTRING: "doc" * 200,
                }
            )
        )
        <= 6000
    )


def test_uncommitted_project_and_bounded_chunk_pipeline(engine, roots):
    engine._register(roots[0])
    with pytest.raises(ValueError, match="no committed index"):
        engine.search(roots[0], "test")
    with pytest.raises(ValueError, match="no committed index"):
        engine.similar(roots[0], "test")
    assert engine.clear(roots[0])[constants.KEY_PROJECTS][roots[0]][constants.KEY_FILES] == 0
    for number in range(8):
        (Path(roots[0]) / f"file{number}.py").write_text(f"def file{number}(): return {number}\n")
    assert engine.index(roots[0])[test_constants.KEY_RESULT][constants.KEY_FILES] == 10
    assert len(engine.search(roots[0], "file", k=1)[constants.KEY_RESULTS]) == 1


def test_failed_stats_persistence_does_not_leave_jobs_hanging(engine, roots, monkeypatch):
    engine.index(roots[0])
    before = engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][constants.KEY_GENERATION]
    (Path(roots[0]) / test_constants.PATH_NEW_PY).write_text("def new(): return 2\n")
    original = engine._build

    def build(*args):
        def fail():
            raise OSError("disk full")

        monkeypatch.setattr(engine.state, "_save", fail)
        return original(*args)

    monkeypatch.setattr(engine, "_build", build)
    with pytest.raises(OSError, match="disk full"):
        engine.index(roots[0])
    assert (
        engine.state.snapshot()[constants.KEY_PROJECTS][roots[0]][constants.KEY_GENERATION]
        == before
    )
    monkeypatch.undo()


def test_watcher_error_reconciles_and_shutdown_does_not_enqueue(engine, roots, monkeypatch):
    import watchfiles

    engine.index(roots[0])
    attempts = []

    def watch(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("watch overflow")
        # Several batches exercise normal continued listening and shutdown delivery.
        yield {(1, str(Path(roots[0]) / test_constants.PATH_ALPHA_PY))}
        engine.closed = True
        yield {(1, str(Path(roots[0]) / test_constants.PATH_ALPHA_PY))}

    monkeypatch.setattr(watchfiles, "watch", watch)
    monkeypatch.setattr(engine.watch_reset, constants.KEY_WAIT, lambda *args: None)
    engine._watch()
    assert len(attempts) == 2
    engine.closed = False


def test_missing_faiss_matches_do_not_return_last_chunk(engine, roots, monkeypatch):
    import numpy as np

    engine.index(roots[0])
    index = engine._store(roots[0]).read()[0]
    monkeypatch.setattr(index, "search", lambda *args: (np.array([[-np.inf]]), np.array([[-1]])))
    assert engine.search(roots[0], "missing")[constants.KEY_RESULTS] == []


def test_startup_failure_releases_singleton(settings, monkeypatch):
    import code_search_local.engine as module

    original = module.State

    def fail(*args, **kwargs):
        raise OSError("storage unavailable")

    monkeypatch.setattr(module, "State", fail)
    with pytest.raises(OSError):
        Engine(settings, model_factory=FakeModel)
    lock = ServiceLock(settings.root)
    lock.close()
    monkeypatch.setattr(module, "State", original)
    monkeypatch.setattr(module, "ModelWorker", fail)
    with pytest.raises(OSError):
        Engine(settings, model_factory=FakeModel)
    lock = ServiceLock(settings.root)
    lock.close()


def test_corrupt_startup_generation_releases_all_owners(tmp_path):
    from code_search_local.storage import Generations, atomic_json

    root = tmp_path / constants.KEY_PROJECT
    root.mkdir()
    (root / test_constants.PATH_A_PY).write_text("def value(): return 1\n")
    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE), watch=False)
    engine = Engine(settings, model_factory=FakeModel)
    engine.index(str(root))
    engine.close()
    store = Generations(settings.root, str(root))
    original = store.manifest.read_bytes()
    atomic_json(store.manifest, {constants.KEY_GENERATION: "../invalid"})
    with pytest.raises(ValueError, match="manifest"):
        Engine(settings, model_factory=FakeModel)
    store.manifest.write_bytes(original)
    engine = Engine(settings, model_factory=FakeModel, recover=False)
    engine.close()
