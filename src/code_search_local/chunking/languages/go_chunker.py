"""Go-specific tree-sitter based chunker."""

from typing import Any, Dict

from code_search_local import constants
from code_search_local.chunking.base_chunker import LanguageChunker


class GoChunker(LanguageChunker):
    """Go-specific chunker using tree-sitter."""

    LANGUAGE_NAME = constants.LANGUAGE_GO

    SPLITTABLE_NODE_TYPES = frozenset(
        {
            constants.KEY_FUNCTION_DECLARATION,
            constants.KEY_METHOD_DECLARATION,
            constants.KEY_TYPE_DECLARATION,
            constants.KEY_INTERFACE_DECLARATION,
            constants.KEY_STRUCT_DECLARATION,
        }
    )

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract Go-specific metadata."""
        metadata = self.named_metadata(node, source)

        # For methods, extract receiver type
        if node.type == constants.KEY_METHOD_DECLARATION:
            for child in node.children:
                if child.type == constants.SYNTAX_PARAMETER_LIST:
                    # First parameter_list is the receiver
                    for receiver_child in child.children:
                        if receiver_child.type == constants.SYNTAX_PARAMETER_DECLARATION:
                            for param_child in receiver_child.children:
                                if param_child.type in [
                                    constants.SYNTAX_IDENTIFIER,
                                    constants.SYNTAX_POINTER_TYPE,
                                    constants.SYNTAX_TYPE_IDENTIFIER,
                                ]:
                                    metadata[constants.KEY_RECEIVER_TYPE] = self.get_node_text(
                                        param_child, source
                                    )
                                    break
                            break
                    break

        return metadata
