"""Merkle tree-based change detection for efficient incremental indexing."""

from code_search_local.merkle.change_detector import ChangeDetector
from code_search_local.merkle.merkle_dag import MerkleDAG, MerkleNode
from code_search_local.merkle.snapshot_manager import SnapshotManager

__all__ = ["MerkleNode", "MerkleDAG", "SnapshotManager", "ChangeDetector"]
