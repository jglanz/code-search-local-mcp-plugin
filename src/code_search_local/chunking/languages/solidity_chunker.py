"""Solidity-specific tree-sitter based chunker."""

from typing import Any, Dict, Set

from code_search_local import constants
from code_search_local.chunking.base_chunker import LanguageChunker


class SoliditySolChunker(LanguageChunker):
    """Solidity-specific chunker using tree-sitter.

    Top-level chunkable units are contract / library / interface / abstract
    contract declarations. Inside those bodies we split on functions,
    modifiers, constructors, fallback/receive, structs, enums, events, and
    custom errors so each becomes its own searchable chunk.
    """

    # Top-level type containers — these become parents for nested chunks.
    _CONTAINER_NODES = {
        "contract_declaration",
        "library_declaration",
        "interface_declaration",
    }

    # Nested members inside a contract/library/interface body.
    _MEMBER_NODES = {
        "function_definition",
        "modifier_definition",
        "constructor_definition",
        "fallback_receive_definition",
        "struct_declaration",
        "enum_declaration",
        "event_definition",
        "error_declaration",
    }

    LANGUAGE_NAME = constants.LANGUAGE_SOLIDITY

    def _get_splittable_node_types(self) -> Set[str]:
        return self._CONTAINER_NODES | self._MEMBER_NODES

    def _get_recursable_container_types(self) -> Set[str]:
        # Recurse into contract/library/interface bodies so functions,
        # modifiers, structs, enums, events, errors are chunked individually.
        return self._CONTAINER_NODES

    def extract_metadata(self, node: Any, source: bytes) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {constants.KEY_NODE_TYPE: node.type}

        # Name: first identifier child for most node types. fallback_receive
        # nodes have no name (they're implicit `fallback`/`receive`); use the
        # leading keyword text as the name for clarity.
        name = None
        for child in node.children:
            if child.type == constants.SYNTAX_IDENTIFIER:
                name = self.get_node_text(child, source)
                break
        if not name and node.type == constants.KEY_FALLBACK_RECEIVE_DEFINITION:
            # Grab the first leaf token (`fallback` or `receive`).
            head = node.children[0] if node.children else None
            if head is not None:
                name = self.get_node_text(head, source)
        if not name and node.type == constants.KEY_CONSTRUCTOR_DEFINITION:
            name = constants.SYNTAX_CONSTRUCTOR
        if name:
            metadata[constants.KEY_NAME] = name

        # `abstract contract Foo` is still a contract_declaration; surface the
        # `abstract` modifier as a flag so the chunk metadata reflects it.
        if node.type == constants.KEY_CONTRACT_DECLARATION:
            text_before_name = source[
                node.start_byte : node.start_byte + constants.SOLIDITY_DECLARATION_PREFIX_BYTES
            ]
            if b"abstract" in text_before_name.split(b"contract", 1)[0]:
                metadata[constants.KEY_IS_ABSTRACT] = True

        # Visibility / state mutability are sibling children of functions and
        # state variables; expose as semantic tags.
        for child in node.children:
            if child.type == constants.KEY_VISIBILITY:
                metadata[constants.KEY_VISIBILITY] = self.get_node_text(child, source)
            elif child.type == constants.KEY_STATE_MUTABILITY:
                metadata[constants.KEY_STATE_MUTABILITY] = self.get_node_text(child, source)
            elif child.type == constants.SYNTAX_VIRTUAL:
                metadata[constants.KEY_IS_VIRTUAL] = True
            elif child.type == constants.SYNTAX_OVERRIDE_SPECIFIER:
                metadata[constants.KEY_IS_OVERRIDE] = True

        return metadata
