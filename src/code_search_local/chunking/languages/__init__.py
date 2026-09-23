"""Language-specific tree-sitter based chunkers."""

from code_search_local.chunking.languages.c_chunker import CChunker
from code_search_local.chunking.languages.cpp_chunker import CppChunker
from code_search_local.chunking.languages.csharp_chunker import CSharpChunker
from code_search_local.chunking.languages.go_chunker import GoChunker
from code_search_local.chunking.languages.java_chunker import JavaChunker
from code_search_local.chunking.languages.javascript_chunker import JavaScriptChunker
from code_search_local.chunking.languages.jsx_chunker import JSXChunker
from code_search_local.chunking.languages.markdown_chunker import MarkdownChunker
from code_search_local.chunking.languages.python_chunker import PythonChunker
from code_search_local.chunking.languages.rust_chunker import RustChunker
from code_search_local.chunking.languages.solidity_chunker import SoliditySolChunker
from code_search_local.chunking.languages.svelte_chunker import SvelteChunker
from code_search_local.chunking.languages.typescript_chunker import TypeScriptChunker


# Each worker must own its mutable tree-sitter parser.
def _get_cpp_chunker() -> CppChunker:
    return CppChunker()


# Map file extensions to chunker classes and language names
LANGUAGE_MAP = {
    ".py": ("python", PythonChunker),
    ".js": ("javascript", JavaScriptChunker),
    ".jsx": ("jsx", JSXChunker),
    ".ts": ("typescript", lambda: TypeScriptChunker(use_tsx=False)),
    ".tsx": ("tsx", lambda: TypeScriptChunker(use_tsx=True)),
    ".svelte": ("svelte", SvelteChunker),
    ".go": ("go", GoChunker),
    ".rs": ("rust", RustChunker),
    ".java": ("java", JavaChunker),
    ".md": ("markdown", MarkdownChunker),
    ".c": ("c", CChunker),
    ".cpp": ("cpp", _get_cpp_chunker),
    ".cc": ("cpp", _get_cpp_chunker),
    ".cxx": ("cpp", _get_cpp_chunker),
    ".c++": ("cpp", _get_cpp_chunker),
    ".cs": ("csharp", CSharpChunker),
    ".sol": ("solidity", SoliditySolChunker),
}
