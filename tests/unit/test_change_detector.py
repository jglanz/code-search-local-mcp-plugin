"""Unit tests for ChangeDetector class."""

import shutil
import tempfile
from pathlib import Path
from unittest import TestCase

from code_search_local.merkle.change_detector import ChangeDetector, FileChanges
from code_search_local.merkle.merkle_dag import MerkleDAG
from code_search_local.merkle.snapshot_manager import SnapshotManager
from tests import constants as test_constants


class TestChangeDetector(TestCase):
    """Test ChangeDetector class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_path = Path(self.temp_dir)

        self.storage_dir = Path(self.temp_dir) / test_constants.PATH_SNAPSHOTS
        self.snapshot_manager = SnapshotManager(self.storage_dir)
        self.detector = ChangeDetector(self.snapshot_manager)

        self.create_initial_files()

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_initial_files(self):
        """Create initial file structure."""
        (self.test_path / test_constants.PATH_SRC).mkdir()
        (self.test_path / test_constants.VALUE_UNCHANGED_PY).write_text("# unchanged")
        (self.test_path / test_constants.VALUE_TO_MODIFY_PY).write_text("# original")
        (self.test_path / test_constants.VALUE_TO_REMOVE_PY).write_text("# remove me")
        (self.test_path / test_constants.PATH_SRC / test_constants.PATH_MODULE_PY).write_text(
            "# module"
        )

    def test_detect_changes_between_dags(self):
        """Test detecting changes between two DAGs."""
        # Create initial DAG
        dag1 = MerkleDAG(str(self.test_path))
        dag1.build()

        # Modify files
        (self.test_path / test_constants.VALUE_TO_MODIFY_PY).write_text("# modified")
        (self.test_path / test_constants.VALUE_TO_REMOVE_PY).unlink()
        (self.test_path / test_constants.VALUE_ADDED_PY).write_text("# new file")

        # Create new DAG
        dag2 = MerkleDAG(str(self.test_path))
        dag2.build()

        # Detect changes
        changes = self.detector.detect_changes(dag1, dag2)

        assert test_constants.VALUE_ADDED_PY in changes.added
        assert test_constants.VALUE_TO_REMOVE_PY in changes.removed
        assert test_constants.VALUE_TO_MODIFY_PY in changes.modified
        assert test_constants.VALUE_UNCHANGED_PY in changes.unchanged
        assert "src/module.py" in changes.unchanged

        assert changes.has_changes()
        assert changes.total_changed() == 3

    def test_detect_changes_from_snapshot(self):
        """Test detecting changes from saved snapshot."""
        # Create and save initial snapshot
        dag1 = MerkleDAG(str(self.test_path))
        dag1.build()
        self.snapshot_manager.save_snapshot(dag1)

        # Modify files
        (self.test_path / test_constants.VALUE_TO_MODIFY_PY).write_text("# modified content")
        (self.test_path / test_constants.VALUE_NEW_FILE_PY).write_text("# new")

        # Detect changes from snapshot
        changes, current_dag = self.detector.detect_changes_from_snapshot(str(self.test_path))

        assert test_constants.VALUE_NEW_FILE_PY in changes.added
        assert test_constants.VALUE_TO_MODIFY_PY in changes.modified
        assert len(changes.removed) == 0
        assert changes.has_changes()

    def test_no_changes_detection(self):
        """Test when no changes occur."""
        dag1 = MerkleDAG(str(self.test_path))
        dag1.build()

        dag2 = MerkleDAG(str(self.test_path))
        dag2.build()

        changes = self.detector.detect_changes(dag1, dag2)

        assert not changes.has_changes()
        assert changes.total_changed() == 0
        assert len(changes.unchanged) == 4

    def test_quick_check(self):
        """Test quick change detection."""
        # No snapshot exists - should return True
        assert self.detector.quick_check(str(self.test_path))

        # Save snapshot - excluding snapshots directory
        dag = MerkleDAG(str(self.test_path))
        dag.ignore_patterns.add("snapshots")  # Ignore the snapshots directory
        dag.build()
        self.snapshot_manager.save_snapshot(dag)

        # No changes - should return False
        assert not self.detector.quick_check(str(self.test_path))

        # Make a change
        (self.test_path / test_constants.VALUE_TO_MODIFY_PY).write_text("# changed")

        # Should detect change
        assert self.detector.quick_check(str(self.test_path))

    def test_files_to_reindex(self):
        """Test getting files that need reindexing."""
        changes = FileChanges(
            added=["new1.py", "new2.py"],
            removed=["old.py"],
            modified=["changed.py"],
            unchanged=["same.py"],
        )

        files_to_reindex = self.detector.get_files_to_reindex(changes)

        assert len(files_to_reindex) == 3
        assert test_constants.VALUE_NEW1_PY in files_to_reindex
        assert test_constants.VALUE_NEW2_PY in files_to_reindex
        assert test_constants.VALUE_CHANGED_PY in files_to_reindex
        assert test_constants.PATH_OLD_PY not in files_to_reindex

    def test_files_to_remove(self):
        """Test getting files to remove from index."""
        changes = FileChanges(
            added=["new.py"], removed=["deleted.py"], modified=["changed.py"], unchanged=["same.py"]
        )

        files_to_remove = self.detector.get_files_to_remove(changes)

        assert len(files_to_remove) == 2
        assert test_constants.VALUE_DELETED_PY in files_to_remove
        assert (
            test_constants.VALUE_CHANGED_PY in files_to_remove
        )  # Modified files need old chunks removed
        assert test_constants.PATH_NEW_PY not in files_to_remove
