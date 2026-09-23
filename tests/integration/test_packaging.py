"""Install released artifacts from outside the source checkout with all four tools."""

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from code_search_local.install import uv_executable

pytestmark = pytest.mark.packaging
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    if os.environ.get("CODE_SEARCH_PACKAGING") != "1":
        pytest.skip("Set CODE_SEARCH_PACKAGING=1 for the artifact installation matrix")
    output = tmp_path_factory.mktemp("distributions")
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(output.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "code_search_local/runtime/uv.lock" in names
        assert "code_search_local/assets/plugin/plugin.json" in names
        assert sum(name.endswith("/plugin.json") for name in names) == 1
        assert not any(
            ".codex-plugin/" in name or ".claude-plugin/plugin.json" in name for name in names
        )
        assert not any(".omc" in name for name in names)
    return {"wheel": wheel, "sdist": next(output.glob("*.tar.gz"))}


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
@pytest.mark.parametrize("installer", ["uv", "uvx", "pip", "pipx"])
def test_install_outside_checkout(artifacts, artifact, installer, tmp_path):
    source = artifacts[artifact]
    outside = tmp_path / "outside"
    outside.mkdir()
    env = {
        **os.environ,
        "UV_TOOL_DIR": str(tmp_path / "uv-tools"),
        "UV_TOOL_BIN_DIR": str(tmp_path / "bin"),
        "PIPX_HOME": str(tmp_path / "pipx"),
        "PIPX_BIN_DIR": str(tmp_path / "bin"),
        "PIPX_MAN_DIR": str(tmp_path / "man"),
        "PYTHONNOUSERSITE": "1",
    }
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)

    def run(args):
        result = subprocess.run(
            [str(a) for a in args],
            cwd=outside,
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        return result.stdout

    uv = uv_executable()
    if installer == "uv":
        run([uv, "tool", "install", source])
        command = [tmp_path / "bin" / "code-search-local"]
    elif installer == "uvx":
        command = [Path(sys.executable).parent / "uvx", "--from", source, "code-search-local"]
    elif installer == "pip":
        venv = tmp_path / "venv"
        run([sys.executable, "-m", "venv", venv])
        run([venv / "bin" / "python", "-m", "pip", "install", source])
        command = [venv / "bin" / "code-search-local"]
    else:
        run([sys.executable, "-m", "pipx", "install", "--python", sys.executable, source])
        command = [tmp_path / "bin" / "code-search-local"]
    assert "0.2.0" in run([*command, "--version"])
    config = json.loads(run([*command, "doctor", "--backend", "rocm"]))
    assert config["settings"]["backend"] == "rocm"
    assert "stats" in run([*command, "--help"])
