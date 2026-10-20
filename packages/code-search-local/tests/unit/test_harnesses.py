import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from code_search_local import constants, harnesses, install, lifecycle
from code_search_local.cli import main
from code_search_local.config import Settings
from code_search_local.service import token_for
from tests import constants as test_constants

NAME = harnesses.NAME
ID = NAME + "@code-search-local"


@pytest.mark.parametrize(
    "options,expected",
    [
        ((), ()),
        ((constants.HARNESS_NONE,), ()),
        ((constants.HARNESS_ALL,), harnesses.HARNESSES),
        (
            (constants.HARNESS_CLAUDE, constants.HARNESS_CODEX, constants.HARNESS_CLAUDE),
            (constants.HARNESS_CODEX, constants.HARNESS_CLAUDE),
        ),
    ],
)
def test_selection(options, expected):
    assert harnesses.selection(options) == expected


@pytest.mark.parametrize(
    "options",
    [
        (constants.HARNESS_NONE, constants.HARNESS_CLAUDE),
        (constants.HARNESS_NONE, constants.HARNESS_ALL),
        (constants.STATUS_UNKNOWN,),
    ],
)
def test_invalid_selection(options):
    with pytest.raises(ValueError):
        harnesses.selection(options)


def test_cli_harness_defaults_multiple_and_conflicts(monkeypatch):
    original_setup = install.setup
    call = Mock(return_value={})
    monkeypatch.setattr(install, "setup", call)
    runner = CliRunner()
    for args, expected in [
        ([], ()),
        ([constants.OPTION_AGENT_HARNESS, constants.HARNESS_NONE], ()),
        (
            [
                constants.OPTION_AGENT_HARNESS,
                constants.HARNESS_CODEX,
                constants.OPTION_AGENT_HARNESS,
                constants.HARNESS_CLAUDE,
            ],
            (constants.HARNESS_CODEX, constants.HARNESS_CLAUDE),
        ),
        ([constants.OPTION_AGENT_HARNESS, constants.HARNESS_ALL], harnesses.HARNESSES),
        (
            [constants.OPTION_CLIENT, constants.LEGACY_HARNESS_BOTH],
            (constants.HARNESS_CODEX, constants.HARNESS_CLAUDE),
        ),
    ]:
        assert runner.invoke(main, ["setup", *args]).exit_code == 0
        assert call.call_args.kwargs[constants.KEY_AGENT_HARNESS] == expected
    for args in [
        [
            constants.OPTION_CLIENT,
            constants.LEGACY_HARNESS_BOTH,
            constants.OPTION_AGENT_HARNESS,
            constants.HARNESS_CLAUDE,
        ],
        [
            constants.OPTION_AGENT_HARNESS,
            constants.HARNESS_NONE,
            constants.OPTION_AGENT_HARNESS,
            constants.HARNESS_CODEX,
        ],
    ]:
        assert runner.invoke(main, ["setup", *args]).exit_code == 2
    with pytest.raises(ValueError, match="cannot be combined"):
        original_setup(
            Settings(),
            client=constants.LEGACY_HARNESS_BOTH,
            agent_harness=(constants.HARNESS_CODEX,),
        )


def test_no_selection_touches_no_configs(tmp_path):
    harnesses.register(Settings(storage=str(tmp_path / test_constants.PATH_UNUSED)), [])
    assert list(tmp_path.iterdir()) == []


def test_all_harnesses_replace_old_mcp_and_keep_unrelated(tmp_path):
    selected = harnesses.targets()
    originals = {}
    for target, key in zip(
        selected,
        (constants.KEY_MCP_SERVERS_LOWERCASE, constants.KEY_MCP_SERVERS, constants.KEY_MCP),
    ):
        path = Path(target[constants.KEY_PRIMARY])
        harnesses.save_document(
            path,
            {
                key: {
                    NAME: {test_constants.KEY_COMMAND: "old"},
                    test_constants.KEY_OTHER: {test_constants.KEY_COMMAND: "keep"},
                }
            },
        )
        originals[path] = path.read_text()
    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE))
    token = token_for(settings.root, create=True)
    harnesses.register(settings, selected)
    for target, key in zip(
        selected,
        (constants.KEY_MCP_SERVERS_LOWERCASE, constants.KEY_MCP_SERVERS, constants.KEY_MCP),
    ):
        path = Path(target[constants.KEY_PRIMARY])
        doc = harnesses.read_document(path)
        assert doc[key][test_constants.KEY_OTHER] == {test_constants.KEY_COMMAND: "keep"}
        assert test_constants.KEY_COMMAND not in doc[key][NAME]
        assert doc[key][NAME][constants.KEY_URL] == settings.url + constants.MCP_ENDPOINT
        assert token in path.read_text()
        assert (
            path.with_name(path.name + constants.PATH_CODE_SEARCH_LOCAL_BAK).read_text()
            == originals[path]
        )
    assert (
        harnesses.read_document(selected[-1][constants.KEY_PRIMARY])[constants.KEY_MCP][NAME][
            constants.KEY_OAUTH
        ]
        is False
    )


def test_jsonc_overrides_and_duplicate_registration_cleanup(tmp_path, monkeypatch):
    config = tmp_path / test_constants.PATH_CONFIG_OPENCODE_OPENCODE_JSONC
    config.parent.mkdir(parents=True)
    config.write_text('// comment\n{"mcp": {"code-search-local": {"type":"local"}, "other": {}},}')
    custom = tmp_path / test_constants.VALUE_CUSTOM
    explicit = tmp_path / test_constants.PATH_EXPLICIT_JSONC
    monkeypatch.setenv(constants.ENV_OPENCODE_CONFIG_DIR, str(custom))
    monkeypatch.setenv(constants.ENV_OPENCODE_CONFIG, str(explicit))
    target = harnesses.targets((constants.HARNESS_OPENCODE,))[0]
    assert target[constants.KEY_PRIMARY] == str(explicit)
    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE))
    token_for(settings.root, create=True)
    harnesses.register(settings, [target])
    assert NAME not in harnesses.read_document(config)[constants.KEY_MCP]
    assert test_constants.KEY_OTHER in harnesses.read_document(config)[constants.KEY_MCP]
    assert NAME in harnesses.read_document(explicit)[constants.KEY_MCP]
    assert (
        config.with_name(config.name + constants.PATH_CODE_SEARCH_LOCAL_BAK)
        .read_text()
        .startswith("// comment")
    )
    harnesses.unregister(target)
    assert NAME not in harnesses.read_document(explicit)[constants.KEY_MCP]
    # If neither custom config exists, create a JSON config inside the custom directory.
    monkeypatch.delenv(constants.ENV_OPENCODE_CONFIG)
    config.unlink()
    assert harnesses.targets((constants.HARNESS_OPENCODE,))[0][constants.KEY_PRIMARY] == str(
        custom / constants.PATH_OPENCODE_JSON
    )


def test_default_home_paths_and_invalid_document(tmp_path, monkeypatch):
    monkeypatch.delenv(constants.ENV_CODEX_HOME)
    monkeypatch.delenv(constants.ENV_CLAUDE_CONFIG_DIR)
    monkeypatch.delenv(constants.ENV_XDG_CONFIG_HOME)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    codex, claude, opencode = harnesses.targets()
    assert codex[constants.KEY_PRIMARY] == str(
        tmp_path / test_constants.PATH_CODEX_CONFIG_TOML_LOWERCASE
    )
    assert claude[constants.KEY_PRIMARY] == str(tmp_path / constants.PATH_CLAUDE_JSON)
    assert opencode[constants.KEY_PRIMARY] == str(
        tmp_path / test_constants.PATH_CONFIG_OPENCODE_OPENCODE_JSON_LOWERCASE
    )
    assert constants.ENV_CLAUDE_CONFIG_DIR not in harnesses.command_env(claude)
    path = Path(claude[constants.KEY_PRIMARY])
    path.write_text("[]")
    with pytest.raises(ValueError, match="must be an object"):
        harnesses.read_document(path)


@pytest.mark.parametrize(constants.KEY_NAME, [constants.HARNESS_CODEX, constants.HARNESS_CLAUDE])
def test_native_plugin_removal_and_marketplace_preservation(tmp_path, monkeypatch, name):
    target = harnesses.targets((name,))[0]
    if name == constants.HARNESS_CODEX:
        harnesses.save_document(
            target[constants.KEY_PRIMARY],
            {
                constants.KEY_PLUGINS: {
                    ID: {constants.KEY_ENABLED: False},
                    test_constants.KEY_OTHER_MARKET: {constants.KEY_ENABLED: True},
                }
            },
        )
    else:
        harnesses.save_document(
            Path(target[constants.KEY_ROOT]) / constants.PATH_PLUGINS_INSTALLED_PLUGINS_JSON,
            {constants.KEY_PLUGINS: {ID: [{constants.KEY_SCOPE: constants.USER_SCOPE}]}},
        )
        harnesses.save_document(
            Path(target[constants.KEY_ROOT]) / constants.PATH_SETTINGS_JSON,
            {constants.KEY_ENABLED_PLUGINS: {ID: False, test_constants.KEY_OTHER_MARKET: True}},
        )
    commands = Mock()
    monkeypatch.setattr(harnesses.shutil, "which", lambda _: "/bin/tool")
    monkeypatch.setattr(harnesses.subprocess, "run", commands)
    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE))
    token_for(settings.root, create=True)
    harnesses.register(settings, [target], marketplace=True)
    commands.assert_not_called()
    assert ID in harnesses.plugins(target), "Disabled plugins are still installed"
    harnesses.register(settings, [target])
    args = commands.call_args.args[0]
    assert args[:2] == [name, constants.KEY_PLUGIN] and ID in args
    assert (
        commands.call_args.kwargs[constants.KEY_ENV][
            constants.ENV_CODEX_HOME
            if name == constants.HARNESS_CODEX
            else constants.ENV_CLAUDE_CONFIG_DIR
        ]
        == target[constants.KEY_ROOT]
    )
    if name == constants.HARNESS_CLAUDE:
        assert constants.OPTION_SCOPE in args and constants.OPTION_KEEP_DATA in args
        assert harnesses.read_document(
            Path(target[constants.KEY_ROOT]) / constants.PATH_SETTINGS_JSON
        )[constants.KEY_ENABLED_PLUGINS] == {test_constants.KEY_OTHER_MARKET: True}
    else:
        assert harnesses.read_document(target[constants.KEY_PRIMARY])[constants.KEY_PLUGINS] == {
            test_constants.KEY_OTHER_MARKET: {constants.KEY_ENABLED: True}
        }


def test_missing_cli_cleans_own_plugin_only(tmp_path, monkeypatch):
    monkeypatch.setattr(harnesses.shutil, "which", lambda _: None)
    codex, claude, opencode = harnesses.targets()
    registry = Path(claude[constants.KEY_ROOT]) / constants.PATH_PLUGINS_INSTALLED_PLUGINS_JSON
    harnesses.save_document(
        registry,
        {
            constants.KEY_PLUGINS: {
                ID: [
                    {constants.KEY_SCOPE: constants.USER_SCOPE},
                    {constants.KEY_SCOPE: constants.KEY_PROJECT},
                ],
                NAME: [{constants.KEY_SCOPE: constants.USER_SCOPE}],
                test_constants.KEY_OTHER_MARKET: [{constants.KEY_SCOPE: constants.USER_SCOPE}],
            }
        },
    )
    harnesses.save_document(
        codex[constants.KEY_PRIMARY],
        {
            constants.KEY_PLUGINS: {
                ID: {constants.KEY_ENABLED: True},
                test_constants.KEY_OTHER_MARKET: {constants.KEY_ENABLED: True},
            }
        },
    )
    harnesses.save_document(
        opencode[constants.KEY_PRIMARY], {constants.KEY_PLUGIN: [NAME + "@1.0.0", "unrelated"]}
    )
    for target in (codex, claude, opencode):
        harnesses.unregister(target)
        harnesses.unregister(target)
    assert harnesses.read_document(registry)[constants.KEY_PLUGINS] == {
        ID: [{constants.KEY_SCOPE: constants.KEY_PROJECT}],
        test_constants.KEY_OTHER_MARKET: [{constants.KEY_SCOPE: constants.USER_SCOPE}],
    }
    assert harnesses.read_document(opencode[constants.KEY_PRIMARY])[constants.KEY_PLUGIN] == [
        "unrelated"
    ]
    assert (
        "other@market"
        in harnesses.read_document(codex[constants.KEY_PRIMARY])[constants.KEY_PLUGINS]
    )


def test_registration_failure_removes_new_config(tmp_path, monkeypatch):
    target = harnesses.targets((constants.HARNESS_OPENCODE,))[0]
    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE))
    token_for(settings.root, create=True)
    monkeypatch.setattr(harnesses, "save_document", Mock(side_effect=OSError("write failed")))
    with pytest.raises(OSError):
        harnesses.register(settings, [target])
    assert not Path(target[constants.KEY_PRIMARY]).exists()


def test_cli_uninstall_and_internal_check(monkeypatch):
    call = Mock(return_value={constants.KEY_SERVICE_REMOVED: "test.service"})
    monkeypatch.setattr(lifecycle, constants.COMMAND_UNINSTALL, call)
    runner = CliRunner()
    result = runner.invoke(main, [constants.COMMAND_UNINSTALL])
    assert (
        result.exit_code == 0
        and json.loads(result.stdout)[constants.KEY_SERVICE_REMOVED]
        == test_constants.VALUE_TEST_SERVICE
    )
    call.side_effect = RuntimeError("needs retry")
    assert runner.invoke(main, [constants.COMMAND_UNINSTALL]).exit_code == 1
    monkeypatch.setattr(
        lifecycle, "marketplace_check", lambda: {constants.KEY_STATUS: constants.STATUS_INSTALLED}
    )
    assert runner.invoke(main, [constants.COMMAND_MARKETPLACE_CHECK]).exit_code == 0
