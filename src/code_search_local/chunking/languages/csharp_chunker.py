"""C#-specific tree-sitter based chunker."""

from typing import Any, Dict, Set

from code_search_local.chunking.base_chunker import LanguageChunker


class CSharpChunker(LanguageChunker):
    """C#-specific chunker using tree-sitter."""

    def __init__(self):
        super().__init__("csharp")

    def _get_splittable_node_types(self) -> Set[str]:
        """C#-specific splittable node types."""
        return {
            "method_declaration",
            "constructor_declaration",
            "destructor_declaration",
            "class_declaration",
            "struct_declaration",
            "interface_declaration",
            "enum_declaration",
            "namespace_declaration",
            "property_declaration",
            "event_declaration",
            "event_field_declaration",
        }

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract C#-specific metadata."""
        metadata = {"node_type": node.type}

        if node.type == "event_field_declaration":
            declaration = next(c for c in node.children if c.type == "variable_declaration")
            declarator = next(c for c in declaration.children if c.type == "variable_declarator")
            name = declarator.child_by_field_name("name")
            if name is not None:
                metadata["name"] = self.get_node_text(name, source)

        # Extract name
        for child in node.children:
            if child.type == "identifier":
                metadata["name"] = self.get_node_text(child, source)
                break

        # Extract access modifiers
        modifiers = []
        for child in node.children:
            if child.type == "modifier":
                modifier_text = self.get_node_text(child, source)
                if modifier_text in [
                    "public",
                    "private",
                    "protected",
                    "internal",
                    "static",
                    "virtual",
                    "abstract",
                    "override",
                    "async",
                ]:
                    modifiers.append(modifier_text)

        if modifiers:
            metadata["modifiers"] = modifiers
            if "async" in modifiers:
                metadata["is_async"] = True

        # Check for generic parameters
        for child in node.children:
            if child.type == "type_parameter_list":
                metadata["has_generics"] = True
                break

        return metadata
