"""Exercise native marketplace installation in isolated client configurations."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.packaging
def test_both_native_marketplaces(tmp_path):
    if os.environ.get("CODE_SEARCH_MARKETPLACES") != "1":
        pytest.skip("Set CODE_SEARCH_MARKETPLACES=1 with Claude and Codex CLIs installed")
    catalog = tmp_path / "local marketplace"
    catalog.mkdir()
    (tmp_path / "codex").mkdir()
    (tmp_path / "claude").mkdir()
    for directory in (".claude-plugin", "plugins"):
        shutil.copytree(ROOT / directory, catalog / directory)
    env = {
        **os.environ,
        "CODEX_HOME": str(tmp_path / "codex"),
        "CLAUDE_CONFIG_DIR": str(tmp_path / "claude"),
    }

    def run(*args):
        result = subprocess.run(
            [str(a) for a in args],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    run("claude", "plugin", "validate", catalog / ".claude-plugin/marketplace.json")
    run("claude", "plugin", "marketplace", "add", catalog)
    run("claude", "plugin", "install", "code-search-local@code-search-local")
    assert "code-search-local" in run("claude", "plugin", "list", "--json")
    run("codex", "plugin", "marketplace", "add", catalog, "--json")
    run("codex", "plugin", "add", "code-search-local@code-search-local", "--json")
    assert "code-search-local" in run("codex", "plugin", "list", "--json")
    for client in ("claude", "codex"):
        skills = list((tmp_path / client).rglob("SKILL.md"))
        assert any("code-search-local==0.2.0" in skill.read_text() for skill in skills)
    # Removing either plugin must not remove the other client's installed package.
    run("claude", "plugin", "uninstall", "code-search-local@code-search-local")
    assert "code-search-local" in run("codex", "plugin", "list", "--json")
    run("codex", "plugin", "remove", "code-search-local@code-search-local", "--json")
    (tmp_path / "marketplace-validation.json").write_text(
        json.dumps({"claude": "passed", "codex": "passed"})
    )
