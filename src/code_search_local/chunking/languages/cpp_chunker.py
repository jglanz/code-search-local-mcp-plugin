"""C++-specific tree-sitter based chunker."""

from typing import Any, Dict

from code_search_local import constants
from code_search_local.chunking.base_chunker import LanguageChunker


class CppChunker(LanguageChunker):
    """C++-specific chunker using tree-sitter."""

    LANGUAGE_NAME = constants.LANGUAGE_CPP

    SPLITTABLE_NODE_TYPES = frozenset(
        {
            constants.KEY_FUNCTION_DEFINITION,
            constants.KEY_CLASS_SPECIFIER,
            constants.KEY_STRUCT_SPECIFIER,
            constants.KEY_UNION_SPECIFIER,
            constants.KEY_ENUM_SPECIFIER,
            constants.KEY_NAMESPACE_DEFINITION,
            constants.KEY_TEMPLATE_DECLARATION,
            constants.KEY_CONCEPT_DEFINITION,
        }
    )

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract C++-specific metadata."""
        metadata = {constants.KEY_NODE_TYPE: node.type}

        # Extract name
        if node.type == constants.KEY_FUNCTION_DEFINITION:
            metadata = self.declarator_metadata(
                node, source, (constants.SYNTAX_IDENTIFIER, constants.SYNTAX_QUALIFIED_IDENTIFIER)
            )

        elif node.type in [
            constants.KEY_CLASS_SPECIFIER,
            constants.KEY_STRUCT_SPECIFIER,
            constants.KEY_NAMESPACE_DEFINITION,
        ]:
            metadata = self.named_metadata(
                node,
                source,
                [
                    constants.SYNTAX_TYPE_IDENTIFIER,
                    constants.SYNTAX_IDENTIFIER,
                    constants.SYNTAX_NAMESPACE_IDENTIFIER,
                ],
            )

        # Check for template parameters
        if node.type == constants.KEY_TEMPLATE_DECLARATION:
            metadata[constants.KEY_IS_TEMPLATE] = True
            # Get the templated entity name
            for child in node.children:
                if child.type in [constants.KEY_FUNCTION_DEFINITION, constants.KEY_CLASS_SPECIFIER]:
                    child_metadata = self.extract_metadata(child, source)
                    if constants.KEY_NAME in child_metadata:
                        metadata[constants.KEY_NAME] = child_metadata[constants.KEY_NAME]
                    break

        return metadata
