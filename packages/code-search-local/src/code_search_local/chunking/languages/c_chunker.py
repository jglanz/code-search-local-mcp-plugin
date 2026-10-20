"""C-specific tree-sitter based chunker."""

from typing import Any, Dict

from code_search_local import constants
from code_search_local.chunking.base_chunker import LanguageChunker


class CChunker(LanguageChunker):
    """C-specific chunker using tree-sitter."""

    LANGUAGE_NAME = constants.LANGUAGE_C

    SPLITTABLE_NODE_TYPES = frozenset(
        {
            constants.KEY_FUNCTION_DEFINITION,
            constants.KEY_STRUCT_SPECIFIER,
            constants.KEY_UNION_SPECIFIER,
            constants.KEY_ENUM_SPECIFIER,
            constants.SYNTAX_TYPE_DEFINITION,
        }
    )

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract C-specific metadata."""
        metadata = {constants.KEY_NODE_TYPE: node.type}

        # Extract function name
        if node.type == constants.KEY_FUNCTION_DEFINITION:
            metadata = self.declarator_metadata(node, source, (constants.SYNTAX_IDENTIFIER,))

        # Extract struct/union/enum name
        elif node.type in [
            constants.KEY_STRUCT_SPECIFIER,
            constants.KEY_UNION_SPECIFIER,
            constants.KEY_ENUM_SPECIFIER,
        ]:
            metadata = self.named_metadata(
                node, source, [constants.SYNTAX_TYPE_IDENTIFIER, constants.SYNTAX_IDENTIFIER]
            )

        # Extract typedef name
        elif node.type == constants.SYNTAX_TYPE_DEFINITION:
            # Look for the last identifier which is the new type name
            identifiers = []
            for child in node.children:
                if child.type == constants.SYNTAX_IDENTIFIER:
                    identifiers.append(self.get_node_text(child, source))
            if identifiers:
                metadata[constants.KEY_NAME] = identifiers[-1]

        return metadata
