"""Multi-language chunker that combines AST and tree-sitter approaches."""

import logging
from pathlib import Path
from typing import List, Optional

from code_search_local import constants
from code_search_local.chunking.code_chunk import CodeChunk
from code_search_local.chunking.languages import LANGUAGE_MAP
from code_search_local.chunking.tree_sitter import TreeSitterChunk, TreeSitterChunker
from code_search_local.filesystem import default_ignore_patterns
from code_search_local.merkle.merkle_dag import load_pathspec

logger = logging.getLogger(__name__)


class MultiLanguageChunker:
    """Unified chunker supporting multiple programming languages."""

    # Supported extensions - derived from LANGUAGE_MAP
    SUPPORTED_EXTENSIONS = set(LANGUAGE_MAP.keys())

    # Common large/build/tooling directories to skip during traversal
    DEFAULT_IGNORED_DIRS = default_ignore_patterns()

    def __init__(self, root_path: Optional[str] = None):
        """Initialize multi-language chunker.

        Args:
            root_path: Optional root path for relative path calculation
        """
        self.root_path = root_path
        # Use AST chunker for Python (more mature implementation)
        # Use tree-sitter for other languages
        self.tree_sitter_chunker = TreeSitterChunker()
        # Project-level ignore (.code-search-ignore) for chunk_directory()
        self.pathspec = load_pathspec(Path(root_path)) if root_path else None

    def is_supported(self, file_path: str) -> bool:
        """Check if file type is supported.

        Args:
            file_path: Path to file

        Returns:
            True if file type is supported
        """
        suffix = Path(file_path).suffix.lower()
        return suffix in self.SUPPORTED_EXTENSIONS

    def chunk_file(self, file_path: str) -> List[CodeChunk]:
        """Chunk a file into semantic units.

        Args:
            file_path: Path to the file

        Returns:
            List of CodeChunk objects
        """
        if not self.is_supported(file_path):
            logger.debug(f"File type not supported: {file_path}")
            return []

        # Use tree-sitter for all  languages
        try:
            tree_chunks = self.tree_sitter_chunker.chunk_file(file_path)
            # Convert TreeSitterChunk to CodeChunk
            return self._convert_tree_chunks(tree_chunks, file_path)
        except Exception as e:
            logger.error(f"Failed to chunk file {file_path}: {e}")
            return []

    def _convert_tree_chunks(
        self, tree_chunks: List[TreeSitterChunk], file_path: str
    ) -> List[CodeChunk]:
        """Convert tree-sitter chunks to CodeChunk format.

        Args:
            tree_chunks: List of TreeSitterChunk objects
            file_path: Path to the source file

        Returns:
            List of CodeChunk objects
        """
        code_chunks = []

        for tchunk in tree_chunks:
            # Extract metadata
            name = tchunk.metadata.get(constants.KEY_NAME)
            docstring = tchunk.metadata.get(constants.KEY_DOCSTRING)
            decorators = tchunk.metadata.get(constants.KEY_DECORATORS, [])

            # Map tree-sitter node types to our chunk types
            chunk_type_map = {
                constants.KEY_FUNCTION_DECLARATION: constants.KEY_FUNCTION,
                constants.KEY_FUNCTION_DEFINITION: constants.KEY_FUNCTION,
                constants.KEY_ARROW_FUNCTION: constants.KEY_FUNCTION,
                constants.KEY_FUNCTION: constants.KEY_FUNCTION,
                constants.KEY_FUNCTION_ITEM: constants.KEY_FUNCTION,  # Rust
                constants.KEY_METHOD_DECLARATION: constants.SYNTAX_METHOD,  # Go, Java
                constants.KEY_METHOD_DEFINITION: constants.SYNTAX_METHOD,
                constants.KEY_CLASS_DECLARATION: constants.SYNTAX_CLASS,
                constants.KEY_CLASS_DEFINITION: constants.SYNTAX_CLASS,
                constants.KEY_CLASS_SPECIFIER: constants.SYNTAX_CLASS,  # C++
                constants.KEY_INTERFACE_DECLARATION: constants.SYNTAX_INTERFACE,
                constants.KEY_TYPE_ALIAS_DECLARATION: constants.KEY_TYPE,
                constants.KEY_TYPE_DECLARATION: constants.KEY_TYPE,  # Go
                constants.KEY_ENUM_DECLARATION: constants.SYNTAX_ENUM,
                constants.KEY_ENUM_SPECIFIER: constants.SYNTAX_ENUM,  # C
                constants.KEY_ENUM_ITEM: constants.SYNTAX_ENUM,  # Rust
                constants.KEY_STRUCT_DECLARATION: constants.SYNTAX_STRUCT,  # C#
                constants.KEY_STRUCT_SPECIFIER: constants.SYNTAX_STRUCT,  # C/C++
                constants.KEY_STRUCT_ITEM: constants.SYNTAX_STRUCT,  # Rust
                constants.KEY_UNION_SPECIFIER: constants.SYNTAX_UNION,  # C/C++
                constants.KEY_NAMESPACE_DEFINITION: constants.SYNTAX_NAMESPACE,  # C++
                constants.KEY_NAMESPACE_DECLARATION: constants.SYNTAX_NAMESPACE,  # C#
                constants.KEY_IMPL_ITEM: constants.SYNTAX_IMPL,  # Rust
                constants.KEY_TRAIT_ITEM: constants.SYNTAX_TRAIT,  # Rust
                constants.KEY_MOD_ITEM: constants.SYNTAX_MODULE,  # Rust
                constants.KEY_MACRO_DEFINITION: constants.SYNTAX_MACRO,  # Rust
                constants.KEY_CONSTRUCTOR_DECLARATION: constants.SYNTAX_CONSTRUCTOR,  # Java/C#
                constants.KEY_DESTRUCTOR_DECLARATION: constants.SYNTAX_DESTRUCTOR,  # C#
                constants.KEY_PROPERTY_DECLARATION: constants.SYNTAX_PROPERTY,  # C#
                constants.KEY_EVENT_DECLARATION: constants.SYNTAX_EVENT,  # C#
                constants.KEY_TEMPLATE_DECLARATION: constants.SYNTAX_TEMPLATE,  # C++
                constants.KEY_CONCEPT_DEFINITION: constants.SYNTAX_CONCEPT,  # C++
                constants.KEY_ANNOTATION_TYPE_DECLARATION: constants.SYNTAX_ANNOTATION,  # Java
                constants.KEY_SCRIPT_ELEMENT: constants.SYNTAX_SCRIPT,  # Svelte
                constants.KEY_STYLE_ELEMENT: constants.SYNTAX_STYLE,  # Svelte
                constants.KEY_SECTION: constants.KEY_SECTION,  # Markdown
                constants.KEY_PREAMBLE: constants.KEY_PREAMBLE,  # Markdown
                constants.KEY_DOCUMENT: constants.KEY_DOCUMENT,  # Markdown
                constants.KEY_CONTRACT_DECLARATION: constants.SYNTAX_CONTRACT,  # Solidity
                constants.KEY_LIBRARY_DECLARATION: constants.SYNTAX_LIBRARY,  # Solidity
                constants.KEY_MODIFIER_DEFINITION: constants.SYNTAX_MODIFIER,  # Solidity
                constants.KEY_CONSTRUCTOR_DEFINITION: constants.SYNTAX_CONSTRUCTOR,  # Solidity
                constants.KEY_FALLBACK_RECEIVE_DEFINITION: constants.KEY_FUNCTION,  # Solidity (fallback/receive)
                constants.KEY_EVENT_DEFINITION: constants.SYNTAX_EVENT,  # Solidity
                constants.KEY_ERROR_DECLARATION: constants.KEY_ERROR,  # Solidity
            }

            chunk_type = chunk_type_map.get(tchunk.node_type, tchunk.node_type)

            # Extract parent name and adjust chunk type for methods
            parent_name = tchunk.metadata.get(constants.KEY_PARENT_NAME)

            # If we have a parent_name and it's a function, it's actually a method
            if parent_name and chunk_type == constants.KEY_FUNCTION:
                chunk_type = constants.SYNTAX_METHOD

            # Build folder structure from file path
            path = Path(file_path)
            folder_parts = []
            if self.root_path:
                try:
                    rel_path = path.relative_to(self.root_path)
                    folder_parts = list(rel_path.parent.parts)
                except ValueError:
                    folder_parts = [path.parent.name] if path.parent.name else []
            else:
                folder_parts = [path.parent.name] if path.parent.name else []

            # Extract semantic tags from metadata
            tags = []
            if tchunk.metadata.get(constants.KEY_IS_ASYNC):
                tags.append(constants.SYNTAX_ASYNC)
            if tchunk.metadata.get(constants.KEY_IS_GENERATOR):
                tags.append(constants.SYNTAX_GENERATOR)
            if tchunk.metadata.get(constants.KEY_IS_EXPORT):
                tags.append(constants.SYNTAX_EXPORT)
            if tchunk.metadata.get(constants.KEY_HAS_GENERICS):
                tags.append(constants.SYNTAX_GENERIC)
            if tchunk.metadata.get(constants.KEY_IS_COMPONENT):
                tags.append(constants.SYNTAX_COMPONENT)

            # Add language tag
            tags.append(tchunk.language)

            # Create CodeChunk
            chunk = CodeChunk(
                file_path=str(path),
                relative_path=str(path.relative_to(self.root_path))
                if self.root_path
                else str(path),
                folder_structure=folder_parts,
                chunk_type=chunk_type,
                content=tchunk.content,
                start_line=tchunk.start_line,
                end_line=tchunk.end_line,
                name=name,
                parent_name=parent_name,
                docstring=docstring,
                decorators=decorators,
                imports=[],  # Tree-sitter doesn't extract imports yet
                complexity_score=0,  # Not calculated for tree-sitter chunks
                tags=tags,
            )

            code_chunks.append(chunk)

        return code_chunks

    def chunk_directory(
        self, directory_path: str, extensions: Optional[List[str]] = None
    ) -> List[CodeChunk]:
        """Chunk all supported files in a directory.

        Args:
            directory_path: Path to directory
            extensions: Optional list of extensions to process (default: all supported)

        Returns:
            List of CodeChunk objects from all files
        """
        all_chunks = []
        dir_path = Path(directory_path)

        if not dir_path.exists() or not dir_path.is_dir():
            logger.error(f"Directory does not exist: {directory_path}")
            return []

        # Use provided extensions or all supported
        if extensions:
            valid_extensions = set(extensions) & self.SUPPORTED_EXTENSIONS
        else:
            valid_extensions = self.SUPPORTED_EXTENSIONS

        # Find all files with supported extensions
        for ext in valid_extensions:
            for file_path in dir_path.rglob(f"*{ext}"):
                # Skip common large/build/tooling directories
                if any(part in self.DEFAULT_IGNORED_DIRS for part in file_path.parts):
                    continue

                # Honor project .code-search-ignore (gitignore syntax)
                if self.pathspec is not None and self.root_path:
                    try:
                        rel = file_path.relative_to(self.root_path).as_posix()
                    except ValueError:
                        rel = None
                    if rel and self.pathspec.match_file(rel):
                        continue

                try:
                    chunks = self.chunk_file(str(file_path))
                    all_chunks.extend(chunks)
                    logger.debug(f"Chunked {len(chunks)} from {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to chunk {file_path}: {e}")

        logger.info(f"Total chunks from directory: {len(all_chunks)}")
        return all_chunks
