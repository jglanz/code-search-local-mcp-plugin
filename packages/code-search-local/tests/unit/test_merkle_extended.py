import json

from code_search_local import constants
from code_search_local.merkle import ChangeDetector, MerkleDAG, SnapshotManager
from code_search_local.merkle.change_detector import FileChanges
from tests import constants as test_constants


def test_snapshot_errors_age_cleanup_and_change_analysis(tmp_path):
    root = tmp_path / constants.KEY_ROOT
    root.mkdir()
    (root / test_constants.PATH_CODE_PY).write_text("one")
    manager = SnapshotManager()
    assert manager.load_metadata(str(root)) is None
    assert manager.get_snapshot_age(str(root)) is None
    manager.delete_snapshot(str(root))
    dag = MerkleDAG(str(root))
    dag.build()
    manager.save_snapshot(dag)
    assert manager.get_snapshot_age(str(root)) >= 0
    path = manager.get_snapshot_path(str(root))
    value = json.loads(path.read_text())
    value[constants.KEY_VERSION] = "future"
    path.write_text(json.dumps(value))
    assert manager.load_snapshot(str(root)) is not None
    path.write_text("bad json")
    assert manager.load_snapshot(str(root)) is None
    manager.get_metadata_path(str(root)).write_text("bad json")
    assert manager.load_metadata(str(root)) is None
    assert manager.list_snapshots() == []
    manager.save_snapshot(dag)
    manager.cleanup_old_snapshots(keep_count=1)
    assert manager.has_snapshot(str(root))
    manager.cleanup_old_snapshots(keep_count=0)
    assert not manager.has_snapshot(str(root))
    manager.save_snapshot(dag)
    manager.delete_snapshot(str(root))
    detector = ChangeDetector(manager)
    changes = FileChanges(["a.py", "folder/b.js"], ["old"], ["a.py"], [])
    assert changes.total_changed() == 4
    analysis = detector.analyze_change_patterns(changes)
    assert analysis[constants.KEY_FILE_EXTENSIONS] == {
        test_constants.KEY_PY: 2,
        test_constants.KEY_JS: 1,
        constants.KEY_NO_EXTENSION: 1,
    }
    assert analysis[constants.KEY_DIRECTORIES][constants.KEY_ROOT] == 3
    (root / test_constants.VALUE_NESTED).mkdir()
    (root / test_constants.VALUE_NESTED / test_constants.PATH_X_PY).write_text("two")
    newer = MerkleDAG(str(root))
    newer.build()
    assert test_constants.VALUE_NESTED in detector.get_changed_directories(dag, newer)


def test_snapshot_inside_project_and_dag_edge_cases(tmp_path, monkeypatch):
    root = tmp_path / constants.KEY_ROOT
    root.mkdir()
    (root / test_constants.PATH_CODE_PY).write_text("one")
    manager = SnapshotManager(root / test_constants.PATH_SNAPSHOTS)
    detector = ChangeDetector(manager)
    changes, dag = detector.detect_changes_from_snapshot(str(root))
    assert changes.added == ["code.py"]
    manager.save_snapshot(dag)
    assert not detector.quick_check(str(root))
    monkeypatch.setenv(constants.ENV_CODE_SEARCH_MAX_FILE_BYTES, "invalid")
    assert MerkleDAG(str(root)).max_file_bytes > 0
    empty = MerkleDAG(str(tmp_path / test_constants.PATH_MISSING))
    assert empty.get_stats()[constants.KEY_FILE_COUNT] == 0
    empty.build()
    assert empty.get_root_hash() is None
    no_root = dag.to_dict()
    no_root[constants.KEY_ROOT_NODE] = None
    assert MerkleDAG.from_dict(no_root).root_node is None
    (root / test_constants.VALUE_BIG_PY).write_bytes(b"x" * 30)
    limited = MerkleDAG(str(root), max_file_bytes=2)
    limited.build()
    assert test_constants.VALUE_BIG_PY not in limited.get_all_files()
    (root / test_constants.PATH_CLAUDE_CONTEXT_IGNORE).write_text("nested/\n")
    assert MerkleDAG(str(root)).should_ignore(root / test_constants.VALUE_NESTED) is False
