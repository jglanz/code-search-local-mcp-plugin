"""Verify generated configuration with OpenCode's real HTTP MCP client."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from code_search_local import constants, harnesses
from code_search_local.client import Client
from code_search_local.config import Settings
from tests import constants as test_constants
from tests.helpers import free_port, start_test_daemon, stop_process, wait_healthy


@pytest.mark.clients
@pytest.mark.parametrize("profile", ["global_jsonc", "custom_file", "custom_directory"])
def test_opencode_connects_replaces_and_unregisters(tmp_path, monkeypatch, profile):
    if os.environ.get(test_constants.ENV_CODE_SEARCH_OPENCODE_TESTS) != constants.ENV_ENABLED:
        pytest.skip("Set CODE_SEARCH_OPENCODE_TESTS=1 with opencode on PATH")
    executable = shutil.which(
        os.environ.get(test_constants.ENV_CODE_SEARCH_OPENCODE_BIN, constants.HARNESS_OPENCODE)
    )
    assert executable, "OpenCode CLI is required for this acceptance lane"
    for name in list(os.environ):
        if name.startswith("OPENCODE_"):
            monkeypatch.delenv(name)
    for name, path in {
        test_constants.ENV_HOME: tmp_path / test_constants.PATH_HOME,
        test_constants.ENV_XDG_CACHE_HOME: tmp_path / test_constants.PATH_CACHE,
        test_constants.ENV_XDG_DATA_HOME: tmp_path / test_constants.KEY_DATA,
        test_constants.ENV_XDG_STATE_HOME: tmp_path / test_constants.KEY_STATE,
    }.items():
        path.mkdir()
        monkeypatch.setenv(name, str(path))
    monkeypatch.setenv(test_constants.ENV_OPENCODE_DISABLE_AUTOUPDATE, constants.BOOLEAN_TRUE)
    monkeypatch.setenv(test_constants.ENV_OPENCODE_DISABLE_DEFAULT_PLUGINS, constants.BOOLEAN_TRUE)
    global_config = (
        Path(os.environ[constants.ENV_XDG_CONFIG_HOME])
        / test_constants.PATH_OPENCODE_OPENCODE_JSONC
    )
    config = global_config
    if profile == test_constants.VALUE_CUSTOM_FILE:
        config = tmp_path / test_constants.PATH_CUSTOM_JSONC
        monkeypatch.setenv(constants.ENV_OPENCODE_CONFIG, str(config))
    elif profile == test_constants.VALUE_CUSTOM_DIRECTORY:
        config = tmp_path / test_constants.PATH_CUSTOM_OPENCODE_JSONC
        monkeypatch.setenv(constants.ENV_OPENCODE_CONFIG_DIR, str(config.parent))
    config.parent.mkdir(parents=True, exist_ok=True)
    original = (
        '// preserve original in backup\n{"mcp": {'
        '"code-search-local": {"type":"local","command":["stale"],"enabled":false},'
        '"unrelated": {"type":"local","command":["unused"],"enabled":false}}}'
    )
    config.write_text(original)
    settings = Settings(
        storage=str(tmp_path / constants.KEY_STORAGE), port=free_port(), watch=False
    )
    with (tmp_path / test_constants.PATH_DAEMON_LOG).open(test_constants.FILE_MODE_W) as log:
        process = start_test_daemon(settings, log)
        try:
            wait_healthy(process, Client(settings), log)
            target = harnesses.targets((constants.HARNESS_OPENCODE,))[0]
            harnesses.register(settings, [target])
            assert (
                config.with_name(config.name + constants.PATH_CODE_SEARCH_LOCAL_BAK).read_text()
                == original
            )

            def list_servers():
                result = subprocess.run(
                    [executable, constants.KEY_MCP, "list"],
                    cwd=tmp_path,
                    env=os.environ.copy(),
                    capture_output=True,
                    text=True,
                    timeout=test_constants.OPENCODE_COMMAND_TIMEOUT_SECONDS,
                )
                output = re.sub(test_constants.PATTERN_X1B_0, "", result.stdout + result.stderr)
                assert result.returncode == 0, output
                return output

            assert re.search(test_constants.PATTERN_CODE_SEARCH_LOCAL_S_CONNECTED, list_servers())
            harnesses.register(settings, [target])
            assert re.search(test_constants.PATTERN_CODE_SEARCH_LOCAL_S_CONNECTED, list_servers())
            harnesses.unregister(target)
            harnesses.unregister(target)
            output = list_servers()
            assert (
                constants.APPLICATION_NAME not in output and test_constants.KEY_UNRELATED in output
            )
            assert harnesses.read_document(config)[constants.KEY_MCP] == {
                test_constants.KEY_UNRELATED: {
                    constants.KEY_TYPE: "local",
                    test_constants.KEY_COMMAND: ["unused"],
                    constants.KEY_ENABLED: False,
                }
            }
        finally:
            stop_process(process, timeout=test_constants.PROCESS_SHUTDOWN_TIMEOUT_SECONDS)
