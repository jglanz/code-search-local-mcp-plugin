"""Rust-specific tree-sitter based chunker."""

from typing import Any, Dict

from code_search_local import constants
from code_search_local.chunking.base_chunker import LanguageChunker


class RustChunker(LanguageChunker):
    """Rust-specific chunker using tree-sitter."""

    LANGUAGE_NAME = constants.LANGUAGE_RUST

    SPLITTABLE_NODE_TYPES = frozenset(
        {
            constants.KEY_FUNCTION_ITEM,
            constants.KEY_IMPL_ITEM,
            constants.KEY_STRUCT_ITEM,
            constants.KEY_ENUM_ITEM,
            constants.KEY_TRAIT_ITEM,
            constants.KEY_MOD_ITEM,
            constants.KEY_MACRO_DEFINITION,
        }
    )

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract Rust-specific metadata."""
        metadata = self.named_metadata(
            node, source, (constants.SYNTAX_IDENTIFIER, constants.SYNTAX_TYPE_IDENTIFIER)
        )

        # Check for async functions
        if node.type == constants.KEY_FUNCTION_ITEM:
            for child in node.children:
                if (
                    child.type == constants.SYNTAX_ASYNC
                    or self.get_node_text(child, source) == constants.SYNTAX_ASYNC
                ):
                    metadata[constants.KEY_IS_ASYNC] = True
                    break

        # Extract impl type for impl blocks
        if node.type == constants.KEY_IMPL_ITEM:
            for child in node.children:
                if child.type in [constants.SYNTAX_TYPE_IDENTIFIER, constants.SYNTAX_GENERIC_TYPE]:
                    metadata[constants.KEY_IMPL_TYPE] = self.get_node_text(child, source)
                    break

        return metadata
