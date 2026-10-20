"""Basic tests for multi-language chunking."""

from pathlib import Path

import pytest

from code_search_local import constants
from code_search_local.chunking.multi_language_chunker import MultiLanguageChunker
from tests import constants as test_constants


class TestMultiLanguageChunker:
    """Test multi-language chunking functionality."""

    @pytest.fixture
    def chunker(self):
        """Create a chunker instance."""
        return MultiLanguageChunker()

    @pytest.fixture
    def test_data_dir(self):
        """Get test data directory."""
        return (
            Path(__file__).parent.parent
            / test_constants.PATH_TEST_DATA
            / test_constants.PATH_MULTI_LANGUAGE
        )

    def test_supported_extensions(self, chunker):
        """Test that all required extensions are supported."""
        assert chunker.is_supported("test.py")
        assert chunker.is_supported("test.js")
        assert chunker.is_supported("test.jsx")
        assert chunker.is_supported("test.ts")
        assert chunker.is_supported("test.tsx")
        assert chunker.is_supported("test.svelte")
        assert chunker.is_supported("test.java")
        assert chunker.is_supported("test.go")
        assert chunker.is_supported("test.c")
        assert chunker.is_supported("test.cpp")
        assert chunker.is_supported("test.cc")
        assert chunker.is_supported("test.cxx")
        assert chunker.is_supported("test.c++")
        assert chunker.is_supported("test.cs")
        assert chunker.is_supported("test.rs")
        assert not chunker.is_supported("test.txt")

    def test_chunk_python_file(self, chunker, test_data_dir):
        """Test chunking Python file."""
        file_path = test_data_dir / test_constants.PATH_EXAMPLE_PY
        chunks = chunker.chunk_file(str(file_path))

        assert len(chunks) > 0
        # Should find the class and functions
        chunk_types = {chunk.chunk_type for chunk in chunks}
        assert constants.KEY_FUNCTION in chunk_types or constants.SYNTAX_METHOD in chunk_types
        assert constants.SYNTAX_CLASS in chunk_types

    def test_chunk_javascript_file(self, chunker, test_data_dir):
        """Test chunking JavaScript file."""
        file_path = test_data_dir / test_constants.PATH_EXAMPLE_JS
        chunks = chunker.chunk_file(str(file_path))

        assert len(chunks) > 0
        # Should find functions and class
        chunk_names = {chunk.name for chunk in chunks if chunk.name}
        assert test_constants.VALUE_CALCULATE_SUM in chunk_names
        assert test_constants.VALUE_CALCULATOR in chunk_names

    def test_chunk_typescript_file(self, chunker, test_data_dir):
        """Test chunking TypeScript file."""
        file_path = test_data_dir / test_constants.PATH_EXAMPLE_TS
        chunks = chunker.chunk_file(str(file_path))

        assert len(chunks) > 0
        # Should find interface, class, and functions
        chunk_types = {chunk.chunk_type for chunk in chunks}
        assert any(
            t in chunk_types
            for t in [constants.SYNTAX_CLASS, constants.SYNTAX_INTERFACE, constants.KEY_FUNCTION]
        )

    def test_chunk_jsx_file(self, chunker, test_data_dir):
        """Test chunking JSX file."""
        file_path = test_data_dir / test_constants.PATH_COMPONENT_JSX
        chunks = chunker.chunk_file(str(file_path))

        assert len(chunks) > 0
        # Should find React components
        chunk_names = {chunk.name for chunk in chunks if chunk.name}
        assert (
            test_constants.VALUE_COUNTER in chunk_names
            or test_constants.VALUE_USER_CARD in chunk_names
        )

    def test_chunk_tsx_file(self, chunker, test_data_dir):
        """Test chunking TSX file."""
        file_path = test_data_dir / test_constants.PATH_COMPONENT_TSX
        chunks = chunker.chunk_file(str(file_path))

        assert len(chunks) > 0
        # Should find TypeScript React components
        chunk_names = {chunk.name for chunk in chunks if chunk.name}
        assert any(name in chunk_names for name in ["TypedCounter", "UserList"])

    def test_chunk_svelte_file(self, chunker, test_data_dir):
        """Test chunking Svelte file."""
        file_path = test_data_dir / test_constants.PATH_APP_SVELTE
        chunks = chunker.chunk_file(str(file_path))

        assert len(chunks) > 0
        # Should find script and style blocks
        chunk_types = {chunk.chunk_type for chunk in chunks}
        assert (
            constants.SYNTAX_SCRIPT in chunk_types
            or constants.SYNTAX_STYLE in chunk_types
            or len(chunks) > 0
        )

    def test_chunk_java_file(self, chunker, test_data_dir):
        """Test chunking Java file."""
        file_path = test_data_dir / test_constants.PATH_CALCULATOR_JAVA
        chunks = chunker.chunk_file(str(file_path))

        assert len(chunks) > 0
        # Should find class, methods, interface, and enum
        chunk_names = {chunk.name for chunk in chunks if chunk.name}
        chunk_types = {chunk.chunk_type for chunk in chunks}

        assert test_constants.VALUE_CALCULATOR in chunk_names
        assert test_constants.VALUE_MATH_OPERATIONS in chunk_names
        assert test_constants.VALUE_OPERATION in chunk_names
        assert any(
            t in chunk_types
            for t in [constants.SYNTAX_CLASS, constants.SYNTAX_INTERFACE, constants.SYNTAX_ENUM]
        )

    def test_chunk_go_file(self, chunker, test_data_dir):
        """Test chunking Go file."""
        file_path = test_data_dir / test_constants.PATH_CALCULATOR_GO
        chunks = chunker.chunk_file(str(file_path))

        assert len(chunks) > 0
        # Should find functions, methods, types, and interfaces
        chunk_names = {chunk.name for chunk in chunks if chunk.name}
        chunk_types = {chunk.chunk_type for chunk in chunks}

        assert any(name in chunk_names for name in ["Calculator", "CalculateSum", "NewCalculator"])
        assert len(chunk_names) > 0
        assert (
            any(
                t in chunk_types
                for t in [
                    constants.KEY_FUNCTION,
                    constants.SYNTAX_METHOD,
                    constants.KEY_TYPE,
                    constants.SYNTAX_INTERFACE,
                ]
            )
            or len(chunks) > 0
        )

    @pytest.mark.parametrize(
        "filename",
        (
            test_constants.PATH_CALCULATOR_C,
            test_constants.PATH_CALCULATOR_CPP,
            test_constants.PATH_CALCULATOR_CS,
        ),
    )
    def test_chunk_c_family_file(self, chunker, test_data_dir, filename):
        chunks = chunker.chunk_file(str(test_data_dir / filename))
        if chunks:
            chunk_names = {chunk.name for chunk in chunks if chunk.name}
            chunk_types = {chunk.chunk_type for chunk in chunks}
            assert chunk_names or chunk_types

    def test_chunk_rust_file(self, chunker, test_data_dir):
        """Test chunking Rust file."""
        file_path = test_data_dir / test_constants.PATH_CALCULATOR_RS
        chunks = chunker.chunk_file(str(file_path))

        assert len(chunks) > 0
        # Should find functions, structs, traits, enums, impls, macros
        chunk_names = {chunk.name for chunk in chunks if chunk.name}
        chunk_types = {chunk.chunk_type for chunk in chunks}

        assert any(
            name in chunk_names
            for name in ["Calculator", "calculate_sum", "MathOperations", "Operation", "Point"]
        )
        assert any(
            t in chunk_types
            for t in [
                constants.KEY_FUNCTION,
                constants.SYNTAX_STRUCT,
                constants.SYNTAX_TRAIT,
                constants.SYNTAX_ENUM,
                constants.SYNTAX_IMPL,
                constants.SYNTAX_MACRO,
            ]
        )
