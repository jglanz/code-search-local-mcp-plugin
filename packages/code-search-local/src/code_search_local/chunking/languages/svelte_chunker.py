"""Svelte-specific tree-sitter based chunker."""

from typing import Any, Dict

from code_search_local import constants
from code_search_local.chunking.base_chunker import LanguageChunker


class SvelteChunker(LanguageChunker):
    """Svelte-specific chunker using tree-sitter."""

    LANGUAGE_NAME = constants.LANGUAGE_SVELTE

    SPLITTABLE_NODE_TYPES = frozenset(
        {
            constants.KEY_SCRIPT_ELEMENT,
            constants.KEY_STYLE_ELEMENT,
            constants.KEY_FUNCTION_DECLARATION,
            constants.KEY_FUNCTION,
            constants.KEY_ARROW_FUNCTION,
            constants.KEY_CLASS_DECLARATION,
            constants.KEY_METHOD_DEFINITION,
        }
    )

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract Svelte-specific metadata."""
        metadata = {constants.KEY_NODE_TYPE: node.type}

        if node.type == constants.KEY_SCRIPT_ELEMENT:
            self._tag_metadata(
                node,
                source,
                metadata,
                constants.KEY_SCRIPT_TYPE,
                constants.SVELTE_MODULE_CONTEXT,
                constants.SYNTAX_MODULE,
                constants.SYNTAX_INSTANCE,
            )
        elif node.type == constants.KEY_STYLE_ELEMENT:
            self._tag_metadata(
                node,
                source,
                metadata,
                constants.KEY_STYLE_SCOPE,
                constants.SYNTAX_GLOBAL,
                constants.SYNTAX_GLOBAL,
                constants.SYNTAX_COMPONENT,
            )

        # Extract function/class names
        for child in node.children:
            if child.type == constants.SYNTAX_IDENTIFIER:
                metadata[constants.KEY_NAME] = self.get_node_text(child, source)
                break

        return metadata

    def _tag_metadata(self, node, source, metadata, key, marker, present, absent):
        for child in node.children:
            if child.type == constants.SYNTAX_START_TAG:
                tag_text = self.get_node_text(child, source)
                metadata[key] = present if marker in tag_text else absent
                break
