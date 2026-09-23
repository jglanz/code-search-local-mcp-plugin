import json

from code_search_local.merkle import ChangeDetector, MerkleDAG, SnapshotManager
from code_search_local.merkle.change_detector import FileChanges


def test_snapshot_errors_age_cleanup_and_change_analysis(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "code.py").write_text("one")
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
    value["version"] = "future"
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
    assert analysis["file_extensions"] == {".py": 2, ".js": 1, "no_extension": 1}
    assert analysis["directories"]["root"] == 3
    (root / "nested").mkdir()
    (root / "nested" / "x.py").write_text("two")
    newer = MerkleDAG(str(root))
    newer.build()
    assert "nested" in detector.get_changed_directories(dag, newer)


def test_snapshot_inside_project_and_dag_edge_cases(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "code.py").write_text("one")
    manager = SnapshotManager(root / "snapshots")
    detector = ChangeDetector(manager)
    changes, dag = detector.detect_changes_from_snapshot(str(root))
    assert changes.added == ["code.py"]
    manager.save_snapshot(dag)
    assert not detector.quick_check(str(root))
    monkeypatch.setenv("CODE_SEARCH_MAX_FILE_BYTES", "invalid")
    assert MerkleDAG(str(root)).max_file_bytes > 0
    empty = MerkleDAG(str(tmp_path / "missing"))
    assert empty.get_stats()["file_count"] == 0
    empty.build()
    assert empty.get_root_hash() is None
    no_root = dag.to_dict()
    no_root["root_node"] = None
    assert MerkleDAG.from_dict(no_root).root_node is None
    (root / "big.py").write_bytes(b"x" * 30)
    limited = MerkleDAG(str(root), max_file_bytes=2)
    limited.build()
    assert "big.py" not in limited.get_all_files()
    (root / ".claude-context-ignore").write_text("nested/\n")
    assert MerkleDAG(str(root)).should_ignore(root / "nested") is False
