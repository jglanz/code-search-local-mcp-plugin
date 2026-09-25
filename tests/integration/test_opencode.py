"""Verify generated configuration with OpenCode's real HTTP MCP client."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from code_search_local import harnesses
from code_search_local.client import Client
from code_search_local.config import Settings
from tests.helpers import free_port, wait_healthy


@pytest.mark.clients
@pytest.mark.parametrize("profile", ["global_jsonc", "custom_file", "custom_directory"])
def test_opencode_connects_replaces_and_unregisters(tmp_path, monkeypatch, profile):
    if os.environ.get("CODE_SEARCH_OPENCODE_TESTS") != "1":
        pytest.skip("Set CODE_SEARCH_OPENCODE_TESTS=1 with opencode on PATH")
    executable = shutil.which(os.environ.get("CODE_SEARCH_OPENCODE_BIN", "opencode"))
    assert executable, "OpenCode CLI is required for this acceptance lane"
    for name in list(os.environ):
        if name.startswith("OPENCODE_"):
            monkeypatch.delenv(name)
    for name, path in {
        "HOME": tmp_path / "home",
        "XDG_CACHE_HOME": tmp_path / "cache",
        "XDG_DATA_HOME": tmp_path / "data",
        "XDG_STATE_HOME": tmp_path / "state",
    }.items():
        path.mkdir()
        monkeypatch.setenv(name, str(path))
    monkeypatch.setenv("OPENCODE_DISABLE_AUTOUPDATE", "true")
    monkeypatch.setenv("OPENCODE_DISABLE_DEFAULT_PLUGINS", "true")
    global_config = Path(os.environ["XDG_CONFIG_HOME"]) / "opencode/opencode.jsonc"
    config = global_config
    if profile == "custom_file":
        config = tmp_path / "custom.jsonc"
        monkeypatch.setenv("OPENCODE_CONFIG", str(config))
    elif profile == "custom_directory":
        config = tmp_path / "custom/opencode.jsonc"
        monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(config.parent))
    config.parent.mkdir(parents=True, exist_ok=True)
    original = (
        '// preserve original in backup\n{"mcp": {'
        '"code-search-local": {"type":"local","command":["stale"],"enabled":false},'
        '"unrelated": {"type":"local","command":["unused"],"enabled":false}}}'
    )
    config.write_text(original)
    settings = Settings(storage=str(tmp_path / "storage"), port=free_port(), watch=False)
    with (tmp_path / "daemon.log").open("w+") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.daemon",
                "--fake",
                "--storage",
                settings.storage,
                "--port",
                str(settings.port),
            ],
            stdout=log,
            stderr=log,
        )
        try:
            wait_healthy(process, Client(settings), log)
            target = harnesses.targets(("opencode",))[0]
            harnesses.register(settings, [target])
            assert config.with_name(config.name + ".code-search-local.bak").read_text() == original

            def list_servers():
                result = subprocess.run(
                    [executable, "mcp", "list"],
                    cwd=tmp_path,
                    env=os.environ.copy(),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", result.stdout + result.stderr)
                assert result.returncode == 0, output
                return output

            assert re.search(r"code-search-local\s+connected", list_servers())
            harnesses.register(settings, [target])
            assert re.search(r"code-search-local\s+connected", list_servers())
            harnesses.unregister(target)
            harnesses.unregister(target)
            output = list_servers()
            assert "code-search-local" not in output and "unrelated" in output
            assert harnesses.read_document(config)["mcp"] == {
                "unrelated": {"type": "local", "command": ["unused"], "enabled": False}
            }
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(15)
