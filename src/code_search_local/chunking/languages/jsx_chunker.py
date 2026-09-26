"""JSX-specific tree-sitter based chunker."""

from typing import Any, Dict, Set

from code_search_local import constants
from code_search_local.chunking.languages.javascript_chunker import JavaScriptChunker


class JSXChunker(JavaScriptChunker):
    """JSX-specific chunker (extends JavaScript chunker)."""

    def __init__(self):
        # JSX uses the JavaScript parser
        super().__init__()

    def _get_splittable_node_types(self) -> Set[str]:
        """JSX-specific splittable node types."""
        types = super()._get_splittable_node_types()
        # Add JSX-specific patterns
        types.add(constants.SYNTAX_JSX_ELEMENT)
        types.add(constants.SYNTAX_JSX_SELF_CLOSING_ELEMENT)
        return types

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract JSX-specific metadata."""
        metadata = super().extract_metadata(node, source)

        # Check if it's a React component (function returning JSX)
        if node.type in [
            constants.KEY_FUNCTION_DECLARATION,
            constants.KEY_ARROW_FUNCTION,
            constants.KEY_FUNCTION,
        ]:
            # Simple heuristic: check if body contains JSX
            body_text = self.get_node_text(node, source)
            if "<" in body_text and (
                constants.LANGUAGE_JSX in body_text.lower() or constants.SYNTAX_RETURN in body_text
            ):
                metadata[constants.KEY_IS_COMPONENT] = True

        return metadata
