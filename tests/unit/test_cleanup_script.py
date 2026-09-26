"""Exercise discovery only. Never execute this script's destructive apply branch."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from code_search_local import constants
from tests import constants as test_constants

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/clean_existing_installations_and_configs.py"
spec = importlib.util.spec_from_file_location("cleanup_installations", SCRIPT)
cleanup = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cleanup
spec.loader.exec_module(cleanup)


def write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    root = tmp_path / test_constants.PATH_HOME
    root.mkdir()
    for key in (
        constants.ENV_CODEX_HOME,
        constants.ENV_CLAUDE_CONFIG_DIR,
        constants.ENV_OPENCODE_CONFIG,
        constants.ENV_OPENCODE_CONFIG_DIR,
        constants.ENV_CODE_SEARCH_STORAGE,
        test_constants.ENV_CLAUDE_CONTEXT_LOCAL_STORAGE,
        test_constants.ENV_CLAUDE_CODE_SEARCH_STORAGE,
        test_constants.ENV_UV_TOOL_DIR,
        test_constants.ENV_UV_TOOL_BIN_DIR,
        test_constants.ENV_UV_CACHE_DIR,
        test_constants.ENV_PIPX_HOME,
        test_constants.ENV_PIPX_BIN_DIR,
        test_constants.ENV_NPM_CONFIG_PREFIX,
        "npm_config_prefix",
        test_constants.ENV_SUDO_USER,
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in {
        test_constants.ENV_HOME: root,
        constants.ENV_XDG_CONFIG_HOME: root / constants.PATH_CONFIG,
        test_constants.ENV_XDG_CACHE_HOME: root / test_constants.PATH_CACHE_LOWERCASE,
        test_constants.ENV_XDG_DATA_HOME: root / test_constants.PATH_LOCAL_SHARE,
        test_constants.ENV_PATH: root / test_constants.PATH_LOCAL_BIN,
    }.items():
        monkeypatch.setenv(key, str(value))

    def readonly(args, **kwargs):
        assert args[0] in {constants.COMMAND_SYSTEMCTL, "crontab"}
        assert test_constants.VALUE_LIST_UNITS in args or test_constants.SHORT_OPTION_L in args
        return SimpleNamespace(
            returncode=0, stdout="[]" if args[0] == constants.COMMAND_SYSTEMCTL else "", stderr=""
        )

    monkeypatch.setattr(cleanup, "readonly", readonly)
    return root


def invoke_cleanup_dry_run(home, *flags):
    return CliRunner().invoke(
        cleanup.main,
        [
            test_constants.OPTION_DRY_RUN,
            constants.OPTION_JSON,
            test_constants.OPTION_HOME,
            str(home),
            constants.OPTION_SCOPE,
            constants.USER_SCOPE,
            *flags,
        ],
    )


def test_dry_run_has_no_mutations_and_redacts_values(home, monkeypatch):
    config = write(
        home / test_constants.PATH_CONFIG_OPENCODE_OPENCODE_JSONC_LOWERCASE,
        """{
      // Comment and unrelated registration must survive in the backup, when applied.
      "mcp": {"ClAuDe_Context_Local": {"type":"local", "command":["old-server"]},
              "keep": {"url":"https://example.test", "headers":{"token":"SECRET_VALUE"}}}
    }""",
    )
    unit = write(
        home / test_constants.PATH_CONFIG_SYSTEMD_USER_CODE_SEARCH_LOCAL_SERVICE,
        "[Service]\nExecStart=code-search-local serve\n",
    )
    backup = home / test_constants.PATH_BACKUPS
    before = {
        path: path.read_bytes()
        for path in home.rglob(test_constants.PATH_PATTERN)
        if path.is_file()
    }
    monkeypatch.setattr(cleanup.Scanner, "processes", lambda self: None)

    def forbidden(*args, **kwargs):
        pytest.fail("Dry-run attempted a mutation")

    monkeypatch.setattr(cleanup, "apply_plan", forbidden)
    monkeypatch.setattr(cleanup, "atomic_write", forbidden)
    monkeypatch.setattr(cleanup.os, "kill", forbidden)
    monkeypatch.setattr(cleanup.shutil, "rmtree", forbidden)
    monkeypatch.setattr(cleanup.subprocess, "run", forbidden)
    result = invoke_cleanup_dry_run(home, test_constants.OPTION_BACKUP_DIR, str(backup))
    assert result.exit_code == 0, result.output
    assert test_constants.ENV_SECRET_VALUE not in result.output
    report = json.loads(result.output)
    assert report[test_constants.KEY_DRY_RUN] is True
    assert report[test_constants.KEY_COUNTS][test_constants.KEY_UNIT] == 1
    assert any(
        a[test_constants.KEY_KIND] == test_constants.VALUE_EDIT
        and a[constants.KEY_TARGET] == str(config)
        for a in report[test_constants.KEY_ACTIONS]
    )
    assert any(
        a[test_constants.KEY_KIND] == constants.COMMAND_REMOVE
        and a[constants.KEY_TARGET] == str(unit)
        for a in report[test_constants.KEY_ACTIONS]
    )
    assert not backup.exists()
    assert before == {
        path: path.read_bytes()
        for path in home.rglob(test_constants.PATH_PATTERN)
        if path.is_file()
    }


@pytest.mark.parametrize(
    constants.KEY_NAME,
    [
        constants.APPLICATION_NAME,
        test_constants.ENV_CODE_SEARCH_LOCAL,
        "Claude-Context-Local",
        "claude_context_local",
    ],
)
def test_registration_aliases_preserve_other_entries(home, name):
    doc = {
        constants.KEY_MCP_SERVERS: {
            name: {test_constants.KEY_COMMAND: constants.SERVER_EXTRA},
            test_constants.KEY_ALIASED: {
                test_constants.KEY_COMMAND: "uvx",
                test_constants.KEY_ARGS: [name],
            },
            test_constants.KEY_KEEP: {
                test_constants.KEY_DESCRIPTION: name,
                test_constants.KEY_COMMAND: "other",
            },
        },
        test_constants.KEY_PERMISSIONS: {
            test_constants.KEY_ALLOW: [f"mcp__{name}__search", "Read"]
        },
        constants.KEY_ENV: {
            constants.ENV_CODE_SEARCH_STORAGE: "/path",
            test_constants.ENV_KEEP: constants.BOOLEAN_YES,
        },
        constants.KEY_PLUGINS: {
            name + "@market": True,
            test_constants.KEY_SHARED_MARKETPLACE: {
                constants.KEY_PLUGINS: [{constants.KEY_NAME: name}, {constants.KEY_NAME: "keep"}]
            },
        },
        test_constants.KEY_NOTES: [f"I wrote about {name}"],
    }
    removed = cleanup.prune(doc)
    assert removed
    assert set(doc[constants.KEY_MCP_SERVERS]) == {"keep"}
    assert doc[test_constants.KEY_PERMISSIONS][test_constants.KEY_ALLOW] == ["Read"]
    assert doc[constants.KEY_ENV] == {test_constants.ENV_KEEP: constants.BOOLEAN_YES}
    assert doc[constants.KEY_PLUGINS] == {
        test_constants.KEY_SHARED_MARKETPLACE: {
            constants.KEY_PLUGINS: [{constants.KEY_NAME: "keep"}]
        }
    }
    assert doc[test_constants.KEY_NOTES] == [f"I wrote about {name}"]


def test_nested_hooks_only_remove_owned_command():
    doc = {
        test_constants.KEY_HOOKS: {
            test_constants.KEY_SESSION_START: [
                {
                    test_constants.KEY_MATCHER: "*",
                    test_constants.KEY_HOOKS: [
                        {
                            constants.KEY_TYPE: "command",
                            test_constants.KEY_COMMAND: "code-search-local warmup",
                        },
                        {constants.KEY_TYPE: "command", test_constants.KEY_COMMAND: "keep-hook"},
                    ],
                }
            ]
        }
    }
    cleanup.prune(doc)
    assert doc[test_constants.KEY_HOOKS][test_constants.KEY_SESSION_START][0][
        test_constants.KEY_HOOKS
    ] == [{constants.KEY_TYPE: "command", test_constants.KEY_COMMAND: "keep-hook"}]


def test_codex_mcp_tool_cache_preserves_unrelated_servers():
    entries = [
        {
            constants.KEY_NAME: "alias",
            test_constants.KEY_SERVER_INFO: {constants.KEY_NAME: constants.APPLICATION_NAME},
        },
        {
            constants.KEY_NAME: "keep",
            test_constants.KEY_SERVER_INFO: {constants.KEY_NAME: "keep-server"},
        },
    ]
    doc = {
        test_constants.KEY_ELECTRON_PERSISTED_ATOM_STATE: {
            test_constants.KEY_MCP_SERVER_TOOLS_CACHE_V2: {test_constants.KEY_CATALOG: entries}
        }
    }
    cleanup.prune(doc)
    assert entries == [
        {
            constants.KEY_NAME: "keep",
            test_constants.KEY_SERVER_INFO: {constants.KEY_NAME: "keep-server"},
        }
    ]


def test_toml_comments_jsonc_and_custom_endpoint(home):
    scanner = cleanup.Scanner(home)
    toml = write(
        home / test_constants.PATH_CODEX_CONFIG_TOML_LOWERCASE,
        '# keep comment\n[other]\nvalue = 1\n[mcp_servers.code_search_local]\ncommand = "server"\n',
    )
    jsonc = write(
        home / test_constants.PATH_CONFIG_OPENCODE_CUSTOM_JSONC,
        '{"mcp":{"alias":{"url":"http://localhost:9988/mcp"},"keep":{"url":"http://localhost:9999/mcp"}}}',
    )
    scanner.endpoints.add("http://localhost:9988/mcp")
    scanner.config(toml)
    scanner.config(jsonc)
    assert "# keep comment" in scanner.actions[("edit", str(toml))].after
    assert (
        test_constants.VALUE_MCP_SERVERS_CODE_SEARCH_LOCAL
        not in scanner.actions[("edit", str(toml))].after
    )
    assert set(json.loads(scanner.actions[("edit", str(jsonc))].after)[constants.KEY_MCP]) == {
        "keep"
    }


def test_malformed_and_unsupported_references_are_reported(home):
    scanner = cleanup.Scanner(home)
    for name, content in [
        ("bad.json", "{code-search-local"),
        ("unrelated.json", "{oops"),
        ("config.yaml", "mcp: code-search-local"),
    ]:
        scanner.config(write(home / name, content))
    assert not scanner.actions
    assert {Path(f[constants.KEY_PATH]).name for f in scanner.findings} == {
        "bad.json",
        "config.yaml",
    }


def test_toml_arrays_and_home_project_do_not_block_service_cleanup(home):
    config = write(
        home / test_constants.PATH_CODEX_CONFIG_TOML_LOWERCASE,
        '# comment\n[projects."'
        + str(home)
        + '"]\ntrust_level="trusted"\n[mcp_servers.code-search-local]\nargs=["serve"]\n[other]\nvalues=["keep"]\n',
    )
    service = write(
        home / test_constants.PATH_CONFIG_SYSTEMD_USER_CODE_SEARCH_LOCAL_SERVICE,
        "[Service]\nExecStart=code-search-local serve\n",
    )
    scanner = cleanup.Scanner(home, scope=constants.USER_SCOPE)
    scanner.profiles()
    scanner.units()
    assert ("edit", str(config)) in scanner.actions
    assert any(
        a.target == str(service) and a.kind == constants.COMMAND_REMOVE for a in scanner.finish()
    )


def test_history_jsonl_and_compressed_assets_are_not_read(home):
    history = write(
        home / test_constants.PATH_CLAUDE_PROJECTS_SESSION_JSONL, '{"prompt":"code-search-local"}\n'
    )
    compressed = write(
        home / test_constants.PATH_CLAUDE_PLUGINS_EXAMPLE_JSON_GZ, "invalidcompressed"
    )
    scanner = cleanup.Scanner(home)
    scanner.profiles()
    assert history not in scanner.scanned
    assert compressed not in scanner.scanned


def test_editor_history_and_config_symlinks(home):
    history = write(
        home / test_constants.PATH_CONFIG_CODE_USER_HISTORY_ID_CONFIG_TOML,
        '[mcp_servers.code-search-local]\ncommand="server"\n',
    )
    protected = write(
        home / test_constants.PATH_BACKUPS_CONFIG_JSON, '{"mcp":{"code-search-local":{}}}'
    )
    alias = home / test_constants.PATH_LINKED_CONFIG_JSON
    alias.symlink_to(protected)
    config = write(
        home / test_constants.PATH_CODEX_CONFIG_TOML_LOWERCASE,
        '[mcp_servers.code-search-local]\ncommand="server"\n',
    )
    (home / test_constants.PATH_CODEX).symlink_to(
        home / constants.PATH_CODEX, target_is_directory=True
    )
    scanner = cleanup.Scanner(home)
    scanner.config(alias)
    scanner.profiles()
    assert history not in scanner.scanned
    assert protected not in scanner.scanned
    edits = [a for a in scanner.actions.values() if a.kind == test_constants.VALUE_EDIT]
    assert len(edits) == 1
    assert Path(edits[0].target).resolve() == config


def test_storage_aliases_and_models_are_preserved_with_index_removal(home, tmp_path):
    storage = tmp_path / test_constants.PATH_DEDICATED_DATA
    index = write(storage / constants.PATH_STATE_SQLITE3, "index")
    write(storage / test_constants.PATH_STATE_SQLITE3_WAL, "wal")
    write(storage / test_constants.PATH_PROJECTS_ID_VECTORS_FAISS, "index")
    model = write(storage / test_constants.PATH_MODELS_UNIQUE_MODEL_MODEL_SAFETENSORS, "weights")
    write(storage / test_constants.PATH_RUNTIMES_OLD_PYTHON, constants.KEY_RUNTIME)
    alias = home / test_constants.PATH_CLAUDE_CODE_SEARCH
    alias.symlink_to(storage, target_is_directory=True)
    write(
        home / test_constants.PATH_CONFIG_CODE_SEARCH_LOCAL_CONFIG_JSON_LOWERCASE,
        json.dumps({constants.KEY_STORAGE: str(storage)}),
    )
    scanner = cleanup.Scanner(home)
    scanner.app_state()
    actions = scanner.finish()
    assert not any(
        a.target
        in {str(alias), str(index), str(storage / constants.RUNTIMES_DIRECTORY), str(storage)}
        for a in actions
    )
    scanner = cleanup.Scanner(home, remove_indexes=True, remove_runtime_packages=True)
    scanner.app_state()
    actions = scanner.finish()
    assert any(a.target == str(index) for a in actions)
    assert any(a.target == str(storage / constants.KEY_PROJECTS) for a in actions)
    assert not any(Path(a.target) == model or Path(a.target) in model.parents for a in actions)
    assert not any(a.target == str(alias) for a in actions)
    assert model.read_text() == test_constants.VALUE_WEIGHTS
    assert index.read_text() == test_constants.VALUE_INDEX


def test_rejects_shared_paths_unverified_storage_and_nested_worktrees(home, tmp_path):
    scanner = cleanup.Scanner(home, remove_indexes=True, remove_runtime_packages=True)
    scanner.storage.update({home, tmp_path / test_constants.PATH_UNVERIFIED})
    write(home / test_constants.PATH_MODELS_EXAMPLE, "data")
    owner = home / test_constants.PATH_CODE_SEARCH_LOCAL_CACHE
    write(owner / test_constants.PATH_NODE_MODULES_DEEP_GIT, "gitdir: /another/worktree\n")
    scanner.delete(owner, "candidate")
    scanner.delete(home, "candidate")
    scanner.delete(SCRIPT.parents[1], "candidate")
    assert not scanner.finish()
    assert any(
        test_constants.VALUE_WORKTREE in f[test_constants.KEY_REASON] for f in scanner.findings
    )


def test_changed_config_and_replaced_symlink_fail_identity_checks(home):
    scanner = cleanup.Scanner(home)
    config = write(home / constants.PATH_CONFIG_JSON, '{"mcp":{"code-search-local":{}}}')
    scanner.config(config)
    action = scanner.actions[("edit", str(config))]
    assert cleanup.unchanged(action)
    config.write_text("{}")
    assert not cleanup.unchanged(action)
    target = write(home / constants.KEY_TARGET, "contents")
    alias = home / constants.APPLICATION_NAME
    alias.symlink_to(target)
    scanner.delete(alias, "alias")
    action = scanner.actions[(constants.COMMAND_REMOVE, str(alias))]
    assert cleanup.unchanged(action)
    alias.unlink()
    alias.write_text("replacement")
    assert not cleanup.unchanged(action)


@pytest.mark.parametrize(
    "args,cwd,expected",
    [
        ([constants.APPLICATION_NAME, constants.COMMAND_SERVE], "/", True),
        (
            [
                constants.KEY_PYTHON,
                constants.SHORT_OPTION_M,
                constants.PACKAGE_NAME,
                constants.COMMAND_SERVE,
            ],
            "/",
            True,
        ),
        (["python3", "mcp_server/server.py"], "/repo/claude-context-local", True),
        (
            [
                "uv",
                "run",
                test_constants.OPTION_DIRECTORY,
                "/repo/claude-context-local",
                constants.KEY_PYTHON,
                "mcp_server/server.py",
            ],
            "/",
            True,
        ),
        (
            [
                "uvx",
                test_constants.OPTION_FROM,
                constants.APPLICATION_NAME,
                constants.APPLICATION_NAME,
                constants.COMMAND_SERVE,
            ],
            "/",
            True,
        ),
        (
            [
                constants.KEY_PYTHON,
                constants.SHORT_OPTION_U,
                constants.SHORT_OPTION_M,
                "ClAuDe_Context_Local",
            ],
            "/",
            True,
        ),
        (
            [constants.HARNESS_CLAUDE, "Tell me about code-search-local"],
            "/repo/code-search-local",
            False,
        ),
        ([constants.HARNESS_CODEX, "exec", "code-search-local serve"], "/", False),
        ([constants.HARNESS_OPENCODE, "run", "claude-context-local"], "/", False),
        (
            [constants.KEY_PYTHON, test_constants.SHORT_OPTION_C, constants.APPLICATION_NAME],
            "/",
            False,
        ),
        (
            [constants.KEY_PYTHON, constants.SHORT_OPTION_M, "pytest", constants.APPLICATION_NAME],
            "/",
            False,
        ),
        (
            ["uv", "run", test_constants.OPTION_DIRECTORY, "/repo/code-search-local", "pytest"],
            "/",
            False,
        ),
        (["bash", test_constants.SHORT_OPTION_C, "code-search-local serve"], "/", False),
        ([constants.KEY_PYTHON, "mcp_server/server.py"], "/repo/another-server", False),
        (
            [constants.KEY_PYTHON, str(SCRIPT), test_constants.OPTION_DRY_RUN],
            str(SCRIPT.parent),
            False,
        ),
        (["code-search-locality"], "/", False),
    ],
)
def test_process_identity_uses_launch_arguments(args, cwd, expected):
    assert (
        cleanup.owned_process({test_constants.KEY_ARGS: args, constants.KEY_CWD: cwd}) is expected
    )


def test_process_discovery_includes_children_excludes_ancestors_and_zombies(
    home, tmp_path, monkeypatch
):
    proc = tmp_path / test_constants.PATH_PROC
    proc.mkdir()
    info = {}
    for pid, ppid, args, state in [
        (400, 1, [constants.APPLICATION_NAME, constants.COMMAND_SERVE], "S"),
        (401, 400, ["worker"], "S"),
        (402, 1, [constants.APPLICATION_NAME], "Z"),
        (403, 1, [constants.HARNESS_CODEX, constants.APPLICATION_NAME], "S"),
    ]:
        (proc / str(pid)).mkdir()
        info[pid] = {
            test_constants.KEY_PID: pid,
            test_constants.KEY_PPID: ppid,
            test_constants.KEY_ARGS: args,
            test_constants.KEY_STATE: state,
            test_constants.KEY_UID: home.stat().st_uid,
            test_constants.KEY_START_TICKS: "123",
            constants.KEY_CWD: str(home),
        }
    scanner = cleanup.Scanner(home)
    monkeypatch.setattr(cleanup, "process_info", lambda p: info.get(int(p.name)))
    scanner.processes(proc)
    assert {a.target for a in scanner.actions.values()} == {"400", "401"}
    scanner.actions.clear()
    scanner.ancestors.add(400)
    scanner.processes(proc)
    assert not scanner.actions


def test_unit_content_comments_and_activation_units(home):
    root = home / test_constants.PATH_CONFIG_SYSTEMD_USER
    write(root / test_constants.PATH_CODE_SEARCH_LOCAL_PATH, "[Path]\nPathChanged=/config\n")
    write(
        root / test_constants.PATH_ALIAS_SERVICE,
        "[Service]\nExecStart=/usr/bin/python -m code_search_local serve\n",
    )
    write(
        root / test_constants.PATH_UNRELATED_SERVICE,
        "# code-search-local documentation\n[Service]\nExecStart=/bin/true\n",
    )
    write(
        root / test_constants.PATH_OTHER_SERVICE_D_OVERRIDE_CONF,
        "[Service]\nEnvironment=CODE_SEARCH_STORAGE=/tmp/code-search-local\n",
    )
    scanner = cleanup.Scanner(home, scope=constants.USER_SCOPE)
    scanner.units()
    units = {
        a.details[test_constants.KEY_UNIT]
        for a in scanner.actions.values()
        if a.kind == test_constants.KEY_UNIT
    }
    assert units == {"alias.service", "code-search-local.path"}
    assert any("unrelated unit" in f[test_constants.KEY_REASON] for f in scanner.findings)


def make_environment(venv, *, installer="uv", name=constants.APPLICATION_NAME):
    metadata = (
        venv
        / test_constants.PATH_LIB_PYTHON3_12_SITE_PACKAGES
        / (name.replace("-", "_") + "-1.0.0.dist-info")
    )
    write(metadata / test_constants.PATH_METADATA, f"Name: {name}\n")
    write(metadata / test_constants.PATH_INSTALLER, installer)
    write(venv / test_constants.PATH_PYVENV_CFG_LOWERCASE, "home = /usr/bin\n")
    write(venv / constants.PATH_BIN_PYTHON, "fixture")
    if installer == constants.COMMAND_PIP:
        write(venv / test_constants.PATH_LIB_PYTHON3_12_SITE_PACKAGES_PIP_MAIN_PY, "fixture")
    return metadata


def test_installer_receipts_and_default_runtime_retention(home, monkeypatch):
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    uv = home / test_constants.PATH_LOCAL_SHARE_UV_TOOLS_CODE_SEARCH_LOCAL
    make_environment(uv)
    write(
        uv / test_constants.PATH_UV_RECEIPT_TOML,
        '[tool]\nrequirements=[{name="code-search-local"}]\n',
    )
    pipx = home / test_constants.PATH_LOCAL_SHARE_PIPX_VENVS_CLAUDE_CONTEXT_LOCAL
    make_environment(pipx, installer=constants.COMMAND_PIP, name="claude-context-local")
    write(
        pipx / test_constants.PATH_PIPX_METADATA_JSON,
        json.dumps(
            {
                test_constants.KEY_MAIN_PACKAGE: {
                    constants.INSTALL_MODE_PACKAGE: "claude-context-local"
                }
            }
        ),
    )
    shared = home / test_constants.PATH_VENVS_OTHER
    make_environment(shared, installer=constants.COMMAND_PIP)
    scanner = cleanup.Scanner(home, scope=constants.USER_SCOPE)
    scanner.installations()
    assert not scanner.finish()
    scanner = cleanup.Scanner(home, scope=constants.USER_SCOPE, remove_runtime_packages=True)
    scanner.installations()
    actions = {a.target: a for a in scanner.finish()}
    assert actions[str(uv)].details[test_constants.KEY_COMMANDS] == [
        ["/tools/uv", constants.KEY_TOOL, constants.COMMAND_UNINSTALL, constants.APPLICATION_NAME]
    ]
    assert actions[str(uv)].details[test_constants.KEY_ENVIRONMENT] == {
        test_constants.ENV_UV_TOOL_DIR: str(uv.parent)
    }
    assert actions[str(pipx)].details[test_constants.KEY_COMMANDS] == [
        ["/tools/pipx", constants.COMMAND_UNINSTALL, "claude-context-local"]
    ]
    assert actions[str(pipx)].details[test_constants.KEY_ENVIRONMENT] == {
        test_constants.ENV_PIPX_HOME: str(pipx.parent.parent)
    }
    assert actions[str(shared)].details[test_constants.KEY_COMMANDS] == [
        [
            str(shared / constants.PATH_BIN_PYTHON),
            constants.SHORT_OPTION_M,
            constants.COMMAND_PIP,
            constants.COMMAND_UNINSTALL,
            test_constants.SHORT_OPTION_Y,
            constants.APPLICATION_NAME,
        ]
    ]
    assert all(
        a.kind == constants.INSTALL_MODE_PACKAGE and test_constants.KEY_CLEANUP_DIR not in a.details
        for a in actions.values()
    )


def test_project_discovery_cache_manifest_and_backups(home, tmp_path):
    project = tmp_path / test_constants.PATH_WORKSPACE
    write(
        project / test_constants.PATH_MCP_JSON_LOWERCASE,
        '{"mcpServers":{"code-search-local":{},"keep":{}}}',
    )
    write(
        home / constants.PATH_CLAUDE_JSON, json.dumps({constants.KEY_PROJECTS: {str(project): {}}})
    )
    plugin = home / test_constants.PATH_CODEX_PLUGINS_CACHE_ABC123
    write(plugin / test_constants.PATH_CODEX_PLUGIN_PLUGIN_JSON, '{"name":"code-search-local"}')
    backup = write(
        home / test_constants.PATH_CLAUDE_BACKUPS_CONFIG_JSON, '{"mcp":{"code-search-local":{}}}'
    )
    scanner = cleanup.Scanner(home)
    scanner.profiles()
    assert ("edit", str(project / test_constants.PATH_MCP_JSON_LOWERCASE)) in scanner.actions
    assert (constants.COMMAND_REMOVE, str(plugin)) in scanner.actions
    assert backup not in scanner.scanned


def test_shell_and_cron_preserve_compound_and_unrelated_commands(home):
    path = write(
        home / test_constants.PATH_BASHRC,
        'export CODE_SEARCH_STORAGE="/data"\nexport PATH="/repo/code-search-local/bin:$PATH"\nalias code-search-local="run server"\necho code-search-local\n',
    )
    scanner = cleanup.Scanner(home)
    scanner.launch_references()
    after = scanner.actions[("edit", str(path))].after
    assert constants.ENV_CODE_SEARCH_STORAGE not in after
    assert "export PATH=" in after
    assert "echo code-search-local" in after
    text = "@reboot code-search-local serve\n* * * * * echo code-search-local\n0 0 * * * code-search-local serve && keep\n@daily keep\n"
    after, removed, ambiguous = cleanup.clean_cron(text, home)
    assert removed == [1]
    assert ambiguous == [2, 3]
    assert "@daily keep" in after
    assert cleanup.clean_cron("@reboot root code-search-local serve\n", home, system=True)[1] == [1]


@pytest.mark.parametrize(
    "flags,indexes,runtimes",
    [
        ([], False, False),
        ([test_constants.OPTION_REMOVE_INDEXES], True, False),
        ([test_constants.OPTION_REMOVE_RUNTIME_PACKAGES], False, True),
        ([test_constants.OPTION_REMOVE_ALL], True, True),
    ],
)
def test_removal_flag_matrix_is_read_only(home, monkeypatch, flags, indexes, runtimes):
    storage = home / test_constants.KEY_DATA
    model = write(storage / test_constants.PATH_MODELS_NAMED_MODEL_MODEL_SAFETENSORS, "weights")
    index = write(storage / constants.PATH_STATE_SQLITE3, "index")
    runtime = storage / test_constants.PATH_RUNTIMES_RELEASE
    write(runtime / constants.PATH_README_MD, "Managed code-search-local runtime.\n")
    write(runtime / constants.PATH_UV_LOCK, "version = 1\n")
    make_environment(runtime / constants.PATH_VENV)
    config = write(
        home / test_constants.PATH_CONFIG_OPENCODE_OPENCODE_JSON_LOWERCASE,
        '{"mcp":{"code-search-local":{},"keep":{}},"plugin":["code-search-local","keep"]}',
    )
    claude_mcp = write(
        home / constants.PATH_CLAUDE_JSON, '{"mcpServers":{"claude-context-local":{},"keep":{}}}'
    )
    claude_plugins = write(
        home / test_constants.PATH_CLAUDE_PLUGINS_INSTALLED_PLUGINS_JSON,
        '{"plugins":{"code-search-local@market":[{"scope":"user"}],"keep@market":[]}}',
    )
    claude_settings = write(
        home / test_constants.PATH_CLAUDE_SETTINGS_JSON,
        '{"enabledPlugins":{"code-search-local@market":true,"keep@market":true}}',
    )
    codex = write(
        home / test_constants.PATH_CODEX_CONFIG_TOML_LOWERCASE,
        '[mcp_servers.code-search-local]\ncommand="server"\n[plugins."claude-context-local@market"]\nenabled=true\n[plugins."keep@market"]\nenabled=true\n',
    )
    caches = [
        home / name / test_constants.PATH_PLUGINS_CACHE_CODE_SEARCH_LOCAL
        for name in (constants.PATH_CLAUDE, constants.PATH_CODEX)
    ]
    for cache in caches:
        write(cache / test_constants.PATH_1_0_0_PLUGIN_JSON, '{"name":"code-search-local"}')
    unit_root = home / test_constants.PATH_CONFIG_SYSTEMD_USER
    unit_names = [
        "code-search-local.service",
        "code-search-local-marketplace.service",
        "code-search-local-marketplace.path",
        "code-search-local-marketplace.timer",
        "claude-context-local.service",
    ]
    for name in unit_names:
        write(unit_root / name, "[Unit]\nDescription=fixture\n")
    link = unit_root / test_constants.PATH_DEFAULT_TARGET_WANTS_CODE_SEARCH_LOCAL_SERVICE
    link.parent.mkdir()
    link.symlink_to(unit_root / test_constants.PATH_CODE_SEARCH_LOCAL_SERVICE)
    unrelated_unit = write(
        unit_root / test_constants.PATH_KEEP_SERVICE, "[Service]\nExecStart=/bin/true\n"
    )
    write(
        home / test_constants.PATH_CONFIG_CODE_SEARCH_LOCAL_CONFIG_JSON_LOWERCASE,
        json.dumps({constants.KEY_STORAGE: str(storage)}),
    )
    before = {
        path: path.read_bytes()
        for path in home.rglob(test_constants.PATH_PATTERN)
        if path.is_file()
    }
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    monkeypatch.setattr(cleanup.Scanner, "processes", lambda self: None)

    def forbidden(*args, **kwargs):
        pytest.fail("A dry-run attempted to modify the installation")

    monkeypatch.setattr(cleanup, "apply_plan", forbidden)
    monkeypatch.setattr(cleanup.subprocess, "run", forbidden)
    monkeypatch.setattr(cleanup.shutil, "rmtree", forbidden)
    monkeypatch.setattr(cleanup.os, "kill", forbidden)
    result = invoke_cleanup_dry_run(home, *flags)
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report[test_constants.KEY_REMOVE_INDEXES] is indexes
    assert report[test_constants.KEY_REMOVE_RUNTIME_PACKAGES] is runtimes
    assert report[test_constants.KEY_MODELS_PRESERVED] is True
    assert (
        any(a[constants.KEY_TARGET] == str(index) for a in report[test_constants.KEY_ACTIONS])
        is indexes
    )
    assert (
        any(
            a[test_constants.KEY_KIND] == constants.INSTALL_MODE_PACKAGE
            for a in report[test_constants.KEY_ACTIONS]
        )
        is runtimes
    )
    assert any(
        a[constants.KEY_TARGET] == str(config)
        and a[test_constants.KEY_KIND] == test_constants.VALUE_EDIT
        for a in report[test_constants.KEY_ACTIONS]
    )
    # Services and all harness registrations are always removed, including flags=[].
    planned = {
        (a[test_constants.KEY_KIND], a[constants.KEY_TARGET]): a
        for a in report[test_constants.KEY_ACTIONS]
    }
    for name in unit_names:
        assert ("unit", f"user:{name}") in planned
        assert (constants.COMMAND_REMOVE, str(unit_root / name)) in planned
    assert (constants.COMMAND_REMOVE, str(link)) in planned
    assert (constants.COMMAND_REMOVE, str(unrelated_unit)) not in planned
    for cache in caches:
        assert (constants.COMMAND_REMOVE, str(cache)) in planned
    for path, entries in [
        (claude_mcp, ["/mcpServers/claude-context-local"]),
        (claude_plugins, ["/plugins/code-search-local@market"]),
        (claude_settings, ["/enabledPlugins/code-search-local@market"]),
        (codex, ["/mcp_servers/code-search-local", "/plugins/claude-context-local@market"]),
        (config, ["/mcp/code-search-local", "/plugin/0"]),
    ]:
        assert planned[("edit", str(path))][test_constants.KEY_ENTRIES] == entries
    assert all(
        Path(a[constants.KEY_TARGET]) != model
        and Path(a[constants.KEY_TARGET]) not in model.parents
        for a in report[test_constants.KEY_ACTIONS]
    )
    assert (
        model.read_text() == test_constants.VALUE_WEIGHTS
        and index.read_text() == test_constants.VALUE_INDEX
    )
    assert before == {
        path: path.read_bytes()
        for path in home.rglob(test_constants.PATH_PATTERN)
        if path.is_file()
    }


@pytest.mark.parametrize("marker", ["directory", "file"])
def test_clones_and_linked_worktrees_always_preserve_runtime(home, tmp_path, monkeypatch, marker):
    project = tmp_path / test_constants.PATH_UNRELATED_PROJECT_NAME
    env = project / constants.PATH_VENV
    make_environment(env)
    if marker == test_constants.VALUE_DIRECTORY:
        (project / test_constants.PATH_GIT).mkdir()
    else:
        write(project / test_constants.PATH_GIT, "gitdir: /other/repo/.git/worktrees/test\n")
    scanner = cleanup.Scanner(
        home, remove_runtime_packages=True, remove_indexes=True, project_roots=[project]
    )
    scanner.python_environment(env)
    assert not scanner.finish()
    write(
        env / test_constants.PATH_UV_RECEIPT_TOML,
        '[tool]\nrequirements=[{name="code-search-local"}]\n',
    )
    alias = home / test_constants.PATH_LOCAL_SHARE_UV_TOOLS_CODE_SEARCH_LOCAL
    alias.parent.mkdir(parents=True)
    alias.symlink_to(env, target_is_directory=True)
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    scanner.installations()
    assert not scanner.finish()
    assert any(
        test_constants.VALUE_WORKTREE in f[test_constants.KEY_REASON] for f in scanner.findings
    )


def test_managed_runtime_uses_installer_then_dedicated_cleanup(home, monkeypatch):
    root = home / test_constants.PATH_DATA_RUNTIMES_RELEASE
    env = root / constants.PATH_VENV
    make_environment(env)
    make_environment(env, name="dependency")
    write(root / constants.PATH_README_MD, "Managed code-search-local runtime.\n")
    write(root / constants.PATH_UV_LOCK, "version=1\n")
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.storage.add(home / test_constants.KEY_DATA)
    scanner.installations()
    action = scanner.actions[(constants.INSTALL_MODE_PACKAGE, str(env))]
    assert action.details[test_constants.KEY_COMMANDS] == [
        [
            "/tools/uv",
            constants.COMMAND_PIP,
            constants.COMMAND_UNINSTALL,
            constants.OPTION_PYTHON,
            str(env / constants.PATH_BIN_PYTHON),
            constants.APPLICATION_NAME,
            "dependency",
        ]
    ]
    assert action.details[test_constants.KEY_CLEANUP_DIR] == str(root)
    assert cleanup.unchanged(action)
    (root / constants.PATH_UV_LOCK).write_text("changed")
    assert not cleanup.unchanged(action)


def test_unknown_installer_retained_and_models_block_parent_removal(home):
    env = home / test_constants.PATH_VENVS_UNKNOWN
    make_environment(env, installer=constants.STATUS_UNKNOWN)
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.python_environment(env)
    assert not scanner.actions
    parent = home / test_constants.PATH_OWNED_PLUGIN
    write(parent / test_constants.PATH_MODELS_SPECIAL_MODEL_SAFETENSORS, "weights")
    scanner.delete(parent, "matching plugin")
    assert not scanner.actions
    assert any(
        "Unknown/missing INSTALLER" in f[test_constants.KEY_REASON] for f in scanner.findings
    )
    assert any("downloaded models" in f[test_constants.KEY_REASON] for f in scanner.findings)


def test_uvx_cache_cleanup_uses_uv_and_respects_worktrees(home, monkeypatch):
    cache = home / test_constants.PATH_CACHE_UV
    make_environment(cache / test_constants.PATH_ARCHIVE_V0_HASH)
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.installations()
    action = scanner.actions[(constants.INSTALL_MODE_PACKAGE, str(cache))]
    assert action.details[test_constants.KEY_COMMANDS] == [
        ["/tools/uv", "cache", "clean", constants.APPLICATION_NAME]
    ]
    assert not any(a.kind == constants.COMMAND_REMOVE for a in scanner.actions.values())
    write(cache / test_constants.PATH_ARCHIVE_V0_HASH_GIT, "gitdir: /worktree\n")
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.installations()
    assert not scanner.actions


@pytest.mark.parametrize(
    "relative",
    [
        ".codex-global-state.json.bak",
        "config.toml.BAK1",
        "config.json.bak-keybindings-20260924",
        "settings.json.backup.20260924",
        "settings.json.bkp",
        "config.toml.old",
        "config.json.orig",
        "config.json.save",
        "config.json~",
        "#config.json#",
        ".config.json.swp",
        "config.toml.2026-09-24",
        "backups/config.json",
        ".backup-20260924/config.json",
        "legacy-backups/state.json",
        "mcp-cleanup-backups/20260924/config.json",
    ],
)
def test_backup_paths_are_ignored_before_reading(home, monkeypatch, relative):
    root = home / constants.PATH_CODEX
    path = write(root / relative, '{"mcp_servers":{"code-search-local":{}}}')
    alias = write(home / test_constants.PATH_PLACEHOLDER_JSON)
    alias.unlink()
    alias.symlink_to(path)
    original_read = Path.read_bytes

    def read(candidate):
        if candidate.resolve() == path:
            pytest.fail("Backup contents must not be read during discovery")
        return original_read(candidate)

    monkeypatch.setattr(Path, "read_bytes", read)
    scanner = cleanup.Scanner(home, remove_indexes=True, remove_runtime_packages=True)
    scanner.config(path)
    scanner.config(alias)
    scanner.walk_configs(root)
    scanner.delete(path, "candidate")
    scanner.delete(alias, "candidate")
    assert not scanner.scanned
    assert not scanner.actions


def test_backup_profile_overrides_are_ignored(home, monkeypatch):
    root = home / test_constants.PATH_BACKUPS_CODEX
    write(root / constants.PATH_CONFIG_TOML, '[mcp_servers.code-search-local]\ncommand="server"\n')
    write(
        root / test_constants.PATH_PLUGINS_CODE_SEARCH_LOCAL_PLUGIN_JSON,
        '{"name":"code-search-local"}',
    )
    write(
        home / test_constants.PATH_CONFIG_CODE_SEARCH_LOCAL_INSTALLATION_JSON,
        json.dumps(
            {
                constants.KEY_TARGETS: [
                    {constants.KEY_CONFIGS: [str(root / constants.PATH_CONFIG_TOML)]}
                ]
            }
        ),
    )
    monkeypatch.setenv(constants.ENV_CODEX_HOME, str(root))
    scanner = cleanup.Scanner(home, scan_roots=[root])
    scanner.app_state()
    scanner.profiles()
    assert not scanner.scanned
    assert all(not cleanup.backup_path(a.target) for a in scanner.actions.values())


@pytest.mark.parametrize(
    constants.KEY_NAME,
    [
        "old_fractionfield.py",
        "old_polynomialring.py",
        "gpurun-old",
        "saved_variable_hooks.h",
        "saved_variable.h",
        constants.PATH_CONFIG_JSON,
        constants.PATH_CONFIG_TOML,
    ],
)
def test_normal_package_filenames_are_not_treated_as_recovery_files(name):
    assert not cleanup.backup_name(name)


def test_parent_removal_retains_nested_backups_and_eligible_siblings(home):
    owner = home / test_constants.PATH_CLAUDE_PLUGINS_CODE_SEARCH_LOCAL
    active = write(owner / test_constants.PATH_PLUGIN_JSON, '{"name":"code-search-local"}')
    backup = write(owner / test_constants.PATH_NESTED_SAVED_CONFIG_JSON, "recovery data")
    sibling = write(owner / test_constants.PATH_NESTED_ACTIVE_JSON, "active")
    scanner = cleanup.Scanner(home)
    scanner.delete(owner, "matching plugin")
    targets = {Path(a.target) for a in scanner.finish()}
    assert targets == {active, sibling}
    assert backup.read_text() == "recovery data"
    assert active.exists() and sibling.exists()


@pytest.mark.parametrize("installer", ["uv", "pipx"])
def test_native_package_uninstall_cannot_remove_existing_backups(home, monkeypatch, installer):
    root = home / (
        ".local/share/uv/tools"
        if installer == test_constants.VALUE_UV
        else ".local/share/pipx/venvs"
    )
    env = root / constants.APPLICATION_NAME
    if installer == test_constants.VALUE_UV:
        write(
            env / test_constants.PATH_UV_RECEIPT_TOML,
            '[tool]\nrequirements=[{name="code-search-local"}]\n',
        )
    else:
        write(
            env / test_constants.PATH_PIPX_METADATA_JSON,
            '{"main_package":{"package":"code-search-local"}}',
        )
    saved = write(env / test_constants.PATH_CONFIG_JSON_BAK, "recovery data")
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.installations()
    assert not scanner.actions
    assert any(
        test_constants.PATH_BACKUPS in item[test_constants.KEY_REASON] for item in scanner.findings
    )
    assert saved.read_text() == "recovery data"


def test_managed_runtime_parent_backups_block_package_uninstall(home, monkeypatch):
    root = home / test_constants.PATH_DATA_RUNTIMES_RELEASE
    make_environment(root / constants.PATH_VENV)
    write(root / constants.PATH_README_MD, "Managed code-search-local runtime.\n")
    write(root / constants.PATH_UV_LOCK, "version=1\n")
    write(root / test_constants.PATH_UV_LOCK_BAK, "recovery lock")
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.storage.add(home / test_constants.KEY_DATA)
    scanner.installations()
    assert not scanner.actions
    assert test_constants.PATH_BACKUPS in scanner.artifact_guard(root, environment=True)


@pytest.mark.parametrize("installer", ["uv", "pipx"])
def test_installer_receipt_symlinks_do_not_read_recovery_data(home, monkeypatch, installer):
    env = home / (
        ".local/share/uv/tools/code-search-local"
        if installer == test_constants.VALUE_UV
        else ".local/share/pipx/venvs/code-search-local"
    )
    receipt = env / (
        "uv-receipt.toml" if installer == test_constants.VALUE_UV else "pipx_metadata.json"
    )
    saved = write(home / test_constants.PATH_BACKUPS_RECEIPT, "must not be read")
    receipt.parent.mkdir(parents=True)
    receipt.symlink_to(saved)
    original_read = Path.read_text

    def read(candidate, *args, **kwargs):
        if candidate.resolve() == saved:
            pytest.fail("Discovery must not read an installer receipt linked to a backup")
        return original_read(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.installations()
    assert not scanner.actions


def test_new_backups_are_detected_after_discovery(home):
    owner = home / test_constants.PATH_CODE_SEARCH_LOCAL_CACHE
    write(owner / constants.PATH_CONFIG_JSON, "{}")
    scanner = cleanup.Scanner(home)
    scanner.delete(owner, "matching cache")
    assert (constants.COMMAND_REMOVE, str(owner)) in scanner.actions
    write(owner / test_constants.PATH_CONFIG_JSON_BAK, "recovery data")
    assert test_constants.PATH_BACKUPS in scanner.artifact_guard(owner)
    # Inspection only: the destructive branch remains deliberately unexecuted.


@pytest.mark.parametrize(
    "flags",
    [
        [],
        [test_constants.OPTION_REMOVE_INDEXES],
        [test_constants.OPTION_REMOVE_RUNTIME_PACKAGES],
        [test_constants.OPTION_REMOVE_ALL],
    ],
)
def test_all_cleanup_modes_keep_backups_and_still_remove_active_registrations(
    home, monkeypatch, flags
):
    config = write(
        home / test_constants.PATH_CODEX_CONFIG_TOML_LOWERCASE,
        '[mcp_servers.code-search-local]\ncommand="server"\n',
    )
    backup = write(home / test_constants.PATH_CODEX_CONFIG_TOML_BAK, config.read_text())
    unit = write(
        home / test_constants.PATH_CONFIG_SYSTEMD_USER_CODE_SEARCH_LOCAL_SERVICE,
        "[Service]\nExecStart=code-search-local serve\n",
    )
    saved_unit = write(unit.with_suffix(test_constants.PATH_SERVICE_BAK), unit.read_text())
    archived_unit = write(
        unit.parent / test_constants.PATH_BACKUPS_CODE_SEARCH_LOCAL_OLD_SERVICE, unit.read_text()
    )
    storage = home / test_constants.PATH_CODE_SEARCH_LOCAL
    write(storage / constants.PATH_STATE_SQLITE3, "index")
    legacy = write(
        storage / test_constants.PATH_LEGACY_BACKUPS_PROJECTS_ID_INDEX_JSON, "saved index"
    )
    nested = write(storage / test_constants.PATH_PROJECTS_ID_INDEX_JSON_BAK, "saved index")
    write(storage / test_constants.PATH_PROJECTS_ID_VECTORS_FAISS, "active index")
    monkeypatch.setattr(cleanup.Scanner, "processes", lambda self: None)

    def forbidden(*args, **kwargs):
        pytest.fail("Dry-run attempted a mutation")

    monkeypatch.setattr(cleanup, "apply_plan", forbidden)
    monkeypatch.setattr(cleanup.subprocess, "run", forbidden)
    before = {p: p.read_bytes() for p in home.rglob(test_constants.PATH_PATTERN) if p.is_file()}
    result = invoke_cleanup_dry_run(home, *flags)
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report[test_constants.KEY_COUNTS][test_constants.KEY_UNIT] == 1
    assert any(
        a[test_constants.KEY_KIND] == test_constants.VALUE_EDIT
        and a[constants.KEY_TARGET] == str(config)
        for a in report[test_constants.KEY_ACTIONS]
    )
    assert any(
        a[test_constants.KEY_KIND] == constants.COMMAND_REMOVE
        and a[constants.KEY_TARGET] == str(unit)
        for a in report[test_constants.KEY_ACTIONS]
    )
    for action in report[test_constants.KEY_ACTIONS]:
        target = Path(action[constants.KEY_TARGET])
        assert not cleanup.backup_path(target)
        assert all(
            target != p and target not in p.parents
            for p in (backup, saved_unit, archived_unit, legacy, nested)
        )
    assert before == {
        p: p.read_bytes() for p in home.rglob(test_constants.PATH_PATTERN) if p.is_file()
    }


def test_reports_show_match_identity_and_prioritize_active_registrations(home, monkeypatch):
    cached = write(
        home / test_constants.PATH_CODEX_CODEX_GLOBAL_STATE_JSON,
        json.dumps(
            {
                test_constants.KEY_ELECTRON_PERSISTED_ATOM_STATE: {
                    test_constants.KEY_MCP_SERVER_TOOLS_CACHE_V2: {
                        test_constants.KEY_CATALOG: [
                            {constants.KEY_NAME: "unrelated", test_constants.KEY_SERVER_INFO: None},
                            {
                                constants.KEY_NAME: "keep",
                                test_constants.KEY_DESCRIPTION: "mentions code-search-local",
                            },
                            {
                                constants.KEY_NAME: constants.APPLICATION_NAME,
                                test_constants.KEY_SERVER_INFO: {
                                    constants.KEY_NAME: constants.APPLICATION_NAME
                                },
                                constants.KEY_TOKEN: test_constants.ENV_DO_NOT_SHOW,
                            },
                        ]
                    }
                }
            }
        ),
    )
    active = write(
        home / test_constants.PATH_CODEX_CONFIG_TOML_LOWERCASE,
        '[mcp_servers.code-search-local]\ncommand="server"\n',
    )
    (home / test_constants.PATH_CODEX).symlink_to(
        home / constants.PATH_CODEX, target_is_directory=True
    )
    scanner = cleanup.Scanner(home)
    scanner.profiles()
    actions = scanner.finish()
    assert Path(actions[0].target).resolve() == active
    action = next(a for a in actions if Path(a.target).resolve() == cached)
    public = action.public()
    assert public[constants.KEY_TARGET] == str(cached)
    assert public[test_constants.KEY_MATCHES] == [
        {
            test_constants.KEY_ENTRY: "/electron-persisted-atom-state/mcp-server-tools-cache-v2/catalog/2",
            test_constants.KEY_CATEGORY: "cached MCP discovery entry",
            test_constants.KEY_MATCHED_FIELDS: [
                {
                    test_constants.KEY_FIELD: constants.KEY_NAME,
                    test_constants.KEY_MATCHED_NAME: constants.APPLICATION_NAME,
                },
                {
                    test_constants.KEY_FIELD: "serverInfo.name",
                    test_constants.KEY_MATCHED_NAME: constants.APPLICATION_NAME,
                },
            ],
        }
    ]
    assert not {constants.KEY_IDENTITY, "resolved", "evidence", "before", "after"} & public.keys()
    assert test_constants.ENV_DO_NOT_SHOW not in json.dumps(public)
    retained = json.loads(action.after)[test_constants.KEY_ELECTRON_PERSISTED_ATOM_STATE][
        test_constants.KEY_MCP_SERVER_TOOLS_CACHE_V2
    ][test_constants.KEY_CATALOG]
    assert [entry[constants.KEY_NAME] for entry in retained] == ["unrelated", "keep"]
    monkeypatch.setattr(cleanup.Scanner, "scan", lambda self: actions)
    result = CliRunner().invoke(
        cleanup.main, [test_constants.OPTION_DRY_RUN, test_constants.OPTION_HOME, str(home)]
    )
    assert result.exit_code == 0, result.output
    assert "name: code-search-local; serverInfo.name: code-search-local" in result.output
    assert result.output.index(str(active)) < result.output.index(str(cached))
    assert test_constants.ENV_DO_NOT_SHOW not in result.output
