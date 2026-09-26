"""Base classes and data structures for tree-sitter based code chunking."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

from tree_sitter import Parser

from code_search_local import constants
from code_search_local.chunking.available_languages import get_availiable_language

# map {language: language_obj}
AVAILABLE_LANGUAGES = get_availiable_language()

logger = logging.getLogger(__name__)


@dataclass
class TreeSitterChunk:
    """Represents a code chunk extracted using tree-sitter."""

    content: str
    start_line: int
    end_line: int
    node_type: str
    language: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict:
        """Convert to dictionary format compatible with existing system."""
        return {
            constants.KEY_CONTENT: self.content,
            constants.KEY_START_LINE: self.start_line,
            constants.KEY_END_LINE: self.end_line,
            constants.KEY_TYPE: self.node_type,
            constants.KEY_LANGUAGE: self.language,
            constants.KEY_METADATA: self.metadata,
        }


class LanguageChunker(ABC):
    """Abstract base class for language-specific chunkers."""

    LANGUAGE_NAME = None
    SPLITTABLE_NODE_TYPES = frozenset()

    def __init__(self, language_name: str | None = None):
        """Initialize language chunker.

        Args:
            language_name: Programming language name
        """
        language_name = self.LANGUAGE_NAME if language_name is None else language_name
        self.language_name = language_name
        if language_name not in AVAILABLE_LANGUAGES:
            raise ValueError(
                f"Language {language_name} not available. Install tree-sitter-{language_name}"
            )

        self.language = AVAILABLE_LANGUAGES[language_name]
        self.parser = Parser(self.language)
        self.splittable_node_types = self._get_splittable_node_types()

    def _get_splittable_node_types(self) -> Set[str]:
        """Return a per-parser set from the language's immutable configuration."""
        return set(self.SPLITTABLE_NODE_TYPES)

    @abstractmethod
    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract metadata from a node.

        Args:
            node: Tree-sitter node
            source: Source code bytes

        Returns:
            Metadata dictionary
        """
        pass

    def should_chunk_node(self, node: Any) -> bool:
        """Check if a node should be chunked.

        Args:
            node: Tree-sitter node

        Returns:
            True if node should be chunked
        """
        return node.type in self.splittable_node_types

    def _get_recursable_container_types(self) -> Set[str]:
        """Container node types whose children should still be visited after
        the container itself is chunked, so nested members get their own
        chunks.

        Default: classes (so methods are extracted). Languages with other
        type-bearing containers (e.g. Solidity contracts/libraries) override.
        """
        return {constants.KEY_CLASS_DEFINITION, constants.KEY_CLASS_DECLARATION}

    def _container_parent_info(self, node: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Parent info dict propagated to children of a recursable container."""
        return {
            constants.KEY_PARENT_NAME: metadata.get(constants.KEY_NAME),
            constants.KEY_PARENT_TYPE: metadata.get(constants.KEY_NODE_TYPE, node.type),
        }

    def named_metadata(self, node, source, identifier_types=(constants.SYNTAX_IDENTIFIER,)):
        """Collect the common node type and first declared child name."""
        metadata = {constants.KEY_NODE_TYPE: node.type}
        for child in node.children:
            if child.type in identifier_types:
                metadata[constants.KEY_NAME] = self.get_node_text(child, source)
                break
        return metadata

    def declarator_metadata(self, node, source, identifier_types):
        """Read the first function declarator without confusing its parameter names."""
        metadata = {constants.KEY_NODE_TYPE: node.type}
        for child in node.children:
            if child.type == constants.SYNTAX_FUNCTION_DECLARATOR:
                declaration = self.named_metadata(child, source, identifier_types)
                if constants.KEY_NAME in declaration:
                    metadata[constants.KEY_NAME] = declaration[constants.KEY_NAME]
                break
        return metadata

    @staticmethod
    def has_child_type(node, node_type):
        return any(child.type == node_type for child in node.children)

    def get_node_text(self, node: Any, source: bytes) -> str:
        """Get text content of a node.

        Args:
            node: Tree-sitter node
            source: Source code bytes

        Returns:
            Text content
        """
        return source[node.start_byte : node.end_byte].decode(constants.TEXT_ENCODING)

    def get_line_numbers(self, node: Any) -> Tuple[int, int]:
        """Get start and end line numbers for a node.

        Args:
            node: Tree-sitter node

        Returns:
            Tuple of (start_line, end_line)
        """
        # Tree-sitter uses 0-based indexing, convert to 1-based
        return node.start_point[0] + 1, node.end_point[0] + 1

    def chunk_code(self, source_code: str) -> List[TreeSitterChunk]:
        """Chunk source code into semantic units.

        Args:
            source_code: Source code string

        Returns:
            List of TreeSitterChunk objects
        """
        source_bytes = bytes(source_code, constants.TEXT_ENCODING)
        tree = self.parser.parse(source_bytes)
        chunks = []

        def traverse(node, depth=0, parent_info=None):
            """Recursively traverse the tree and extract chunks."""
            if self.should_chunk_node(node):
                start_line, end_line = self.get_line_numbers(node)
                content = self.get_node_text(node, source_bytes)
                metadata = self.extract_metadata(node, source_bytes)

                # Add parent information if available
                if parent_info:
                    metadata.update(parent_info)

                chunk = TreeSitterChunk(
                    content=content,
                    start_line=start_line,
                    end_line=end_line,
                    node_type=node.type,
                    language=self.language_name,
                    metadata=metadata,
                )
                chunks.append(chunk)

                # For containers (classes by default; contracts/libraries
                # for languages that opt in via _get_recursable_container_types),
                # continue traversing so nested members are chunked too.
                if node.type in self._get_recursable_container_types():
                    container_info = self._container_parent_info(node, metadata)
                    for child in node.children:
                        traverse(child, depth + 1, container_info)
                return

            # Traverse children, passing along parent info
            for child in node.children:
                traverse(child, depth + 1, parent_info)

        traverse(tree.root_node)

        # If no chunks found, create a single module-level chunk
        if not chunks and source_code.strip():
            chunks.append(
                TreeSitterChunk(
                    content=source_code,
                    start_line=1,
                    end_line=len(source_code.split("\n")),
                    node_type=constants.SYNTAX_MODULE,
                    language=self.language_name,
                    metadata={constants.KEY_TYPE: constants.SYNTAX_MODULE},
                )
            )

        return chunks
