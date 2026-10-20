"""Unit tests for MerkleNode class."""

from unittest import TestCase

from code_search_local import constants
from code_search_local.merkle.merkle_dag import MerkleNode
from tests import constants as test_constants


class TestMerkleNode(TestCase):
    """Test MerkleNode class."""

    def test_node_creation(self):
        """Test creating a Merkle node."""
        node = MerkleNode(path="test.py", hash="abc123", is_file=True, size=100)

        assert node.path == test_constants.VALUE_TEST_PY
        assert node.hash == test_constants.VALUE_ABC123
        assert node.is_file is True
        assert node.size == 100
        assert len(node.children) == 0

    def test_node_serialization(self):
        """Test node to/from dict conversion."""
        # Create parent with children
        child1 = MerkleNode("child1.py", "hash1", True, 50)
        child2 = MerkleNode("child2.py", "hash2", True, 75)
        parent = MerkleNode("parent", "parent_hash", False, 0)
        parent.children = [child1, child2]

        # Serialize
        data = parent.to_dict()

        # Verify structure
        assert data[constants.KEY_PATH] == test_constants.VALUE_PARENT
        assert data[constants.KEY_HASH] == test_constants.VALUE_PARENT_HASH
        assert data[constants.KEY_IS_FILE] is False
        assert len(data[constants.KEY_CHILDREN]) == 2

        # Deserialize
        restored = MerkleNode.from_dict(data)

        # Verify restoration
        assert restored.path == parent.path
        assert restored.hash == parent.hash
        assert len(restored.children) == 2
        assert restored.children[0].path == test_constants.VALUE_CHILD1_PY
        assert restored.children[1].path == test_constants.VALUE_CHILD2_PY
