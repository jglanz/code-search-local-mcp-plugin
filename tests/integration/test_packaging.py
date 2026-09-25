"""Install released artifacts from outside the source checkout with all four tools."""

import json
import os
import signal
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from code_search_local import __version__
from code_search_local.client import Client
from code_search_local.config import Settings
from code_search_local.install import uv_executable
from tests.helpers import copy_source_checkout, free_port, wait_healthy

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
        assert archive.read("code_search_local/runtime/uv.lock") == (ROOT / "uv.lock").read_bytes()
        assert (
            archive.read("code_search_local/runtime/pyproject.toml")
            == (ROOT / "pyproject.toml").read_bytes()
        )
        assert "code_search_local/assets/plugin/plugin.json" in names
        assert sum(name.endswith("/plugin.json") for name in names) == 1
        assert not any(
            ".codex-plugin/" in name or ".claude-plugin/plugin.json" in name for name in names
        )
    sdist = next(output.glob("*.tar.gz"))
    with tarfile.open(sdist) as archive:
        names = [name.split("/", 1)[-1] for name in archive.getnames()]
        assert "uv.lock" in names
        assert "plugins/code-search-local/plugin.json" in names
        assert "tests/integration/test_packaging.py" in names
        assert "scripts/build_backend.py" not in names
        assert "MANIFEST.in" not in names
        assert not any(
            name.startswith(("src/code_search_local/runtime/", "src/code_search_local/assets/"))
            for name in names
        )
    return {"wheel": wheel, "sdist": sdist}


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
        python = [tmp_path / "uv-tools" / "code-search-local" / "bin" / "python"]
    elif installer == "uvx":
        command = [Path(sys.executable).parent / "uvx", "--from", source, "code-search-local"]
        python = [Path(sys.executable).parent / "uvx", "--from", source, "python"]
    elif installer == "pip":
        venv = tmp_path / "venv"
        run([sys.executable, "-m", "venv", venv])
        run([venv / "bin" / "python", "-m", "pip", "install", source])
        command = [venv / "bin" / "code-search-local"]
        python = [venv / "bin" / "python"]
    else:
        run([sys.executable, "-m", "pipx", "install", "--python", sys.executable, source])
        command = [tmp_path / "bin" / "code-search-local"]
        python = [tmp_path / "pipx" / "venvs" / "code-search-local" / "bin" / "python"]
    assert __version__ in run([*command, "--version"])
    config = json.loads(run([*command, "doctor", "--backend", "rocm"]))
    assert config["settings"]["backend"] == "rocm"
    assert "stats" in run([*command, "--help"])
    probe = """
import json
from importlib.metadata import distribution
from code_search_local import __version__
from code_search_local.install import runtime_identity
dist = distribution("code-search-local")
assert dist.version == __version__
resources = dist.locate_file("code_search_local")
assert (resources / "runtime/pyproject.toml").is_file()
assert (resources / "runtime/uv.lock").is_file()
assert json.loads((resources / "assets/plugin/plugin.json").read_text())["version"] == __version__
print(runtime_identity())
"""
    assert run([*python, "-c", probe]).startswith(__version__ + "-")


def test_editable_install_and_metadata_only_runtime(artifacts, tmp_path):
    """Resources work without generated source copies or the original checkout at runtime."""
    with tarfile.open(artifacts["sdist"]) as archive:
        archive.extractall(tmp_path / "source", filter="data")
    source = next((tmp_path / "source").iterdir())
    venv = tmp_path / "venv"
    python = venv / "bin/python"
    uv = uv_executable()
    subprocess.run([uv, "venv", venv, "--python", sys.executable], check=True)
    subprocess.run([uv, "pip", "install", "--python", python, "--editable", source], check=True)
    probe = """
import json
import sys
from pathlib import Path
from code_search_local import install
from code_search_local.config import Settings
install.run = lambda *args, **kwargs: None
python = install.install_runtime(Settings(storage=sys.argv[1]), "cpu")
print(json.dumps(str(python.parent.parent.parent)))
"""
    result = subprocess.run(
        [python, "-c", probe, tmp_path / "state"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    runtime = Path(json.loads(result.stdout))
    for name in ("pyproject.toml", "uv.lock"):
        assert (runtime / name).read_bytes() == (source / name).read_bytes()
    assert not (source / "src/code_search_local/runtime").exists()
    assert not (source / "src/code_search_local/assets").exists()
    source.rename(tmp_path / "removed-checkout")
    subprocess.run(
        [
            uv,
            "sync",
            "--project",
            runtime,
            "--locked",
            "--no-dev",
            "--no-install-project",
            "--extra",
            "server",
            "--extra",
            "cpu",
            "--dry-run",
        ],
        cwd=tmp_path,
        check=True,
    )


def test_hatch_source_workflow_uses_backend_environment(tmp_path):
    if os.environ.get("CODE_SEARCH_PACKAGING") != "1":
        pytest.skip("Set CODE_SEARCH_PACKAGING=1 for source workflow acceptance")
    source = copy_source_checkout(tmp_path / "source with spaces")
    settings = Settings(storage=str(tmp_path / "state"), port=free_port(), watch=False)
    env = {
        **os.environ,
        "HATCH_DATA_DIR": str(tmp_path / "hatch-data"),
        "HATCH_CACHE_DIR": str(tmp_path / "hatch-cache"),
        "HATCH_ENV": "default",
        "CODE_SEARCH_STORAGE": settings.storage,
    }
    for name in (
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "UV_PROJECT_ENVIRONMENT",
        "HATCH_ENV_TYPE_VIRTUAL_PATH",
        "CODE_SEARCH_PORT",
        "CODE_SEARCH_DEV_BACKEND",
    ):
        env.pop(name, None)
    hatch = [sys.executable, "-m", "hatch"]

    def run(*args):
        result = subprocess.run(
            [*hatch, *args], cwd=source, env=env, text=True, capture_output=True, timeout=240
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        return result.stdout.strip()

    # No build is needed to execute the live checkout.
    assert __version__ in run("run", "cpu:cli", "--version")
    assert not (source / "dist").exists()
    expected = source / ".venvs/cpu"
    assert Path(run("env", "find", "cpu")) == expected
    assert Path(run("env", "find", "cuda")) == source / ".venvs/cuda"
    assert Path(run("env", "find", "rocm")) == source / ".venvs/rocm"
    assert "--source" in run("run", "setup", "--help")
    # Building a release can reuse the CPU tooling environment afterwards.
    run("build")
    assert Path(run("env", "find")) == expected
    assert Path(run("env", "find", "hatch-build")) == expected
    run("run", "cpu:sync")
    assert __version__ in run("run", "cli", "--version")
    location = run(
        "run", "python", "-c", "import code_search_local; print(code_search_local.__file__)"
    )
    assert Path(location) == source / "src/code_search_local/__init__.py"
    cli = source / "src/code_search_local/cli.py"
    cli.write_text(cli.read_text().replace("Local semantic search", "Editable source sentinel"))
    assert "Editable source sentinel" in run("run", "cli", "--help")
    for command in (
        [expected / "bin/python", "-m", "code_search_local", "--help"],
        [expected / "bin/code-search-local", "--help"],
    ):
        result = subprocess.run(
            command, cwd=source, env=env, text=True, capture_output=True, timeout=30
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        assert "Editable source sentinel" in result.stdout
    run("run", "lint")
    run("run", "test", "tests/unit/test_config_cli.py", "-q")
    assert [path.parent for path in tmp_path.rglob("pyvenv.cfg")] == [expected]

    env["CODE_SEARCH_PORT"] = str(settings.port)
    with (tmp_path / "source-server.log").open("w+") as log:
        process = subprocess.Popen(
            [*hatch, "run", "serve", "--backend", "cpu", "--offline", "--no-watch"],
            cwd=source,
            env=env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            wait_healthy(process, Client(settings), log)
            snapshot = json.loads(run("run", "cli", "stats", "--json"))
            assert snapshot["online"] is True
            assert snapshot["projects"] == {}
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=30)
