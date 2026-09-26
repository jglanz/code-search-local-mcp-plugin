"""TypeScript-specific tree-sitter based chunker."""

from typing import Any, Dict, Set

from code_search_local import constants

from .javascript_chunker import JavaScriptChunker


class TypeScriptChunker(JavaScriptChunker):
    """TypeScript-specific chunker using tree-sitter."""

    def __init__(self, use_tsx: bool = False):
        super().__init__(constants.LANGUAGE_TSX if use_tsx else constants.LANGUAGE_TYPESCRIPT)
        self.use_tsx = use_tsx

    def _get_splittable_node_types(self) -> Set[str]:
        """TypeScript-specific splittable node types."""
        return super()._get_splittable_node_types() | {
            constants.KEY_INTERFACE_DECLARATION,
            constants.KEY_TYPE_ALIAS_DECLARATION,
            constants.KEY_ENUM_DECLARATION,
        }

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract TypeScript-specific metadata."""
        metadata = self.named_metadata(
            node, source, (constants.SYNTAX_IDENTIFIER, constants.SYNTAX_TYPE_IDENTIFIER)
        )

        # Check for async
        if node.children and self.get_node_text(node.children[0], source) == constants.SYNTAX_ASYNC:
            metadata[constants.KEY_IS_ASYNC] = True

        # Check for export
        if (
            node.children
            and self.get_node_text(node.children[0], source) == constants.SYNTAX_EXPORT
        ):
            metadata[constants.KEY_IS_EXPORT] = True

        # Check for generic parameters
        if self.has_child_type(node, constants.SYNTAX_TYPE_PARAMETERS):
            metadata[constants.KEY_HAS_GENERICS] = True

        return metadata
