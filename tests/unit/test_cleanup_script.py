"""Exercise discovery only. Never execute this script's destructive apply branch."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/clean-existing-installations-and-configs.py"
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
    root = tmp_path / "home"
    root.mkdir()
    for key in (
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "OPENCODE_CONFIG",
        "OPENCODE_CONFIG_DIR",
        "CODE_SEARCH_STORAGE",
        "CLAUDE_CONTEXT_LOCAL_STORAGE",
        "CLAUDE_CODE_SEARCH_STORAGE",
        "UV_TOOL_DIR",
        "UV_TOOL_BIN_DIR",
        "UV_CACHE_DIR",
        "PIPX_HOME",
        "PIPX_BIN_DIR",
        "NPM_CONFIG_PREFIX",
        "npm_config_prefix",
        "SUDO_USER",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in {
        "HOME": root,
        "XDG_CONFIG_HOME": root / ".config",
        "XDG_CACHE_HOME": root / ".cache",
        "XDG_DATA_HOME": root / ".local/share",
        "PATH": root / ".local/bin",
    }.items():
        monkeypatch.setenv(key, str(value))

    def readonly(args, **kwargs):
        assert args[0] in {"systemctl", "crontab"}
        assert "list-units" in args or "-l" in args
        return SimpleNamespace(
            returncode=0, stdout="[]" if args[0] == "systemctl" else "", stderr=""
        )

    monkeypatch.setattr(cleanup, "readonly", readonly)
    return root


def test_dry_run_has_no_mutations_and_redacts_values(home, monkeypatch):
    config = write(
        home / ".config/opencode/opencode.jsonc",
        """{
      // Comment and unrelated registration must survive in the backup, when applied.
      "mcp": {"ClAuDe_Context_Local": {"type":"local", "command":["old-server"]},
              "keep": {"url":"https://example.test", "headers":{"token":"SECRET_VALUE"}}}
    }""",
    )
    unit = write(
        home / ".config/systemd/user/code-search-local.service",
        "[Service]\nExecStart=code-search-local serve\n",
    )
    backup = home / "backups"
    before = {path: path.read_bytes() for path in home.rglob("*") if path.is_file()}
    monkeypatch.setattr(cleanup.Scanner, "processes", lambda self: None)

    def forbidden(*args, **kwargs):
        pytest.fail("Dry-run attempted a mutation")

    monkeypatch.setattr(cleanup, "apply_plan", forbidden)
    monkeypatch.setattr(cleanup, "atomic_write", forbidden)
    monkeypatch.setattr(cleanup.os, "kill", forbidden)
    monkeypatch.setattr(cleanup.shutil, "rmtree", forbidden)
    monkeypatch.setattr(cleanup.subprocess, "run", forbidden)
    result = CliRunner().invoke(
        cleanup.main,
        [
            "--dry-run",
            "--json",
            "--home",
            str(home),
            "--scope",
            "user",
            "--backup-dir",
            str(backup),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "SECRET_VALUE" not in result.output
    report = json.loads(result.output)
    assert report["dry_run"] is True
    assert report["counts"]["unit"] == 1
    assert any(a["kind"] == "edit" and a["target"] == str(config) for a in report["actions"])
    assert any(a["kind"] == "remove" and a["target"] == str(unit) for a in report["actions"])
    assert not backup.exists()
    assert before == {path: path.read_bytes() for path in home.rglob("*") if path.is_file()}


@pytest.mark.parametrize(
    "name",
    ["code-search-local", "CODE_SEARCH_LOCAL", "Claude-Context-Local", "claude_context_local"],
)
def test_registration_aliases_preserve_other_entries(home, name):
    doc = {
        "mcpServers": {
            name: {"command": "server"},
            "aliased": {"command": "uvx", "args": [name]},
            "keep": {"description": name, "command": "other"},
        },
        "permissions": {"allow": [f"mcp__{name}__search", "Read"]},
        "env": {"CODE_SEARCH_STORAGE": "/path", "KEEP": "yes"},
        "plugins": {
            name + "@market": True,
            "shared-marketplace": {"plugins": [{"name": name}, {"name": "keep"}]},
        },
        "notes": [f"I wrote about {name}"],
    }
    removed = cleanup.prune(doc)
    assert removed
    assert set(doc["mcpServers"]) == {"keep"}
    assert doc["permissions"]["allow"] == ["Read"]
    assert doc["env"] == {"KEEP": "yes"}
    assert doc["plugins"] == {"shared-marketplace": {"plugins": [{"name": "keep"}]}}
    assert doc["notes"] == [f"I wrote about {name}"]


def test_nested_hooks_only_remove_owned_command():
    doc = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "code-search-local warmup"},
                        {"type": "command", "command": "keep-hook"},
                    ],
                }
            ]
        }
    }
    cleanup.prune(doc)
    assert doc["hooks"]["SessionStart"][0]["hooks"] == [{"type": "command", "command": "keep-hook"}]


def test_codex_mcp_tool_cache_preserves_unrelated_servers():
    entries = [
        {"name": "alias", "serverInfo": {"name": "code-search-local"}},
        {"name": "keep", "serverInfo": {"name": "keep-server"}},
    ]
    doc = {"electron-persisted-atom-state": {"mcp-server-tools-cache-v2": {"catalog": entries}}}
    cleanup.prune(doc)
    assert entries == [{"name": "keep", "serverInfo": {"name": "keep-server"}}]


def test_toml_comments_jsonc_and_custom_endpoint(home):
    scanner = cleanup.Scanner(home)
    toml = write(
        home / ".codex/config.toml",
        '# keep comment\n[other]\nvalue = 1\n[mcp_servers.code_search_local]\ncommand = "server"\n',
    )
    jsonc = write(
        home / ".config/opencode/custom.jsonc",
        '{"mcp":{"alias":{"url":"http://localhost:9988/mcp"},"keep":{"url":"http://localhost:9999/mcp"}}}',
    )
    scanner.endpoints.add("http://localhost:9988/mcp")
    scanner.config(toml)
    scanner.config(jsonc)
    assert "# keep comment" in scanner.actions[("edit", str(toml))].after
    assert "mcp_servers.code_search_local" not in scanner.actions[("edit", str(toml))].after
    assert set(json.loads(scanner.actions[("edit", str(jsonc))].after)["mcp"]) == {"keep"}


def test_malformed_and_unsupported_references_are_reported(home):
    scanner = cleanup.Scanner(home)
    for name, content in [
        ("bad.json", "{code-search-local"),
        ("unrelated.json", "{oops"),
        ("config.yaml", "mcp: code-search-local"),
    ]:
        scanner.config(write(home / name, content))
    assert not scanner.actions
    assert {Path(f["path"]).name for f in scanner.findings} == {"bad.json", "config.yaml"}


def test_toml_arrays_and_home_project_do_not_block_service_cleanup(home):
    config = write(
        home / ".codex/config.toml",
        '# comment\n[projects."'
        + str(home)
        + '"]\ntrust_level="trusted"\n[mcp_servers.code-search-local]\nargs=["serve"]\n[other]\nvalues=["keep"]\n',
    )
    service = write(
        home / ".config/systemd/user/code-search-local.service",
        "[Service]\nExecStart=code-search-local serve\n",
    )
    scanner = cleanup.Scanner(home, scope="user")
    scanner.profiles()
    scanner.units()
    assert ("edit", str(config)) in scanner.actions
    assert any(a.target == str(service) and a.kind == "remove" for a in scanner.finish())


def test_history_jsonl_and_compressed_assets_are_not_read(home):
    history = write(home / ".claude/projects/session.jsonl", '{"prompt":"code-search-local"}\n')
    compressed = write(home / ".claude/plugins/example.json.gz", "invalidcompressed")
    scanner = cleanup.Scanner(home)
    scanner.profiles()
    assert history not in scanner.scanned
    assert compressed not in scanner.scanned


def test_editor_history_and_config_symlinks(home):
    history = write(
        home / ".config/Code/User/History/id/config.toml",
        '[mcp_servers.code-search-local]\ncommand="server"\n',
    )
    protected = write(home / "backups/config.json", '{"mcp":{"code-search-local":{}}}')
    alias = home / "linked-config.json"
    alias.symlink_to(protected)
    config = write(
        home / ".codex/config.toml", '[mcp_servers.code-search-local]\ncommand="server"\n'
    )
    (home / ".Codex").symlink_to(home / ".codex", target_is_directory=True)
    scanner = cleanup.Scanner(home)
    scanner.config(alias)
    scanner.profiles()
    assert history not in scanner.scanned
    assert protected not in scanner.scanned
    edits = [a for a in scanner.actions.values() if a.kind == "edit"]
    assert len(edits) == 1
    assert Path(edits[0].target).resolve() == config


def test_storage_aliases_and_models_are_preserved_with_index_removal(home, tmp_path):
    storage = tmp_path / "dedicated-data"
    index = write(storage / "state.sqlite3", "index")
    write(storage / "state.sqlite3-wal", "wal")
    write(storage / "projects/id/vectors.faiss", "index")
    model = write(storage / "models/unique-model/model.safetensors", "weights")
    write(storage / "runtimes/old/python", "runtime")
    alias = home / ".claude-code-search"
    alias.symlink_to(storage, target_is_directory=True)
    write(home / ".config/code-search-local/config.json", json.dumps({"storage": str(storage)}))
    scanner = cleanup.Scanner(home)
    scanner.app_state()
    actions = scanner.finish()
    assert not any(
        a.target in {str(alias), str(index), str(storage / "runtimes"), str(storage)}
        for a in actions
    )
    scanner = cleanup.Scanner(home, remove_indexes=True, remove_runtime_packages=True)
    scanner.app_state()
    actions = scanner.finish()
    assert any(a.target == str(index) for a in actions)
    assert any(a.target == str(storage / "projects") for a in actions)
    assert not any(Path(a.target) == model or Path(a.target) in model.parents for a in actions)
    assert not any(a.target == str(alias) for a in actions)
    assert model.read_text() == "weights"
    assert index.read_text() == "index"


def test_rejects_shared_paths_unverified_storage_and_nested_worktrees(home, tmp_path):
    scanner = cleanup.Scanner(home, remove_indexes=True, remove_runtime_packages=True)
    scanner.storage.update({home, tmp_path / "unverified"})
    write(home / "models/example", "data")
    owner = home / "code-search-local-cache"
    write(owner / "node_modules/deep/.git", "gitdir: /another/worktree\n")
    scanner.delete(owner, "candidate")
    scanner.delete(home, "candidate")
    scanner.delete(SCRIPT.parents[1], "candidate")
    assert not scanner.finish()
    assert any("worktree" in f["reason"] for f in scanner.findings)


def test_changed_config_and_replaced_symlink_fail_identity_checks(home):
    scanner = cleanup.Scanner(home)
    config = write(home / "config.json", '{"mcp":{"code-search-local":{}}}')
    scanner.config(config)
    action = scanner.actions[("edit", str(config))]
    assert cleanup.unchanged(action)
    config.write_text("{}")
    assert not cleanup.unchanged(action)
    target = write(home / "target", "contents")
    alias = home / "code-search-local"
    alias.symlink_to(target)
    scanner.delete(alias, "alias")
    action = scanner.actions[("remove", str(alias))]
    assert cleanup.unchanged(action)
    alias.unlink()
    alias.write_text("replacement")
    assert not cleanup.unchanged(action)


@pytest.mark.parametrize(
    "args,cwd,expected",
    [
        (["code-search-local", "serve"], "/", True),
        (["python", "-m", "code_search_local", "serve"], "/", True),
        (["python3", "mcp_server/server.py"], "/repo/claude-context-local", True),
        (
            [
                "uv",
                "run",
                "--directory",
                "/repo/claude-context-local",
                "python",
                "mcp_server/server.py",
            ],
            "/",
            True,
        ),
        (["uvx", "--from", "code-search-local", "code-search-local", "serve"], "/", True),
        (["python", "-u", "-m", "ClAuDe_Context_Local"], "/", True),
        (["claude", "Tell me about code-search-local"], "/repo/code-search-local", False),
        (["codex", "exec", "code-search-local serve"], "/", False),
        (["opencode", "run", "claude-context-local"], "/", False),
        (["python", "-c", "code-search-local"], "/", False),
        (["python", "-m", "pytest", "code-search-local"], "/", False),
        (["uv", "run", "--directory", "/repo/code-search-local", "pytest"], "/", False),
        (["bash", "-c", "code-search-local serve"], "/", False),
        (["python", "mcp_server/server.py"], "/repo/another-server", False),
        (["python", str(SCRIPT), "--dry-run"], str(SCRIPT.parent), False),
        (["code-search-locality"], "/", False),
    ],
)
def test_process_identity_uses_launch_arguments(args, cwd, expected):
    assert cleanup.owned_process({"args": args, "cwd": cwd}) is expected


def test_process_discovery_includes_children_excludes_ancestors_and_zombies(
    home, tmp_path, monkeypatch
):
    proc = tmp_path / "proc"
    proc.mkdir()
    info = {}
    for pid, ppid, args, state in [
        (400, 1, ["code-search-local", "serve"], "S"),
        (401, 400, ["worker"], "S"),
        (402, 1, ["code-search-local"], "Z"),
        (403, 1, ["codex", "code-search-local"], "S"),
    ]:
        (proc / str(pid)).mkdir()
        info[pid] = {
            "pid": pid,
            "ppid": ppid,
            "args": args,
            "state": state,
            "uid": home.stat().st_uid,
            "start_ticks": "123",
            "cwd": str(home),
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
    root = home / ".config/systemd/user"
    write(root / "code-search-local.path", "[Path]\nPathChanged=/config\n")
    write(
        root / "alias.service", "[Service]\nExecStart=/usr/bin/python -m code_search_local serve\n"
    )
    write(
        root / "unrelated.service",
        "# code-search-local documentation\n[Service]\nExecStart=/bin/true\n",
    )
    write(
        root / "other.service.d/override.conf",
        "[Service]\nEnvironment=CODE_SEARCH_STORAGE=/tmp/code-search-local\n",
    )
    scanner = cleanup.Scanner(home, scope="user")
    scanner.units()
    units = {a.details["unit"] for a in scanner.actions.values() if a.kind == "unit"}
    assert units == {"alias.service", "code-search-local.path"}
    assert any("unrelated unit" in f["reason"] for f in scanner.findings)


def make_environment(venv, *, installer="uv", name="code-search-local"):
    metadata = venv / "lib/python3.12/site-packages" / (name.replace("-", "_") + "-1.0.0.dist-info")
    write(metadata / "METADATA", f"Name: {name}\n")
    write(metadata / "INSTALLER", installer)
    write(venv / "pyvenv.cfg", "home = /usr/bin\n")
    write(venv / "bin/python", "fixture")
    if installer == "pip":
        write(venv / "lib/python3.12/site-packages/pip/__main__.py", "fixture")
    return metadata


def test_installer_receipts_and_default_runtime_retention(home, monkeypatch):
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    uv = home / ".local/share/uv/tools/code-search-local"
    make_environment(uv)
    write(uv / "uv-receipt.toml", '[tool]\nrequirements=[{name="code-search-local"}]\n')
    pipx = home / ".local/share/pipx/venvs/claude-context-local"
    make_environment(pipx, installer="pip", name="claude-context-local")
    write(
        pipx / "pipx_metadata.json",
        json.dumps({"main_package": {"package": "claude-context-local"}}),
    )
    shared = home / ".venvs/other"
    make_environment(shared, installer="pip")
    scanner = cleanup.Scanner(home, scope="user")
    scanner.installations()
    assert not scanner.finish()
    scanner = cleanup.Scanner(home, scope="user", remove_runtime_packages=True)
    scanner.installations()
    actions = {a.target: a for a in scanner.finish()}
    assert actions[str(uv)].details["commands"] == [
        ["/tools/uv", "tool", "uninstall", "code-search-local"]
    ]
    assert actions[str(uv)].details["environment"] == {"UV_TOOL_DIR": str(uv.parent)}
    assert actions[str(pipx)].details["commands"] == [
        ["/tools/pipx", "uninstall", "claude-context-local"]
    ]
    assert actions[str(pipx)].details["environment"] == {"PIPX_HOME": str(pipx.parent.parent)}
    assert actions[str(shared)].details["commands"] == [
        [str(shared / "bin/python"), "-m", "pip", "uninstall", "-y", "code-search-local"]
    ]
    assert all(a.kind == "package" and "cleanup_dir" not in a.details for a in actions.values())


def test_project_discovery_cache_manifest_and_backups(home, tmp_path):
    project = tmp_path / "workspace"
    write(project / ".mcp.json", '{"mcpServers":{"code-search-local":{},"keep":{}}}')
    write(home / ".claude.json", json.dumps({"projects": {str(project): {}}}))
    plugin = home / ".codex/plugins/cache/abc123"
    write(plugin / ".codex-plugin/plugin.json", '{"name":"code-search-local"}')
    backup = write(home / ".claude/backups/config.json", '{"mcp":{"code-search-local":{}}}')
    scanner = cleanup.Scanner(home)
    scanner.profiles()
    assert ("edit", str(project / ".mcp.json")) in scanner.actions
    assert ("remove", str(plugin)) in scanner.actions
    assert backup not in scanner.scanned


def test_shell_and_cron_preserve_compound_and_unrelated_commands(home):
    path = write(
        home / ".bashrc",
        'export CODE_SEARCH_STORAGE="/data"\nexport PATH="/repo/code-search-local/bin:$PATH"\nalias code-search-local="run server"\necho code-search-local\n',
    )
    scanner = cleanup.Scanner(home)
    scanner.launch_references()
    after = scanner.actions[("edit", str(path))].after
    assert "CODE_SEARCH_STORAGE" not in after
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
        (["--remove-indexes"], True, False),
        (["--remove-runtime-packages"], False, True),
        (["--remove-all"], True, True),
    ],
)
def test_removal_flag_matrix_is_read_only(home, monkeypatch, flags, indexes, runtimes):
    storage = home / "data"
    model = write(storage / "models/named-model/model.safetensors", "weights")
    index = write(storage / "state.sqlite3", "index")
    runtime = storage / "runtimes/release"
    write(runtime / "README.md", "Managed code-search-local runtime.\n")
    write(runtime / "uv.lock", "version = 1\n")
    make_environment(runtime / ".venv")
    config = write(
        home / ".config/opencode/opencode.json",
        '{"mcp":{"code-search-local":{},"keep":{}},"plugin":["code-search-local","keep"]}',
    )
    claude_mcp = write(
        home / ".claude.json", '{"mcpServers":{"claude-context-local":{},"keep":{}}}'
    )
    claude_plugins = write(
        home / ".claude/plugins/installed_plugins.json",
        '{"plugins":{"code-search-local@market":[{"scope":"user"}],"keep@market":[]}}',
    )
    claude_settings = write(
        home / ".claude/settings.json",
        '{"enabledPlugins":{"code-search-local@market":true,"keep@market":true}}',
    )
    codex = write(
        home / ".codex/config.toml",
        '[mcp_servers.code-search-local]\ncommand="server"\n[plugins."claude-context-local@market"]\nenabled=true\n[plugins."keep@market"]\nenabled=true\n',
    )
    caches = [home / name / "plugins/cache/code-search-local" for name in (".claude", ".codex")]
    for cache in caches:
        write(cache / "1.0.0/plugin.json", '{"name":"code-search-local"}')
    unit_root = home / ".config/systemd/user"
    unit_names = [
        "code-search-local.service",
        "code-search-local-marketplace.service",
        "code-search-local-marketplace.path",
        "code-search-local-marketplace.timer",
        "claude-context-local.service",
    ]
    for name in unit_names:
        write(unit_root / name, "[Unit]\nDescription=fixture\n")
    link = unit_root / "default.target.wants/code-search-local.service"
    link.parent.mkdir()
    link.symlink_to(unit_root / "code-search-local.service")
    unrelated_unit = write(unit_root / "keep.service", "[Service]\nExecStart=/bin/true\n")
    write(home / ".config/code-search-local/config.json", json.dumps({"storage": str(storage)}))
    before = {path: path.read_bytes() for path in home.rglob("*") if path.is_file()}
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    monkeypatch.setattr(cleanup.Scanner, "processes", lambda self: None)

    def forbidden(*args, **kwargs):
        pytest.fail("A dry-run attempted to modify the installation")

    monkeypatch.setattr(cleanup, "apply_plan", forbidden)
    monkeypatch.setattr(cleanup.subprocess, "run", forbidden)
    monkeypatch.setattr(cleanup.shutil, "rmtree", forbidden)
    monkeypatch.setattr(cleanup.os, "kill", forbidden)
    result = CliRunner().invoke(
        cleanup.main, ["--dry-run", "--json", "--home", str(home), "--scope", "user", *flags]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["remove_indexes"] is indexes
    assert report["remove_runtime_packages"] is runtimes
    assert report["models_preserved"] is True
    assert any(a["target"] == str(index) for a in report["actions"]) is indexes
    assert any(a["kind"] == "package" for a in report["actions"]) is runtimes
    assert any(a["target"] == str(config) and a["kind"] == "edit" for a in report["actions"])
    # Services and all harness registrations are always removed, including flags=[].
    planned = {(a["kind"], a["target"]): a for a in report["actions"]}
    for name in unit_names:
        assert ("unit", f"user:{name}") in planned
        assert ("remove", str(unit_root / name)) in planned
    assert ("remove", str(link)) in planned
    assert ("remove", str(unrelated_unit)) not in planned
    for cache in caches:
        assert ("remove", str(cache)) in planned
    for path, entries in [
        (claude_mcp, ["/mcpServers/claude-context-local"]),
        (claude_plugins, ["/plugins/code-search-local@market"]),
        (claude_settings, ["/enabledPlugins/code-search-local@market"]),
        (codex, ["/mcp_servers/code-search-local", "/plugins/claude-context-local@market"]),
        (config, ["/mcp/code-search-local", "/plugin/0"]),
    ]:
        assert planned[("edit", str(path))]["entries"] == entries
    assert all(
        Path(a["target"]) != model and Path(a["target"]) not in model.parents
        for a in report["actions"]
    )
    assert model.read_text() == "weights" and index.read_text() == "index"
    assert before == {path: path.read_bytes() for path in home.rglob("*") if path.is_file()}


@pytest.mark.parametrize("marker", ["directory", "file"])
def test_clones_and_linked_worktrees_always_preserve_runtime(home, tmp_path, monkeypatch, marker):
    project = tmp_path / "unrelated-project-name"
    env = project / ".venv"
    make_environment(env)
    if marker == "directory":
        (project / ".git").mkdir()
    else:
        write(project / ".git", "gitdir: /other/repo/.git/worktrees/test\n")
    scanner = cleanup.Scanner(
        home, remove_runtime_packages=True, remove_indexes=True, project_roots=[project]
    )
    scanner.python_environment(env)
    assert not scanner.finish()
    write(env / "uv-receipt.toml", '[tool]\nrequirements=[{name="code-search-local"}]\n')
    alias = home / ".local/share/uv/tools/code-search-local"
    alias.parent.mkdir(parents=True)
    alias.symlink_to(env, target_is_directory=True)
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    scanner.installations()
    assert not scanner.finish()
    assert any("worktree" in f["reason"] for f in scanner.findings)


def test_managed_runtime_uses_installer_then_dedicated_cleanup(home, monkeypatch):
    root = home / "data/runtimes/release"
    env = root / ".venv"
    make_environment(env)
    make_environment(env, name="dependency")
    write(root / "README.md", "Managed code-search-local runtime.\n")
    write(root / "uv.lock", "version=1\n")
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.storage.add(home / "data")
    scanner.installations()
    action = scanner.actions[("package", str(env))]
    assert action.details["commands"] == [
        [
            "/tools/uv",
            "pip",
            "uninstall",
            "--python",
            str(env / "bin/python"),
            "code-search-local",
            "dependency",
        ]
    ]
    assert action.details["cleanup_dir"] == str(root)
    assert cleanup.unchanged(action)
    (root / "uv.lock").write_text("changed")
    assert not cleanup.unchanged(action)


def test_unknown_installer_retained_and_models_block_parent_removal(home):
    env = home / ".venvs/unknown"
    make_environment(env, installer="unknown")
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.python_environment(env)
    assert not scanner.actions
    parent = home / "owned-plugin"
    write(parent / "models/special/model.safetensors", "weights")
    scanner.delete(parent, "matching plugin")
    assert not scanner.actions
    assert any("Unknown/missing INSTALLER" in f["reason"] for f in scanner.findings)
    assert any("downloaded models" in f["reason"] for f in scanner.findings)


def test_uvx_cache_cleanup_uses_uv_and_respects_worktrees(home, monkeypatch):
    cache = home / ".cache/uv"
    make_environment(cache / "archive-v0/hash")
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.installations()
    action = scanner.actions[("package", str(cache))]
    assert action.details["commands"] == [["/tools/uv", "cache", "clean", "code-search-local"]]
    assert not any(a.kind == "remove" for a in scanner.actions.values())
    write(cache / "archive-v0/hash/.git", "gitdir: /worktree\n")
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
    root = home / ".codex"
    path = write(root / relative, '{"mcp_servers":{"code-search-local":{}}}')
    alias = write(home / "placeholder.json")
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
    root = home / "backups/codex"
    write(root / "config.toml", '[mcp_servers.code-search-local]\ncommand="server"\n')
    write(root / "plugins/code-search-local/plugin.json", '{"name":"code-search-local"}')
    write(
        home / ".config/code-search-local/installation.json",
        json.dumps({"targets": [{"configs": [str(root / "config.toml")]}]}),
    )
    monkeypatch.setenv("CODEX_HOME", str(root))
    scanner = cleanup.Scanner(home, scan_roots=[root])
    scanner.app_state()
    scanner.profiles()
    assert not scanner.scanned
    assert all(not cleanup.backup_path(a.target) for a in scanner.actions.values())


@pytest.mark.parametrize(
    "name",
    [
        "old_fractionfield.py",
        "old_polynomialring.py",
        "gpurun-old",
        "saved_variable_hooks.h",
        "saved_variable.h",
        "config.json",
        "config.toml",
    ],
)
def test_normal_package_filenames_are_not_treated_as_recovery_files(name):
    assert not cleanup.backup_name(name)


def test_parent_removal_retains_nested_backups_and_eligible_siblings(home):
    owner = home / ".claude/plugins/code-search-local"
    active = write(owner / "plugin.json", '{"name":"code-search-local"}')
    backup = write(owner / "nested/saved/config.json", "recovery data")
    sibling = write(owner / "nested/active.json", "active")
    scanner = cleanup.Scanner(home)
    scanner.delete(owner, "matching plugin")
    targets = {Path(a.target) for a in scanner.finish()}
    assert targets == {active, sibling}
    assert backup.read_text() == "recovery data"
    assert active.exists() and sibling.exists()


@pytest.mark.parametrize("installer", ["uv", "pipx"])
def test_native_package_uninstall_cannot_remove_existing_backups(home, monkeypatch, installer):
    root = home / (".local/share/uv/tools" if installer == "uv" else ".local/share/pipx/venvs")
    env = root / "code-search-local"
    if installer == "uv":
        write(env / "uv-receipt.toml", '[tool]\nrequirements=[{name="code-search-local"}]\n')
    else:
        write(env / "pipx_metadata.json", '{"main_package":{"package":"code-search-local"}}')
    saved = write(env / "config.json.bak", "recovery data")
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.installations()
    assert not scanner.actions
    assert any("backups" in item["reason"] for item in scanner.findings)
    assert saved.read_text() == "recovery data"


def test_managed_runtime_parent_backups_block_package_uninstall(home, monkeypatch):
    root = home / "data/runtimes/release"
    make_environment(root / ".venv")
    write(root / "README.md", "Managed code-search-local runtime.\n")
    write(root / "uv.lock", "version=1\n")
    write(root / "uv.lock.bak", "recovery lock")
    monkeypatch.setattr(cleanup, "manager_executable", lambda name: "/tools/" + name)
    scanner = cleanup.Scanner(home, remove_runtime_packages=True)
    scanner.storage.add(home / "data")
    scanner.installations()
    assert not scanner.actions
    assert "backups" in scanner.artifact_guard(root, environment=True)


@pytest.mark.parametrize("installer", ["uv", "pipx"])
def test_installer_receipt_symlinks_do_not_read_recovery_data(home, monkeypatch, installer):
    env = home / (
        ".local/share/uv/tools/code-search-local"
        if installer == "uv"
        else ".local/share/pipx/venvs/code-search-local"
    )
    receipt = env / ("uv-receipt.toml" if installer == "uv" else "pipx_metadata.json")
    saved = write(home / "backups/receipt", "must not be read")
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
    owner = home / "code-search-local-cache"
    write(owner / "config.json", "{}")
    scanner = cleanup.Scanner(home)
    scanner.delete(owner, "matching cache")
    assert ("remove", str(owner)) in scanner.actions
    write(owner / "config.json.bak", "recovery data")
    assert "backups" in scanner.artifact_guard(owner)
    # Inspection only: the destructive branch remains deliberately unexecuted.


@pytest.mark.parametrize(
    "flags", [[], ["--remove-indexes"], ["--remove-runtime-packages"], ["--remove-all"]]
)
def test_all_cleanup_modes_keep_backups_and_still_remove_active_registrations(
    home, monkeypatch, flags
):
    config = write(
        home / ".codex/config.toml", '[mcp_servers.code-search-local]\ncommand="server"\n'
    )
    backup = write(home / ".codex/config.toml.bak", config.read_text())
    unit = write(
        home / ".config/systemd/user/code-search-local.service",
        "[Service]\nExecStart=code-search-local serve\n",
    )
    saved_unit = write(unit.with_suffix(".service.bak"), unit.read_text())
    archived_unit = write(unit.parent / "backups/code-search-local-old.service", unit.read_text())
    storage = home / ".code-search-local"
    write(storage / "state.sqlite3", "index")
    legacy = write(storage / "legacy-backups/projects/id/index.json", "saved index")
    nested = write(storage / "projects/id/index.json.bak", "saved index")
    write(storage / "projects/id/vectors.faiss", "active index")
    monkeypatch.setattr(cleanup.Scanner, "processes", lambda self: None)

    def forbidden(*args, **kwargs):
        pytest.fail("Dry-run attempted a mutation")

    monkeypatch.setattr(cleanup, "apply_plan", forbidden)
    monkeypatch.setattr(cleanup.subprocess, "run", forbidden)
    before = {p: p.read_bytes() for p in home.rglob("*") if p.is_file()}
    result = CliRunner().invoke(
        cleanup.main, ["--dry-run", "--json", "--home", str(home), "--scope", "user", *flags]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["counts"]["unit"] == 1
    assert any(a["kind"] == "edit" and a["target"] == str(config) for a in report["actions"])
    assert any(a["kind"] == "remove" and a["target"] == str(unit) for a in report["actions"])
    for action in report["actions"]:
        target = Path(action["target"])
        assert not cleanup.backup_path(target)
        assert all(
            target != p and target not in p.parents
            for p in (backup, saved_unit, archived_unit, legacy, nested)
        )
    assert before == {p: p.read_bytes() for p in home.rglob("*") if p.is_file()}


def test_reports_show_match_identity_and_prioritize_active_registrations(home, monkeypatch):
    cached = write(
        home / ".codex/.codex-global-state.json",
        json.dumps(
            {
                "electron-persisted-atom-state": {
                    "mcp-server-tools-cache-v2": {
                        "catalog": [
                            {"name": "unrelated", "serverInfo": None},
                            {"name": "keep", "description": "mentions code-search-local"},
                            {
                                "name": "code-search-local",
                                "serverInfo": {"name": "code-search-local"},
                                "token": "DO_NOT_SHOW",
                            },
                        ]
                    }
                }
            }
        ),
    )
    active = write(
        home / ".codex/config.toml", '[mcp_servers.code-search-local]\ncommand="server"\n'
    )
    (home / ".Codex").symlink_to(home / ".codex", target_is_directory=True)
    scanner = cleanup.Scanner(home)
    scanner.profiles()
    actions = scanner.finish()
    assert Path(actions[0].target).resolve() == active
    action = next(a for a in actions if Path(a.target).resolve() == cached)
    public = action.public()
    assert public["target"] == str(cached)
    assert public["matches"] == [
        {
            "entry": "/electron-persisted-atom-state/mcp-server-tools-cache-v2/catalog/2",
            "category": "cached MCP discovery entry",
            "matched_fields": [
                {"field": "name", "matched_name": "code-search-local"},
                {"field": "serverInfo.name", "matched_name": "code-search-local"},
            ],
        }
    ]
    assert not {"identity", "resolved", "evidence", "before", "after"} & public.keys()
    assert "DO_NOT_SHOW" not in json.dumps(public)
    retained = json.loads(action.after)["electron-persisted-atom-state"][
        "mcp-server-tools-cache-v2"
    ]["catalog"]
    assert [entry["name"] for entry in retained] == ["unrelated", "keep"]
    monkeypatch.setattr(cleanup.Scanner, "scan", lambda self: actions)
    result = CliRunner().invoke(cleanup.main, ["--dry-run", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "name: code-search-local; serverInfo.name: code-search-local" in result.output
    assert result.output.index(str(active)) < result.output.index(str(cached))
    assert "DO_NOT_SHOW" not in result.output
