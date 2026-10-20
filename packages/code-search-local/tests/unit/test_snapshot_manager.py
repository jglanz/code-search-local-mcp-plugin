"""Unit tests for SnapshotManager class."""

import shutil
import tempfile
from pathlib import Path
from unittest import TestCase

from code_search_local import constants
from code_search_local.merkle.merkle_dag import MerkleDAG
from code_search_local.merkle.snapshot_manager import SnapshotManager
from tests import constants as test_constants


class TestSnapshotManager(TestCase):
    """Test SnapshotManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_path = Path(self.temp_dir) / constants.KEY_PROJECT
        self.test_path.mkdir()

        self.storage_dir = Path(self.temp_dir) / test_constants.PATH_SNAPSHOTS
        self.manager = SnapshotManager(self.storage_dir)

        # Create test files
        (self.test_path / test_constants.VALUE_TEST_PY).write_text('print("test")')

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_project_id_generation(self):
        """Test project ID generation."""
        id1 = self.manager.get_project_id("/path/to/project")
        id2 = self.manager.get_project_id("/path/to/project")
        id3 = self.manager.get_project_id("/different/path")

        # Same path should produce same ID
        assert id1 == id2

        # Different path should produce different ID
        assert id1 != id3

    def test_save_and_load_snapshot(self):
        """Test saving and loading snapshots."""
        # Create DAG
        dag = MerkleDAG(str(self.test_path))
        dag.build()

        # Save snapshot
        self.manager.save_snapshot(dag, {test_constants.KEY_TEST: constants.KEY_METADATA})

        # Load snapshot
        loaded_dag = self.manager.load_snapshot(str(self.test_path))

        assert loaded_dag is not None
        assert loaded_dag.get_root_hash() == dag.get_root_hash()
        assert loaded_dag.get_all_files() == dag.get_all_files()

    def test_metadata_handling(self):
        """Test metadata save and load."""
        dag = MerkleDAG(str(self.test_path))
        dag.build()

        # Save with metadata
        custom_metadata = {
            constants.KEY_VERSION: constants.SNAPSHOT_FORMAT_VERSION,
            test_constants.KEY_AUTHOR: "test",
        }
        self.manager.save_snapshot(dag, custom_metadata)

        # Load metadata
        metadata = self.manager.load_metadata(str(self.test_path))

        assert metadata is not None
        assert metadata[constants.KEY_VERSION] == constants.SNAPSHOT_FORMAT_VERSION
        assert metadata[test_constants.KEY_AUTHOR] == test_constants.KEY_TEST
        assert metadata[constants.KEY_PROJECT_PATH] == str(self.test_path)
        assert metadata[constants.KEY_FILE_COUNT] == 1

    def test_snapshot_existence_check(self):
        """Test checking if snapshot exists."""
        assert not self.manager.has_snapshot(str(self.test_path))

        dag = MerkleDAG(str(self.test_path))
        dag.build()
        self.manager.save_snapshot(dag)

        assert self.manager.has_snapshot(str(self.test_path))

    def test_list_snapshots(self):
        """Test listing all snapshots."""
        import time

        # Create multiple project snapshots
        for i in range(3):
            project_path = self.test_path.parent / f"project{i}"
            project_path.mkdir()
            (project_path / test_constants.PATH_FILE_TXT).write_text(f"content{i}")

            dag = MerkleDAG(str(project_path))
            dag.build()
            self.manager.save_snapshot(dag)

            time.sleep(
                test_constants.SNAPSHOT_TIMESTAMP_DELAY_SECONDS
            )  # Ensure different timestamps

        snapshots = self.manager.list_snapshots()

        assert len(snapshots) == 3
        # Should be sorted by timestamp (most recent first)
        assert test_constants.VALUE_PROJECT2 in snapshots[0][constants.KEY_PROJECT_PATH]
