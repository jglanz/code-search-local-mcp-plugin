"""JavaScript-specific tree-sitter based chunker."""

from typing import Any, Dict

from code_search_local import constants
from code_search_local.chunking.base_chunker import LanguageChunker


class JavaScriptChunker(LanguageChunker):
    """JavaScript-specific chunker using tree-sitter."""

    LANGUAGE_NAME = constants.LANGUAGE_JAVASCRIPT

    SPLITTABLE_NODE_TYPES = frozenset(
        {
            constants.KEY_FUNCTION_DECLARATION,
            constants.KEY_FUNCTION,
            constants.KEY_ARROW_FUNCTION,
            constants.KEY_CLASS_DECLARATION,
            constants.KEY_METHOD_DEFINITION,
            constants.SYNTAX_GENERATOR_FUNCTION,
            constants.SYNTAX_GENERATOR_FUNCTION_DECLARATION,
        }
    )

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract JavaScript-specific metadata."""
        metadata = {constants.KEY_NODE_TYPE: node.type}

        name = node.child_by_field_name(constants.KEY_NAME)
        if name is None and node.type in (constants.KEY_ARROW_FUNCTION, constants.KEY_FUNCTION):
            parent = node.parent
            if parent is not None and parent.type in (
                constants.SYNTAX_VARIABLE_DECLARATOR,
                constants.SYNTAX_PAIR,
            ):
                name = parent.child_by_field_name(constants.KEY_NAME) or parent.child_by_field_name(
                    constants.SYNTAX_KEY
                )
        if name is not None:
            metadata[constants.KEY_NAME] = self.get_node_text(name, source)

        # Check for async
        if node.children and self.get_node_text(node.children[0], source) == constants.SYNTAX_ASYNC:
            metadata[constants.KEY_IS_ASYNC] = True

        # Check for generator
        if constants.SYNTAX_GENERATOR in node.type:
            metadata[constants.KEY_IS_GENERATOR] = True

        return metadata
