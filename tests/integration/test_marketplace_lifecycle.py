"""Native uninstall must remove an actual user service without loading models."""

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from code_search_local import constants
from code_search_local.harnesses import read_document, save_document
from code_search_local.lifecycle import guard_paths
from tests import constants as test_constants
from tests.helpers import SYSTEMD_DRIVER, free_port

pytestmark = pytest.mark.packaging
ROOT = Path(__file__).resolve().parents[2]
ID = "code-search-local@code-search-local"
# This acceptance lane tests real systemd and harness lifecycles. Reuse the test interpreter
# and skip only provisioning/model validation; GPU inference has its own acceptance lanes.
DRIVER = SYSTEMD_DRIVER.replace(
    "main(args=",
    """install.install_runtime = lambda *args, **kwargs: Path(sys.executable)
original_run = install.run
def run(args, **kwargs):
    if 'doctor' not in args:
        return original_run(args, **kwargs)
install.run = run
main(args=""",
)


@pytest.mark.parametrize(
    "removal", [constants.HARNESS_CLAUDE, constants.HARNESS_CODEX, constants.INSTALL_ORIGIN_CLI]
)
def test_native_uninstall_removes_running_user_service(tmp_path, removal):
    if (
        os.environ.get(test_constants.ENV_CODE_SEARCH_MARKETPLACES) != constants.ENV_ENABLED
        or os.environ.get(test_constants.ENV_CODE_SEARCH_SYSTEMD_TESTS) != constants.ENV_ENABLED
    ):
        pytest.skip("Set CODE_SEARCH_MARKETPLACES=1 and CODE_SEARCH_SYSTEMD_TESTS=1")
    service = "code-search-local-marketplace-test-" + uuid.uuid4().hex[:12] + constants.PATH_SERVICE
    unit = Path.home() / test_constants.PATH_CONFIG_SYSTEMD_USER / service
    guards = guard_paths(unit)
    catalog = tmp_path / constants.KEY_MARKETPLACE
    for directory in (".claude-plugin", constants.KEY_PLUGINS):
        shutil.copytree(ROOT / directory, catalog / directory)
    env = {**os.environ, constants.ENV_XDG_RUNTIME_DIR: f"/run/user/{os.getuid()}"}
    env.pop(constants.ENV_PYTHONPATH, None)
    Path(env[constants.ENV_CODEX_HOME]).mkdir(parents=True)
    Path(env[constants.ENV_CLAUDE_CONFIG_DIR]).mkdir(parents=True)

    def run(*args, check=True):
        result = subprocess.run(
            [str(arg) for arg in args],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=test_constants.HARNESS_COMMAND_TIMEOUT_SECONDS,
        )
        with (tmp_path / test_constants.PATH_COMMANDS_LOG).open(test_constants.FILE_MODE_A) as log:
            log.write(result.stdout + "\n" + result.stderr + "\n")
        if check:
            assert result.returncode == 0, result.stdout + result.stderr
        return result

    def cli(*args):
        return run(sys.executable, test_constants.SHORT_OPTION_C, DRIVER, service, *args)

    config = Path(env[constants.ENV_XDG_CONFIG_HOME])
    codex_config = Path(env[constants.ENV_CODEX_HOME]) / constants.PATH_CONFIG_TOML
    claude_config = Path(env[constants.ENV_CLAUDE_CONFIG_DIR]) / constants.PATH_CLAUDE_JSON
    opencode_config = config / test_constants.PATH_OPENCODE_OPENCODE_JSONC
    opencode_config.parent.mkdir(parents=True)
    opencode_config.write_text(
        '// keep other servers\n{"mcp":{"other":{"type":"local","command":["other"]}}}'
    )
    storage = tmp_path / constants.KEY_STORAGE
    storage.mkdir(exist_ok=True)
    retained = storage / test_constants.PATH_PRESERVED_INDEX
    retained.write_text("existing index")
    try:
        run(
            constants.HARNESS_CLAUDE,
            constants.KEY_PLUGIN,
            constants.KEY_MARKETPLACE,
            "add",
            catalog,
        )
        run(constants.HARNESS_CLAUDE, constants.KEY_PLUGIN, constants.COMMAND_INSTALL, ID)
        run(
            constants.HARNESS_CODEX,
            constants.KEY_PLUGIN,
            constants.KEY_MARKETPLACE,
            "add",
            catalog,
            constants.OPTION_JSON,
        )
        run(constants.HARNESS_CODEX, constants.KEY_PLUGIN, "add", ID, constants.OPTION_JSON)
        cli(
            "setup",
            constants.OPTION_MARKETPLACE,
            constants.OPTION_AGENT_HARNESS,
            constants.HARNESS_ALL,
            constants.OPTION_BACKEND,
            constants.BACKEND_CPU,
            constants.OPTION_STORAGE,
            storage,
            constants.OPTION_PORT,
            free_port(),
        )
        assert unit.exists() and all(path.exists() for path in guards)
        assert (
            run(
                constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, "is-active", service
            ).stdout.strip()
            == test_constants.VALUE_ACTIVE
        )
        assert (
            "http://127.0.0.1:"
            in run(
                constants.HARNESS_CODEX,
                constants.KEY_MCP,
                "get",
                constants.APPLICATION_NAME,
                constants.OPTION_JSON,
            ).stdout
        )
        assert (
            "http://127.0.0.1:"
            in run(
                constants.HARNESS_CLAUDE, constants.KEY_MCP, "get", constants.APPLICATION_NAME
            ).stdout
        )
        if removal == constants.INSTALL_ORIGIN_CLI:
            cli(constants.COMMAND_UNINSTALL)
            cli(
                constants.COMMAND_UNINSTALL
            )  # repeat is safe even after the recorded installation is gone
            assert (
                '"installed": []'
                in run(
                    constants.HARNESS_CODEX, constants.KEY_PLUGIN, "list", constants.OPTION_JSON
                ).stdout
            )
            assert (
                json.loads(
                    run(
                        constants.HARNESS_CLAUDE,
                        constants.KEY_PLUGIN,
                        "list",
                        constants.OPTION_JSON,
                    ).stdout
                )
                == []
            )
        else:
            args = (
                (constants.OPTION_SCOPE, constants.USER_SCOPE)
                if removal == constants.HARNESS_CLAUDE
                else (constants.OPTION_JSON,)
            )
            if removal == constants.HARNESS_CLAUDE:
                run(removal, constants.KEY_PLUGIN, constants.COMMAND_DISABLE, ID, *args)
            else:
                # Codex's enabled switch is stored in config, without a CLI disable subcommand.
                document = read_document(codex_config)
                document[constants.KEY_PLUGINS][ID][constants.KEY_ENABLED] = False
                save_document(codex_config, document)
            cli(constants.COMMAND_MARKETPLACE_CHECK)
            assert unit.exists(), "Disabling must leave the shared service running"
            if removal == constants.HARNESS_CODEX:
                # Deliberately miss the registry event and exercise the real fallback timer.
                run(
                    constants.COMMAND_SYSTEMCTL,
                    constants.OPTION_USER,
                    constants.COMMAND_STOP,
                    guards[0].name,
                )
            run(
                removal,
                constants.KEY_PLUGIN,
                constants.COMMAND_UNINSTALL
                if removal == constants.HARNESS_CLAUDE
                else constants.COMMAND_REMOVE,
                ID,
                *args,
            )
            deadline = time.monotonic() + test_constants.MARKETPLACE_REMOVAL_TIMEOUT_SECONDS
            while (
                unit.exists()
                or (config / test_constants.PATH_CODE_SEARCH_LOCAL_INSTALLATION_JSON).exists()
            ):
                assert time.monotonic() < deadline, run(
                    constants.COMMAND_JOURNALCTL,
                    constants.OPTION_USER,
                    constants.SHORT_OPTION_U,
                    guards[-1].name,
                    constants.OPTION_NO_PAGER,
                ).stdout
                time.sleep(test_constants.SERVICE_POLL_SECONDS)
            other = (
                constants.HARNESS_CLAUDE
                if removal == constants.HARNESS_CODEX
                else constants.HARNESS_CODEX
            )
            assert ID in run(other, constants.KEY_PLUGIN, "list", constants.OPTION_JSON).stdout
        assert not unit.exists() and not any(path.exists() for path in guards)
        assert (
            run(
                constants.COMMAND_SYSTEMCTL,
                constants.OPTION_USER,
                "is-active",
                service,
                check=False,
            ).returncode
            != 0
        )
        assert constants.APPLICATION_NAME not in read_document(codex_config).get(
            constants.KEY_MCP_SERVERS_LOWERCASE, {}
        )
        assert constants.APPLICATION_NAME not in read_document(claude_config).get(
            constants.KEY_MCP_SERVERS, {}
        )
        assert read_document(opencode_config)[constants.KEY_MCP] == {
            test_constants.KEY_OTHER: {
                constants.KEY_TYPE: "local",
                test_constants.KEY_COMMAND: ["other"],
            }
        }
        assert retained.read_text() == "existing index"
    finally:
        run(
            constants.COMMAND_SYSTEMCTL,
            constants.OPTION_USER,
            constants.COMMAND_DISABLE,
            constants.OPTION_NOW,
            service,
            *(path.name for path in guards[:2]),
            check=False,
        )
        run(
            constants.COMMAND_SYSTEMCTL,
            constants.OPTION_USER,
            constants.COMMAND_STOP,
            guards[-1].name,
            check=False,
        )
        for path in [unit, *guards]:
            path.unlink(missing_ok=True)
        run(
            constants.COMMAND_SYSTEMCTL,
            constants.OPTION_USER,
            constants.COMMAND_DAEMON_RELOAD,
            check=False,
        )
        run(
            constants.HARNESS_CLAUDE,
            constants.KEY_PLUGIN,
            constants.COMMAND_UNINSTALL,
            ID,
            constants.OPTION_SCOPE,
            constants.USER_SCOPE,
            check=False,
        )
        run(
            constants.HARNESS_CODEX,
            constants.KEY_PLUGIN,
            constants.COMMAND_REMOVE,
            ID,
            constants.OPTION_JSON,
            check=False,
        )
