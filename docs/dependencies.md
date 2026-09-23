# Dependency selection (2026-09-23)

Every direct application, test and build dependency is declared in `pyproject.toml`. `uv.lock` records exact transitive resolution. Runtime provisioning uses the bundled copies of those same files; there is no second requirements list. Latest stable versions were checked using the [PyPI JSON API](https://docs.pypi.org/api/json/). Vendor GPU wheels use the explicitly scoped PyTorch and AMD indexes.

| Package | Latest stable checked | Latest PyPI upload |
|---|---|---|
| [aiohttp](https://pypi.org/project/aiohttp/) | 3.14.3 | 2026-07-23 |
| [build](https://pypi.org/project/build/) | 1.6.1 | 2026-09-10 |
| [click](https://pypi.org/project/click/) | 8.5.0 | 2026-08-26 |
| [coverage](https://pypi.org/project/coverage/) | 7.16.1 | 2026-09-13 |
| [faiss-cpu](https://pypi.org/project/faiss-cpu/) | 1.15.1 | 2026-09-16 |
| [fastmcp](https://pypi.org/project/fastmcp/) | 4.0.7 | 2026-09-23 |
| [httpx2](https://pypi.org/project/httpx2/) | 2.13.1 | 2026-09-23 |
| [huggingface-hub](https://pypi.org/project/huggingface-hub/) | 1.32.0 | 2026-09-17 |
| [numpy](https://pypi.org/project/numpy/) | 2.5.3 | 2026-09-06 |
| [pathspec](https://pypi.org/project/pathspec/) | 1.1.1 | 2026-04-27 |
| [pipx](https://pypi.org/project/pipx/) | 1.17.6 | 2026-09-22 |
| [pytest](https://pypi.org/project/pytest/) | 9.1.1 | 2026-06-19 |
| [pytest-asyncio](https://pypi.org/project/pytest-asyncio/) | 1.4.0 | 2026-05-26 |
| [pytest-cov](https://pypi.org/project/pytest-cov/) | 7.1.0 | 2026-03-21 |
| [pyzmq](https://pypi.org/project/pyzmq/) | 27.2.0 | 2026-08-20 |
| [rich](https://pypi.org/project/rich/) | 15.0.0 | 2026-04-12 |
| [ruff](https://pypi.org/project/ruff/) | 0.16.8 | 2026-09-16 |
| [sentence-transformers](https://pypi.org/project/sentence-transformers/) | 6.1.0 | 2026-09-18 |
| [setuptools](https://pypi.org/project/setuptools/) | 84.0.0 | 2026-08-08 |
| [starlette](https://pypi.org/project/starlette/) | 1.7.0 | 2026-09-23 |
| [textual](https://pypi.org/project/textual/) | 8.2.8 | 2026-06-30 |
| [tomlkit](https://pypi.org/project/tomlkit/) | 0.15.1 | 2026-07-17 |
| [tree-sitter](https://pypi.org/project/tree-sitter/) | 0.26.0 | 2026-06-30 |
| [tree-sitter-language-pack](https://pypi.org/project/tree-sitter-language-pack/) | 1.20.0 | 2026-09-14 |
| [uv](https://pypi.org/project/uv/) | 0.12.18 | 2026-09-22 |
| [uvicorn](https://pypi.org/project/uvicorn/) | 0.53.0 | 2026-09-14 |
| [watchfiles](https://pypi.org/project/watchfiles/) | 1.3.0 | 2026-09-21 |
| [wheel](https://pypi.org/project/wheel/) | 0.48.0 | 2026-08-11 |

Pytest-cov's stable release is just outside six months, but [upstream maintenance](https://github.com/pytest-dev/pytest-cov) was verified on 2026-09-21. The other selected PyPI packages above have releases within six months. Unused pytest-mock and PyYAML were removed rather than installed. SQLite comes from Python's standard library.

## Alternatives examined

- **IPC:** [ipc](https://pypi.org/project/ipc/) last released in 2018 and is unsuitable. [pynng](https://pypi.org/project/pynng/) 0.9.0 last released 2026-02-04. [PyZMQ](https://pypi.org/project/pyzmq/) 27.2.0 has a recent release, broad adoption (including Jupyter), native Unix IPC/pub-sub and asyncio support. It supplies transport, bounded socket queues and reconnection; application sequence numbers and snapshot resynchronization handle dropped updates.
- **HTTP:** PyPI `http-server` returns 404. [FastAPI](https://pypi.org/project/fastapi/) is actively maintained, but another routing framework adds no value here. [FastMCP](https://pypi.org/project/fastmcp/) already supplies Streamable HTTP through Starlette; [Uvicorn](https://pypi.org/project/uvicorn/) is the established ASGI server. The service uses those existing interfaces and one Uvicorn worker.
- **TUI:** [Textual](https://pypi.org/project/textual/) supplies fullscreen/inline terminal applications and headless test support; its Rich dependency renders the same complete report. Rich is also declared directly because the application imports it.
- **Parsing:** the maintained tree-sitter-language-pack replaces disparate individual grammar wheels. Setup prefetches supported grammars so runtime parsing can work offline.
- **Persistence:** abandoned sqlitedict was replaced with standard-library SQLite WAL transactions and immutable FAISS generation files.

## GPU package sources

PyTorch 2.14.0 is selected from its [CPU](https://download.pytorch.org/whl/cpu/torch/), [CUDA 13.0](https://download.pytorch.org/whl/cu130/torch/) or [ROCm 7.14](https://download.pytorch.org/whl/rocm7.14/torch/) index. ROCm 7.14.1 and device libraries come from the PyTorch ROCm and [AMD multi-architecture](https://repo.amd.com/rocm/whl-multi-arch/) indexes. These wheels install into isolated environments, following [AMD's venv runtime packaging](https://rocm.docs.amd.com/en/docs-7.14.0/install/rocm.html).

The unrelated PyPI `rocm` package must never satisfy the runtime requirement. ROCm components are direct optional dependencies with explicit uv source mappings because uv does not apply source overrides to purely transitive packages. The CPU, CUDA and ROCm extras conflict by design. FAISS always uses the CPU wheel; embeddings use the selected GPU.
