"""All tests isolate storage and explicitly opt into a fake model."""

from pathlib import Path
from typing import Dict

import pytest

from code_search_local.chunking.multi_language_chunker import MultiLanguageChunker
from tests.fixtures.sample_code import (
    SAMPLE_API_MODULE,
    SAMPLE_AUTH_MODULE,
    SAMPLE_DATABASE_MODULE,
    SAMPLE_UTILS_MODULE,
)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("CODE_SEARCH_STORAGE", str(tmp_path / "storage"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))


# Test fixtures
@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Each test gets a workspace owned and cleaned up by pytest."""
    project = tmp_path / "test_project"
    project.mkdir()
    return project


@pytest.fixture
def sample_codebase(temp_project_dir: Path) -> Dict[str, Path]:
    """Create a sample codebase with various Python modules."""
    if not SAMPLE_AUTH_MODULE:
        pytest.skip("Sample code not available")

    # Create directory structure
    src_dir = temp_project_dir / "src"
    src_dir.mkdir()

    auth_dir = src_dir / "auth"
    auth_dir.mkdir()

    database_dir = src_dir / "database"
    database_dir.mkdir()

    api_dir = src_dir / "api"
    api_dir.mkdir()

    utils_dir = src_dir / "utils"
    utils_dir.mkdir()

    # Create Python files with sample code
    files = {}

    # Authentication module
    auth_file = auth_dir / "authenticator.py"
    auth_file.write_text(SAMPLE_AUTH_MODULE)
    files["auth"] = auth_file

    # Database module
    db_file = database_dir / "manager.py"
    db_file.write_text(SAMPLE_DATABASE_MODULE)
    files["database"] = db_file

    # API module
    api_file = api_dir / "endpoints.py"
    api_file.write_text(SAMPLE_API_MODULE)
    files["api"] = api_file

    # Utils module
    utils_file = utils_dir / "helpers.py"
    utils_file.write_text(SAMPLE_UTILS_MODULE)
    files["utils"] = utils_file

    # Add __init__.py files
    for directory in [src_dir, auth_dir, database_dir, api_dir, utils_dir]:
        init_file = directory / "__init__.py"
        init_file.write_text("# Package init file")

    return files


@pytest.fixture
def chunker(temp_project_dir: Path) -> "MultiLanguageChunker":
    """Create a MultiLanguageChunker instance."""
    return MultiLanguageChunker(str(temp_project_dir))
