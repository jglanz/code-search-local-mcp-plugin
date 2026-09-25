"""Exercise real grammars and metadata, including languages previously untested."""

import pytest

from code_search_local.chunking.available_languages import (
    get_availiable_language,
    prefetch_languages,
)
from code_search_local.chunking.code_chunk import CodeChunk
from code_search_local.chunking.languages.markdown_chunker import MarkdownChunker
from code_search_local.chunking.multi_language_chunker import MultiLanguageChunker
from code_search_local.chunking.tree_sitter import TreeSitterChunker

CASES = [
    (
        "sample.sol",
        """pragma solidity ^0.8.24;
abstract contract Base { function value() public virtual returns (uint); }
contract Wallet is Base {
    struct Balance { uint amount; }
    enum Status { Open, Closed }
    event Paid(address user);
    error Unauthorized();
    constructor() {}
    modifier allowed() { _; }
    function value() public pure override returns (uint) { return 1; }
    receive() external payable {}
    fallback() external payable {}
}
library Numbers { function add(uint a,uint b) internal pure returns(uint) { return a+b; } }
interface IWallet { function value() external returns (uint); }
""",
        {
            "Wallet",
            "Base",
            "Balance",
            "Status",
            "Paid",
            "Unauthorized",
            "constructor",
            "allowed",
            "value",
            "receive",
            "fallback",
            "Numbers",
            "IWallet",
        },
    ),
    (
        "sample.cpp",
        """template<typename T> T identity(T x) { return x; }
class Example { public: int run() { return 1; } };
struct Pair { int a; int b; };
namespace Demo { int run() { return 2; } }
int Example::run() { return 3; }
union Number { int i; double d; };
enum State { On, Off };
""",
        {"identity", "Example", "Pair", "Demo"},
    ),
    (
        "sample.cs",
        """public class Handler<T> {
    public Handler() {} ~Handler() {}
    public async Task<T> Fetch<T>() { return default(T); }
    public string Name { get; set; }
    public event Action Changed;
}
namespace Example { class Other {} }
""",
        {"Handler", "Fetch", "Name", "Changed", "Example"},
    ),
    (
        "sample.c",
        """static inline int square(int x) { return x*x; }
struct Point { int x; int y; };
union Number { int i; double d; };
enum State { On, Off };
typedef struct Point Point;
int (*factory(void))(int) { return square; }
""",
        {"square", "Point", "Number", "State"},
    ),
    (
        "sample.java",
        """public abstract class Store<T> {
    public Store() {}
    public static <U> U identity(U x) { return x; }
    protected abstract T load();
}
@interface Label { String value(); }
""",
        {"Store", "identity", "load"},
    ),
    (
        "sample.py",
        '''@decorator(flag=True)
async def fetch(value: str) -> str:
    """Return the value."""
    return value
class Example:
    @property
    def name(self):
        return "name"
def generator():
    yield 1
''',
        {"fetch", "Example", "name", "generator"},
    ),
    (
        "sample.js",
        """export async function fetch() { return 1; }
const lower = x => x;
function* generator() { yield 1; }
class Store { method() {} }
""",
        {"fetch", "lower", "generator", "Store"},
    ),
    (
        "sample.ts",
        """export async function fetch<T>(input:T):Promise<T> { return input; }
interface Store<T> { value:T; }
type Value = string | number;
class Handler<T> { run() {} }
""",
        {"fetch", "Store", "Value", "Handler"},
    ),
    (
        "sample.jsx",
        """export const Card = () => <div>Card</div>;
const lowercase = () => 1;
function Panel() { return <Card/>; }
""",
        {"Card", "lowercase", "Panel"},
    ),
    (
        "sample.svelte",
        """<script lang="ts">export let name: string; const value = 1;</script>
<script context="module">export const shared = 1;</script>
<h1>{name}</h1><style lang="scss">h1 { color: red; }</style>
""",
        set(),
    ),
]


@pytest.mark.parametrize("filename,source,names", CASES, ids=[c[0] for c in CASES])
def test_language_metadata_from_real_grammar(filename, source, names):
    chunker = TreeSitterChunker().get_chunker(filename)
    chunks = chunker.chunk_code(source)
    assert chunks
    found = {chunk.metadata.get("name") for chunk in chunks}
    assert names <= found, found
    for chunk in chunks:
        assert chunk.content.strip()
        assert 1 <= chunk.start_line <= chunk.end_line
        assert chunk.to_dict()["language"] == chunk.language


@pytest.mark.parametrize(
    "source,types",
    [
        ("", []),
        ("plain text\n", ["document"]),
        ("Introduction\n\n# First\nBody\n## Second\nText\n", ["preamble", "section", "section"]),
        ("\n\n# Only\nBody", ["section"]),
        ("# Heading\nText", ["section"]),
    ],
)
def test_markdown_sections(source, types):
    chunker = MarkdownChunker()
    chunks = chunker.chunk_code(source)
    assert [c.node_type for c in chunks] == types
    source_bytes = source.encode()

    def visit(node):
        metadata = chunker.extract_metadata(node, source_bytes)
        if node.type == "atx_heading":
            assert metadata["heading_level"] >= 1
        for child in node.children:
            visit(child)

    visit(chunker.parser.parse(source_bytes).root_node)


def test_directory_chunking_and_invalid_inputs(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("async def fetch(): return 1\n")
    (tmp_path / "b.txt").write_text("text")
    (tmp_path / "ignored.py").write_text("def ignored(): pass\n")
    (tmp_path / ".claude-context-ignore").write_text("ignored.py\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("function ignored() {}")
    backend_env = tmp_path / ".venvs" / "cuda" / "site-packages"
    backend_env.mkdir(parents=True)
    (backend_env / "library.py").write_text("def ignored(): pass\n")
    fresh = MultiLanguageChunker(str(tmp_path))
    chunks = fresh.chunk_directory(str(tmp_path))
    assert chunks and all(c.name != "ignored" for c in chunks)
    assert fresh.chunk_file(str(tmp_path / "b.txt")) == []
    assert fresh.chunk_file(str(tmp_path / "missing.py")) == []
    outside = tmp_path.parent / "outside.py"
    outside.write_text("def outside(): pass\n")
    assert MultiLanguageChunker().chunk_file(str(outside))
    tree = TreeSitterChunker()
    for content in (b"\0binary", b"\xff\xfe"):
        (tmp_path / "bad.py").write_bytes(content)
        assert tree.chunk_file(str(tmp_path / "bad.py")) == []

    def fail(*args, **kwargs):
        raise ValueError("bad parser")

    monkeypatch.setattr(tree.get_chunker("a.py"), "chunk_code", fail)
    assert tree.chunk_file(str(tmp_path / "a.py")) == []
    monkeypatch.setattr(fresh.tree_sitter_chunker, "chunk_file", fail)
    assert fresh.chunk_file(str(tmp_path / "a.py")) == []


def test_language_catalog_and_chunk_defaults():
    languages = get_availiable_language()
    assert len(languages) == len(list(languages)) >= 14
    assert languages["python"]
    prefetch_languages()
    chunk = CodeChunk(
        "x", "module", 1, 1, "/root/a.py", "folder/a.py", [], None, None, None, [], [], 0, []
    )
    assert chunk.folder_structure == ["folder"]


@pytest.mark.parametrize(
    "literal,expected",
    [
        ('"""  Multi line doc.  """', "Multi line doc."),
        ("'Short doc.'", "Short doc."),
        ('r"Raw doc."', "Raw doc."),
    ],
)
def test_python_docstrings_in_decorated_functions(literal, expected):
    chunker = TreeSitterChunker().get_chunker("sample.py")
    source = f"@decorate\ndef documented(a: int, b=2):\n    {literal}\n    return a + b\n"
    chunks = chunker.chunk_code(source)
    documented = next(chunk for chunk in chunks if chunk.metadata.get("name") == "documented")
    assert documented.metadata["docstring"] == expected
    assert documented.metadata["decorators"] == ["@decorate"]
    assert documented.metadata["param_count"] == 2


def test_code_chunk_has_independent_metadata_lists():
    first = CodeChunk("one", "module", 1, 1, "", "", [])
    second = CodeChunk("two", "module", 1, 1, "", "", [])
    first.tags.append("tag")
    first.imports.append("math")
    first.decorators.append("cached")
    assert second.tags == second.imports == second.decorators == []


@pytest.mark.parametrize("literal", ['f"dynamic {value}"', 'b"bytes"'])
def test_python_nonconstant_or_bytes_are_not_docstrings(literal):
    chunker = TreeSitterChunker().get_chunker("sample.py")
    chunks = chunker.chunk_code(f"def sample():\n    {literal}\n")
    assert "docstring" not in chunks[0].metadata
