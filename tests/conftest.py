"""All tests isolate storage and explicitly opt into a fake model."""

from pathlib import Path
from typing import Dict

import pytest

from code_search_local import constants
from code_search_local.chunking.multi_language_chunker import MultiLanguageChunker
from tests import constants as test_constants
from tests.fixtures.sample_code import (
    SAMPLE_API_MODULE,
    SAMPLE_AUTH_MODULE,
    SAMPLE_DATABASE_MODULE,
    SAMPLE_UTILS_MODULE,
)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setenv(constants.ENV_CODE_SEARCH_STORAGE, str(tmp_path / constants.KEY_STORAGE))
    monkeypatch.setenv(constants.ENV_XDG_CONFIG_HOME, str(tmp_path / test_constants.PATH_CONFIG))
    monkeypatch.setenv(constants.ENV_XDG_RUNTIME_DIR, str(tmp_path / constants.KEY_RUNTIME))
    monkeypatch.setenv(constants.ENV_CODEX_HOME, str(tmp_path / constants.HARNESS_CODEX))
    monkeypatch.setenv(constants.ENV_CLAUDE_CONFIG_DIR, str(tmp_path / constants.HARNESS_CLAUDE))
    monkeypatch.delenv(constants.ENV_OPENCODE_CONFIG, raising=False)
    monkeypatch.delenv(constants.ENV_OPENCODE_CONFIG_DIR, raising=False)


# Test fixtures
@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Each test gets a workspace owned and cleaned up by pytest."""
    project = tmp_path / test_constants.PATH_TEST_PROJECT
    project.mkdir()
    return project


@pytest.fixture
def sample_codebase(temp_project_dir: Path) -> Dict[str, Path]:
    """Create a sample codebase with various Python modules."""
    if not SAMPLE_AUTH_MODULE:
        pytest.skip("Sample code not available")

    # Create directory structure
    src_dir = temp_project_dir / test_constants.PATH_SRC
    src_dir.mkdir()

    auth_dir = src_dir / test_constants.KEY_AUTH
    auth_dir.mkdir()

    database_dir = src_dir / test_constants.KEY_DATABASE
    database_dir.mkdir()

    api_dir = src_dir / test_constants.KEY_API
    api_dir.mkdir()

    utils_dir = src_dir / test_constants.KEY_UTILS
    utils_dir.mkdir()

    # Create Python files with sample code
    files = {}

    # Authentication module
    auth_file = auth_dir / test_constants.PATH_AUTHENTICATOR_PY
    auth_file.write_text(SAMPLE_AUTH_MODULE)
    files[test_constants.KEY_AUTH] = auth_file

    # Database module
    db_file = database_dir / test_constants.PATH_MANAGER_PY
    db_file.write_text(SAMPLE_DATABASE_MODULE)
    files[test_constants.KEY_DATABASE] = db_file

    # API module
    api_file = api_dir / test_constants.PATH_ENDPOINTS_PY
    api_file.write_text(SAMPLE_API_MODULE)
    files[test_constants.KEY_API] = api_file

    # Utils module
    utils_file = utils_dir / test_constants.PATH_HELPERS_PY
    utils_file.write_text(SAMPLE_UTILS_MODULE)
    files[test_constants.KEY_UTILS] = utils_file

    # Add __init__.py files
    for directory in [src_dir, auth_dir, database_dir, api_dir, utils_dir]:
        init_file = directory / test_constants.PATH_INIT_PY
        init_file.write_text("# Package init file")

    return files


@pytest.fixture
def chunker(temp_project_dir: Path) -> "MultiLanguageChunker":
    """Create a MultiLanguageChunker instance."""
    return MultiLanguageChunker(str(temp_project_dir))
