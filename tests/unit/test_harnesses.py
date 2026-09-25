import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from code_search_local import harnesses, install, lifecycle
from code_search_local.cli import main
from code_search_local.config import Settings
from code_search_local.service import token_for

NAME = harnesses.NAME
ID = NAME + "@code-search-local"


@pytest.mark.parametrize(
    "options,expected",
    [
        ((), ()),
        (("none",), ()),
        (("all",), harnesses.HARNESSES),
        (("claude", "codex", "claude"), ("codex", "claude")),
    ],
)
def test_selection(options, expected):
    assert harnesses.selection(options) == expected


@pytest.mark.parametrize("options", [("none", "claude"), ("none", "all"), ("unknown",)])
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
        (["--agent-harness", "none"], ()),
        (["--agent-harness", "codex", "--agent-harness", "claude"], ("codex", "claude")),
        (["--agent-harness", "all"], harnesses.HARNESSES),
        (["--client", "both"], ("codex", "claude")),
    ]:
        assert runner.invoke(main, ["setup", *args]).exit_code == 0
        assert call.call_args.kwargs["agent_harness"] == expected
    for args in [
        ["--client", "both", "--agent-harness", "claude"],
        ["--agent-harness", "none", "--agent-harness", "codex"],
    ]:
        assert runner.invoke(main, ["setup", *args]).exit_code == 2
    with pytest.raises(ValueError, match="cannot be combined"):
        original_setup(Settings(), client="both", agent_harness=("codex",))


def test_no_selection_touches_no_configs(tmp_path):
    harnesses.register(Settings(storage=str(tmp_path / "unused")), [])
    assert list(tmp_path.iterdir()) == []


def test_all_harnesses_replace_old_mcp_and_keep_unrelated(tmp_path):
    selected = harnesses.targets()
    originals = {}
    for target, key in zip(selected, ("mcp_servers", "mcpServers", "mcp")):
        path = Path(target["primary"])
        harnesses.save_document(
            path, {key: {NAME: {"command": "old"}, "other": {"command": "keep"}}}
        )
        originals[path] = path.read_text()
    settings = Settings(storage=str(tmp_path / "state"))
    token = token_for(settings.root, create=True)
    harnesses.register(settings, selected)
    for target, key in zip(selected, ("mcp_servers", "mcpServers", "mcp")):
        path = Path(target["primary"])
        doc = harnesses.read_document(path)
        assert doc[key]["other"] == {"command": "keep"}
        assert "command" not in doc[key][NAME]
        assert doc[key][NAME]["url"] == settings.url + "/mcp"
        assert token in path.read_text()
        assert path.with_name(path.name + ".code-search-local.bak").read_text() == originals[path]
    assert harnesses.read_document(selected[-1]["primary"])["mcp"][NAME]["oauth"] is False


def test_jsonc_overrides_and_duplicate_registration_cleanup(tmp_path, monkeypatch):
    config = tmp_path / "config/opencode/opencode.jsonc"
    config.parent.mkdir(parents=True)
    config.write_text('// comment\n{"mcp": {"code-search-local": {"type":"local"}, "other": {}},}')
    custom = tmp_path / "custom"
    explicit = tmp_path / "explicit.jsonc"
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(custom))
    monkeypatch.setenv("OPENCODE_CONFIG", str(explicit))
    target = harnesses.targets(("opencode",))[0]
    assert target["primary"] == str(explicit)
    settings = Settings(storage=str(tmp_path / "state"))
    token_for(settings.root, create=True)
    harnesses.register(settings, [target])
    assert NAME not in harnesses.read_document(config)["mcp"]
    assert "other" in harnesses.read_document(config)["mcp"]
    assert NAME in harnesses.read_document(explicit)["mcp"]
    assert (
        config.with_name(config.name + ".code-search-local.bak")
        .read_text()
        .startswith("// comment")
    )
    harnesses.unregister(target)
    assert NAME not in harnesses.read_document(explicit)["mcp"]
    # If neither custom config exists, create a JSON config inside the custom directory.
    monkeypatch.delenv("OPENCODE_CONFIG")
    config.unlink()
    assert harnesses.targets(("opencode",))[0]["primary"] == str(custom / "opencode.json")


def test_default_home_paths_and_invalid_document(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_HOME")
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    codex, claude, opencode = harnesses.targets()
    assert codex["primary"] == str(tmp_path / ".codex/config.toml")
    assert claude["primary"] == str(tmp_path / ".claude.json")
    assert opencode["primary"] == str(tmp_path / ".config/opencode/opencode.json")
    assert "CLAUDE_CONFIG_DIR" not in harnesses.command_env(claude)
    path = Path(claude["primary"])
    path.write_text("[]")
    with pytest.raises(ValueError, match="must be an object"):
        harnesses.read_document(path)


@pytest.mark.parametrize("name", ["codex", "claude"])
def test_native_plugin_removal_and_marketplace_preservation(tmp_path, monkeypatch, name):
    target = harnesses.targets((name,))[0]
    if name == "codex":
        harnesses.save_document(
            target["primary"],
            {"plugins": {ID: {"enabled": False}, "other@market": {"enabled": True}}},
        )
    else:
        harnesses.save_document(
            Path(target["root"]) / "plugins/installed_plugins.json",
            {"plugins": {ID: [{"scope": "user"}]}},
        )
        harnesses.save_document(
            Path(target["root"]) / "settings.json",
            {"enabledPlugins": {ID: False, "other@market": True}},
        )
    commands = Mock()
    monkeypatch.setattr(harnesses.shutil, "which", lambda _: "/bin/tool")
    monkeypatch.setattr(harnesses.subprocess, "run", commands)
    settings = Settings(storage=str(tmp_path / "state"))
    token_for(settings.root, create=True)
    harnesses.register(settings, [target], marketplace=True)
    commands.assert_not_called()
    assert ID in harnesses.plugins(target), "Disabled plugins are still installed"
    harnesses.register(settings, [target])
    args = commands.call_args.args[0]
    assert args[:2] == [name, "plugin"] and ID in args
    assert (
        commands.call_args.kwargs["env"]["CODEX_HOME" if name == "codex" else "CLAUDE_CONFIG_DIR"]
        == target["root"]
    )
    if name == "claude":
        assert "--scope" in args and "--keep-data" in args
        assert harnesses.read_document(Path(target["root"]) / "settings.json")[
            "enabledPlugins"
        ] == {"other@market": True}
    else:
        assert harnesses.read_document(target["primary"])["plugins"] == {
            "other@market": {"enabled": True}
        }


def test_missing_cli_cleans_own_plugin_only(tmp_path, monkeypatch):
    monkeypatch.setattr(harnesses.shutil, "which", lambda _: None)
    codex, claude, opencode = harnesses.targets()
    registry = Path(claude["root"]) / "plugins/installed_plugins.json"
    harnesses.save_document(
        registry,
        {
            "plugins": {
                ID: [{"scope": "user"}, {"scope": "project"}],
                NAME: [{"scope": "user"}],
                "other@market": [{"scope": "user"}],
            }
        },
    )
    harnesses.save_document(
        codex["primary"], {"plugins": {ID: {"enabled": True}, "other@market": {"enabled": True}}}
    )
    harnesses.save_document(opencode["primary"], {"plugin": [NAME + "@1.0.0", "unrelated"]})
    for target in (codex, claude, opencode):
        harnesses.unregister(target)
        harnesses.unregister(target)
    assert harnesses.read_document(registry)["plugins"] == {
        ID: [{"scope": "project"}],
        "other@market": [{"scope": "user"}],
    }
    assert harnesses.read_document(opencode["primary"])["plugin"] == ["unrelated"]
    assert "other@market" in harnesses.read_document(codex["primary"])["plugins"]


def test_registration_failure_removes_new_config(tmp_path, monkeypatch):
    target = harnesses.targets(("opencode",))[0]
    settings = Settings(storage=str(tmp_path / "state"))
    token_for(settings.root, create=True)
    monkeypatch.setattr(harnesses, "save_document", Mock(side_effect=OSError("write failed")))
    with pytest.raises(OSError):
        harnesses.register(settings, [target])
    assert not Path(target["primary"]).exists()


def test_cli_uninstall_and_internal_check(monkeypatch):
    call = Mock(return_value={"service_removed": "test.service"})
    monkeypatch.setattr(lifecycle, "uninstall", call)
    runner = CliRunner()
    result = runner.invoke(main, ["uninstall"])
    assert result.exit_code == 0 and json.loads(result.stdout)["service_removed"] == "test.service"
    call.side_effect = RuntimeError("needs retry")
    assert runner.invoke(main, ["uninstall"]).exit_code == 1
    monkeypatch.setattr(lifecycle, "marketplace_check", lambda: {"status": "installed"})
    assert runner.invoke(main, ["marketplace-check"]).exit_code == 0
