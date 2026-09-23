"""Python-specific tree-sitter based chunker."""

import ast
from typing import Any, Dict, Optional, Set

from code_search_local.chunking.base_chunker import LanguageChunker


class PythonChunker(LanguageChunker):
    """Python-specific chunker using tree-sitter."""

    def __init__(self):
        super().__init__("python")

    def _get_splittable_node_types(self) -> Set[str]:
        """Python-specific splittable node types."""
        return {
            "function_definition",
            "class_definition",
            "decorated_definition",
        }

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        """Extract Python-specific metadata."""
        metadata = {"node_type": node.type}

        # Extract function/class name
        for child in node.children:
            if child.type == "identifier":
                metadata["name"] = self.get_node_text(child, source)
                break

        # Extract decorators if present
        if node.type == "decorated_definition":
            decorators = []
            for child in node.children:
                if child.type == "decorator":
                    decorators.append(self.get_node_text(child, source))
            metadata["decorators"] = decorators

            # Get the actual definition node
            for child in node.children:
                if child.type in ["function_definition", "class_definition"]:
                    # Get name from the actual definition
                    for subchild in child.children:
                        if subchild.type == "identifier":
                            metadata["name"] = self.get_node_text(subchild, source)
                            break

        # Extract docstring for functions and classes
        docstring = self._extract_docstring(node, source)
        if docstring:
            metadata["docstring"] = docstring

        # Count parameters for functions
        if node.type == "function_definition" or (
            node.type == "decorated_definition"
            and any(c.type == "function_definition" for c in node.children)
        ):
            definition = node.child_by_field_name("definition") or node
            for child in definition.children:
                if child.type == "parameters":
                    # Count parameter nodes
                    param_count = sum(
                        1
                        for c in child.children
                        if c.type in ["identifier", "typed_parameter", "default_parameter"]
                    )
                    metadata["param_count"] = param_count
                    break

        return metadata

    def _extract_docstring(self, node: Any, source: bytes) -> Optional[str]:
        """Extract docstring from function or class definition."""
        # Find the body/block of the function or class
        body_node = None
        for child in node.children:
            if child.type == "block":
                body_node = child
                break
            elif child.type in ["function_definition", "class_definition"]:
                # Handle decorated definitions
                for subchild in child.children:
                    if subchild.type == "block":
                        body_node = subchild
                        break

        if not body_node or not body_node.children:
            return None

        # New grammars expose a string directly; older versions wrap expressions.
        first = body_node.children[0]
        candidates = first.children if first.type == "expression_statement" else [first]
        for child in candidates:
            if child.type == "string":
                try:
                    value = ast.literal_eval(self.get_node_text(child, source))
                except (SyntaxError, ValueError):
                    return None
                return value.strip() if isinstance(value, str) else None
        return None
