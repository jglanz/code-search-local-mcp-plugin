"""Java-specific tree-sitter based chunker."""

from typing import Any, Dict

from code_search_local import constants
from code_search_local.chunking.base_chunker import LanguageChunker


class JavaChunker(LanguageChunker):
    """Java-specific chunker using tree-sitter."""

    LANGUAGE_NAME = constants.LANGUAGE_JAVA

    SPLITTABLE_NODE_TYPES = frozenset(
        {
            constants.KEY_METHOD_DECLARATION,
            constants.KEY_CONSTRUCTOR_DECLARATION,
            constants.KEY_CLASS_DECLARATION,
            constants.KEY_INTERFACE_DECLARATION,
            constants.KEY_ENUM_DECLARATION,
            constants.KEY_ANNOTATION_TYPE_DECLARATION,
        }
    )

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract Java-specific metadata."""
        metadata = self.named_metadata(node, source)

        # Extract access modifiers
        modifiers = []
        for child in node.children:
            if child.type == constants.KEY_MODIFIERS:
                for modifier in child.children:
                    if modifier.type in [
                        constants.SYNTAX_PUBLIC,
                        constants.SYNTAX_PRIVATE,
                        constants.SYNTAX_PROTECTED,
                        constants.SYNTAX_STATIC,
                        constants.SYNTAX_FINAL,
                        constants.SYNTAX_ABSTRACT,
                        constants.SYNTAX_SYNCHRONIZED,
                    ]:
                        modifiers.append(self.get_node_text(modifier, source))

        if modifiers:
            metadata[constants.KEY_MODIFIERS] = modifiers

        # Check for generic parameters
        if self.has_child_type(node, constants.SYNTAX_TYPE_PARAMETERS):
            metadata[constants.KEY_HAS_GENERICS] = True

        return metadata
