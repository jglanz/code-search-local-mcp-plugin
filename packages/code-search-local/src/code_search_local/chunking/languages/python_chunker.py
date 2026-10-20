"""Python-specific tree-sitter based chunker."""

import ast
from typing import Any, Dict, Optional

from code_search_local import constants
from code_search_local.chunking.base_chunker import LanguageChunker


class PythonChunker(LanguageChunker):
    """Python-specific chunker using tree-sitter."""

    LANGUAGE_NAME = constants.KEY_PYTHON

    SPLITTABLE_NODE_TYPES = frozenset(
        {
            constants.KEY_FUNCTION_DEFINITION,
            constants.KEY_CLASS_DEFINITION,
            constants.SYNTAX_DECORATED_DEFINITION,
        }
    )

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract Python-specific metadata."""
        metadata = self.named_metadata(node, source)

        # Extract decorators if present
        if node.type == constants.SYNTAX_DECORATED_DEFINITION:
            decorators = []
            for child in node.children:
                if child.type == constants.SYNTAX_DECORATOR:
                    decorators.append(self.get_node_text(child, source))
            metadata[constants.KEY_DECORATORS] = decorators

            # Get the actual definition node
            for child in node.children:
                if child.type in [
                    constants.KEY_FUNCTION_DEFINITION,
                    constants.KEY_CLASS_DEFINITION,
                ]:
                    # Get name from the actual definition
                    for subchild in child.children:
                        if subchild.type == constants.SYNTAX_IDENTIFIER:
                            metadata[constants.KEY_NAME] = self.get_node_text(subchild, source)
                            break

        # Extract docstring for functions and classes
        docstring = self._extract_docstring(node, source)
        if docstring:
            metadata[constants.KEY_DOCSTRING] = docstring

        # Count parameters for functions
        if node.type == constants.KEY_FUNCTION_DEFINITION or (
            node.type == constants.SYNTAX_DECORATED_DEFINITION
            and any(c.type == constants.KEY_FUNCTION_DEFINITION for c in node.children)
        ):
            definition = node.child_by_field_name(constants.SYNTAX_DEFINITION) or node
            for child in definition.children:
                if child.type == constants.SYNTAX_PARAMETERS:
                    # Count parameter nodes
                    param_count = sum(
                        1
                        for c in child.children
                        if c.type
                        in [
                            constants.SYNTAX_IDENTIFIER,
                            constants.SYNTAX_TYPED_PARAMETER,
                            constants.SYNTAX_DEFAULT_PARAMETER,
                        ]
                    )
                    metadata[constants.KEY_PARAM_COUNT] = param_count
                    break

        return metadata

    def _extract_docstring(self, node: Any, source: bytes) -> Optional[str]:
        """Extract docstring from function or class definition."""
        # Find the body/block of the function or class
        body_node = None
        for child in node.children:
            if child.type == constants.SYNTAX_BLOCK:
                body_node = child
                break
            elif child.type in [constants.KEY_FUNCTION_DEFINITION, constants.KEY_CLASS_DEFINITION]:
                # Handle decorated definitions
                for subchild in child.children:
                    if subchild.type == constants.SYNTAX_BLOCK:
                        body_node = subchild
                        break

        if not body_node or not body_node.children:
            return None

        # New grammars expose a string directly; older versions wrap expressions.
        first = body_node.children[0]
        candidates = (
            first.children if first.type == constants.SYNTAX_EXPRESSION_STATEMENT else [first]
        )
        for child in candidates:
            if child.type == constants.SYNTAX_STRING:
                try:
                    value = ast.literal_eval(self.get_node_text(child, source))
                except (SyntaxError, ValueError):
                    return None
                return value.strip() if isinstance(value, str) else None
        return None
