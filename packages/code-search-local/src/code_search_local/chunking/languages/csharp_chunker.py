"""C#-specific tree-sitter based chunker."""

from typing import Any, Dict

from code_search_local import constants
from code_search_local.chunking.base_chunker import LanguageChunker


class CSharpChunker(LanguageChunker):
    """C#-specific chunker using tree-sitter."""

    LANGUAGE_NAME = constants.LANGUAGE_CSHARP

    SPLITTABLE_NODE_TYPES = frozenset(
        {
            constants.KEY_METHOD_DECLARATION,
            constants.KEY_CONSTRUCTOR_DECLARATION,
            constants.KEY_DESTRUCTOR_DECLARATION,
            constants.KEY_CLASS_DECLARATION,
            constants.KEY_STRUCT_DECLARATION,
            constants.KEY_INTERFACE_DECLARATION,
            constants.KEY_ENUM_DECLARATION,
            constants.KEY_NAMESPACE_DECLARATION,
            constants.KEY_PROPERTY_DECLARATION,
            constants.KEY_EVENT_DECLARATION,
            constants.SYNTAX_EVENT_FIELD_DECLARATION,
        }
    )

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract C#-specific metadata."""
        metadata = {constants.KEY_NODE_TYPE: node.type}

        if node.type == constants.SYNTAX_EVENT_FIELD_DECLARATION:
            declaration = next(
                c for c in node.children if c.type == constants.SYNTAX_VARIABLE_DECLARATION
            )
            declarator = next(
                c for c in declaration.children if c.type == constants.SYNTAX_VARIABLE_DECLARATOR
            )
            name = declarator.child_by_field_name(constants.KEY_NAME)
            if name is not None:
                metadata[constants.KEY_NAME] = self.get_node_text(name, source)

        # Extract name
        for child in node.children:
            if child.type == constants.SYNTAX_IDENTIFIER:
                metadata[constants.KEY_NAME] = self.get_node_text(child, source)
                break

        # Extract access modifiers
        modifiers = []
        for child in node.children:
            if child.type == constants.SYNTAX_MODIFIER:
                modifier_text = self.get_node_text(child, source)
                if modifier_text in [
                    constants.SYNTAX_PUBLIC,
                    constants.SYNTAX_PRIVATE,
                    constants.SYNTAX_PROTECTED,
                    constants.SYNTAX_INTERNAL,
                    constants.SYNTAX_STATIC,
                    constants.SYNTAX_VIRTUAL,
                    constants.SYNTAX_ABSTRACT,
                    constants.SYNTAX_OVERRIDE,
                    constants.SYNTAX_ASYNC,
                ]:
                    modifiers.append(modifier_text)

        if modifiers:
            metadata[constants.KEY_MODIFIERS] = modifiers
            if constants.SYNTAX_ASYNC in modifiers:
                metadata[constants.KEY_IS_ASYNC] = True

        # Check for generic parameters
        if self.has_child_type(node, constants.SYNTAX_TYPE_PARAMETER_LIST):
            metadata[constants.KEY_HAS_GENERICS] = True

        return metadata
