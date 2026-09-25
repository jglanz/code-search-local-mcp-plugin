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

from code_search_local.harnesses import read_document, save_document
from code_search_local.lifecycle import guard_paths
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


@pytest.mark.parametrize("removal", ["claude", "codex", "cli"])
def test_native_uninstall_removes_running_user_service(tmp_path, removal):
    if (
        os.environ.get("CODE_SEARCH_MARKETPLACES") != "1"
        or os.environ.get("CODE_SEARCH_SYSTEMD_TESTS") != "1"
    ):
        pytest.skip("Set CODE_SEARCH_MARKETPLACES=1 and CODE_SEARCH_SYSTEMD_TESTS=1")
    service = "code-search-local-marketplace-test-" + uuid.uuid4().hex[:12] + ".service"
    unit = Path.home() / ".config/systemd/user" / service
    guards = guard_paths(unit)
    catalog = tmp_path / "marketplace"
    for directory in (".claude-plugin", "plugins"):
        shutil.copytree(ROOT / directory, catalog / directory)
    env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
    env.pop("PYTHONPATH", None)
    Path(env["CODEX_HOME"]).mkdir(parents=True)
    Path(env["CLAUDE_CONFIG_DIR"]).mkdir(parents=True)

    def run(*args, check=True):
        result = subprocess.run(
            [str(arg) for arg in args],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=90,
        )
        with (tmp_path / "commands.log").open("a") as log:
            log.write(result.stdout + "\n" + result.stderr + "\n")
        if check:
            assert result.returncode == 0, result.stdout + result.stderr
        return result

    def cli(*args):
        return run(sys.executable, "-c", DRIVER, service, *args)

    config = Path(env["XDG_CONFIG_HOME"])
    codex_config = Path(env["CODEX_HOME"]) / "config.toml"
    claude_config = Path(env["CLAUDE_CONFIG_DIR"]) / ".claude.json"
    opencode_config = config / "opencode/opencode.jsonc"
    opencode_config.parent.mkdir(parents=True)
    opencode_config.write_text(
        '// keep other servers\n{"mcp":{"other":{"type":"local","command":["other"]}}}'
    )
    storage = tmp_path / "storage"
    storage.mkdir(exist_ok=True)
    retained = storage / "preserved-index"
    retained.write_text("existing index")
    try:
        run("claude", "plugin", "marketplace", "add", catalog)
        run("claude", "plugin", "install", ID)
        run("codex", "plugin", "marketplace", "add", catalog, "--json")
        run("codex", "plugin", "add", ID, "--json")
        cli(
            "setup",
            "--marketplace",
            "--agent-harness",
            "all",
            "--backend",
            "cpu",
            "--storage",
            storage,
            "--port",
            free_port(),
        )
        assert unit.exists() and all(path.exists() for path in guards)
        assert run("systemctl", "--user", "is-active", service).stdout.strip() == "active"
        assert (
            "http://127.0.0.1:" in run("codex", "mcp", "get", "code-search-local", "--json").stdout
        )
        assert "http://127.0.0.1:" in run("claude", "mcp", "get", "code-search-local").stdout
        if removal == "cli":
            cli("uninstall")
            cli("uninstall")  # repeat is safe even after the recorded installation is gone
            assert '"installed": []' in run("codex", "plugin", "list", "--json").stdout
            assert json.loads(run("claude", "plugin", "list", "--json").stdout) == []
        else:
            args = ("--scope", "user") if removal == "claude" else ("--json",)
            if removal == "claude":
                run(removal, "plugin", "disable", ID, *args)
            else:
                # Codex's enabled switch is stored in config, without a CLI disable subcommand.
                document = read_document(codex_config)
                document["plugins"][ID]["enabled"] = False
                save_document(codex_config, document)
            cli("marketplace-check")
            assert unit.exists(), "Disabling must leave the shared service running"
            if removal == "codex":
                # Deliberately miss the registry event and exercise the real fallback timer.
                run("systemctl", "--user", "stop", guards[0].name)
            run(removal, "plugin", "uninstall" if removal == "claude" else "remove", ID, *args)
            deadline = time.monotonic() + 50
            while unit.exists() or (config / "code-search-local/installation.json").exists():
                assert time.monotonic() < deadline, run(
                    "journalctl", "--user", "-u", guards[-1].name, "--no-pager"
                ).stdout
                time.sleep(0.2)
            other = "claude" if removal == "codex" else "codex"
            assert ID in run(other, "plugin", "list", "--json").stdout
        assert not unit.exists() and not any(path.exists() for path in guards)
        assert run("systemctl", "--user", "is-active", service, check=False).returncode != 0
        assert "code-search-local" not in read_document(codex_config).get("mcp_servers", {})
        assert "code-search-local" not in read_document(claude_config).get("mcpServers", {})
        assert read_document(opencode_config)["mcp"] == {
            "other": {"type": "local", "command": ["other"]}
        }
        assert retained.read_text() == "existing index"
    finally:
        run(
            "systemctl",
            "--user",
            "disable",
            "--now",
            service,
            *(path.name for path in guards[:2]),
            check=False,
        )
        run("systemctl", "--user", "stop", guards[-1].name, check=False)
        for path in [unit, *guards]:
            path.unlink(missing_ok=True)
        run("systemctl", "--user", "daemon-reload", check=False)
        run("claude", "plugin", "uninstall", ID, "--scope", "user", check=False)
        run("codex", "plugin", "remove", ID, "--json", check=False)
