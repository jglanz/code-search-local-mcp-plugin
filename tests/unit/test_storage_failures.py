import sqlite3

import numpy as np
import pytest

from code_search_local.storage import Generations, ServiceLock, State, atomic_json


def test_state_rolls_back_failed_edits(tmp_path):
    state = State(tmp_path)
    before = state.snapshot()
    with pytest.raises(ValueError):
        with state.edit() as value:
            value["shared"]["incorrect"] = 1
            raise ValueError("transaction failed")
    assert state.snapshot() == before
    state.close()
    lock = ServiceLock(tmp_path)
    lock.close()
    lock.close()


def test_rejects_invalid_manifest_and_inconsistent_generation(tmp_path):
    store = Generations(tmp_path, "project")
    atomic_json(store.manifest, {"generation": "../outside"})
    with pytest.raises(ValueError, match="manifest"):
        store.read()
    store.manifest.unlink()
    store.publish([{"name": "one"}], np.ones((1, 4), dtype=np.float32), {}, {}, {})
    current = store.current()
    db = sqlite3.connect(current / "chunks.sqlite3")
    db.execute("DELETE FROM chunks")
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="inconsistent"):
        store.read()


def test_generation_retention_does_not_remove_live_reader_snapshot(tmp_path):
    store = Generations(tmp_path, "project")
    for value in range(3):
        store.publish([{"name": str(value)}], np.ones((1, 4), dtype=np.float32), {}, {}, {})
        if value == 0:
            original = store.read()
    assert len(list(store.root.glob("gen-*"))) == 2
    assert original[1][0]["name"] == "0"
    assert store.read()[1][0]["name"] == "2"


def test_failed_reclamation_keeps_successful_commit(tmp_path, monkeypatch):
    from code_search_local import storage

    store = Generations(tmp_path, "project")
    for value in range(2):
        store.publish([{"name": str(value)}], np.ones((1, 4), dtype=np.float32), {}, {}, {})

    def fail(path):
        raise PermissionError("cannot remove old generation")

    monkeypatch.setattr(storage.shutil, "rmtree", fail)
    store.publish([{"name": "new"}], np.ones((1, 4), dtype=np.float32), {}, {}, {})
    assert store.read()[1][0]["name"] == "new"
