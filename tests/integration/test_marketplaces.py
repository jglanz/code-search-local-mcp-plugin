"""Exercise native marketplace installation in isolated client configurations."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from code_search_local import constants
from tests import constants as test_constants

ROOT = Path(__file__).resolve().parents[2]


def plugin_command(run, harness, *arguments):
    flags = (constants.OPTION_JSON,) if harness == constants.HARNESS_CODEX else ()
    return run(harness, constants.KEY_PLUGIN, *arguments, *flags)


@pytest.mark.packaging
def test_both_native_marketplaces(tmp_path):
    if os.environ.get(test_constants.ENV_CODE_SEARCH_MARKETPLACES) != constants.ENV_ENABLED:
        pytest.skip("Set CODE_SEARCH_MARKETPLACES=1 with Claude and Codex CLIs installed")
    catalog = tmp_path / test_constants.PATH_LOCAL_MARKETPLACE
    catalog.mkdir()
    (tmp_path / constants.HARNESS_CODEX).mkdir()
    (tmp_path / constants.HARNESS_CLAUDE).mkdir()
    for directory in (".claude-plugin", constants.KEY_PLUGINS):
        shutil.copytree(ROOT / directory, catalog / directory)
    env = {
        **os.environ,
        constants.ENV_CODEX_HOME: str(tmp_path / constants.HARNESS_CODEX),
        constants.ENV_CLAUDE_CONFIG_DIR: str(tmp_path / constants.HARNESS_CLAUDE),
    }

    def run(*args):
        result = subprocess.run(
            [str(a) for a in args],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=test_constants.HARNESS_COMMAND_TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    plugin_command(
        run,
        constants.HARNESS_CLAUDE,
        "validate",
        catalog / test_constants.PATH_CLAUDE_PLUGIN_MARKETPLACE_JSON,
    )
    plugin_command(run, constants.HARNESS_CLAUDE, constants.KEY_MARKETPLACE, "add", catalog)
    plugin_command(
        run,
        constants.HARNESS_CLAUDE,
        constants.COMMAND_INSTALL,
        "code-search-local@code-search-local",
    )
    assert constants.APPLICATION_NAME in plugin_command(
        run, constants.HARNESS_CLAUDE, "list", constants.OPTION_JSON
    )
    plugin_command(run, constants.HARNESS_CODEX, constants.KEY_MARKETPLACE, "add", catalog)
    plugin_command(run, constants.HARNESS_CODEX, "add", "code-search-local@code-search-local")
    assert constants.APPLICATION_NAME in plugin_command(run, constants.HARNESS_CODEX, "list")
    for client in (constants.HARNESS_CLAUDE, constants.HARNESS_CODEX):
        skills = list((tmp_path / client).rglob(test_constants.PATH_SKILL_MD))
        assert any("code-search-local==1.0.0" in skill.read_text() for skill in skills)
    # Removing either plugin must not remove the other client's installed package.
    plugin_command(
        run,
        constants.HARNESS_CLAUDE,
        constants.COMMAND_UNINSTALL,
        "code-search-local@code-search-local",
    )
    assert constants.APPLICATION_NAME in plugin_command(run, constants.HARNESS_CODEX, "list")
    plugin_command(
        run,
        constants.HARNESS_CODEX,
        constants.COMMAND_REMOVE,
        "code-search-local@code-search-local",
    )
    (tmp_path / test_constants.PATH_MARKETPLACE_VALIDATION_JSON).write_text(
        json.dumps({constants.HARNESS_CLAUDE: "passed", constants.HARNESS_CODEX: "passed"})
    )
