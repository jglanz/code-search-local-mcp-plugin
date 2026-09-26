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

from code_search_local import __version__, constants
from code_search_local.client import Client
from code_search_local.config import Settings
from code_search_local.install import uv_executable
from tests import constants as test_constants
from tests.helpers import copy_source_checkout, free_port, install_pipx_package, wait_healthy

pytestmark = pytest.mark.packaging
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope=test_constants.FIXTURE_SCOPE_MODULE)
def artifacts(tmp_path_factory):
    if os.environ.get(test_constants.ENV_CODE_SEARCH_PACKAGING) != constants.ENV_ENABLED:
        pytest.skip("Set CODE_SEARCH_PACKAGING=1 for the artifact installation matrix")
    output = tmp_path_factory.mktemp(test_constants.PATH_DISTRIBUTIONS)
    subprocess.run(
        [
            sys.executable,
            constants.SHORT_OPTION_M,
            "build",
            test_constants.OPTION_OUTDIR,
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(output.glob(test_constants.PATH_WHL))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "code_search_local/runtime/uv.lock" in names
        assert (
            archive.read("code_search_local/runtime/uv.lock")
            == (ROOT / constants.PATH_UV_LOCK).read_bytes()
        )
        assert (
            archive.read("code_search_local/runtime/pyproject.toml")
            == (ROOT / constants.PATH_PYPROJECT_TOML).read_bytes()
        )
        assert "code_search_local/assets/plugin/plugin.json" in names
        assert sum(name.endswith("/plugin.json") for name in names) == 1
        assert not any(
            ".codex-plugin/" in name or ".claude-plugin/plugin.json" in name for name in names
        )
    sdist = next(output.glob(test_constants.PATH_TAR_GZ))
    with tarfile.open(sdist) as archive:
        names = [name.split("/", 1)[-1] for name in archive.getnames()]
        assert constants.PATH_UV_LOCK in names
        assert "plugins/code-search-local/plugin.json" in names
        assert "tests/integration/test_packaging.py" in names
        assert "scripts/build_backend.py" not in names
        assert test_constants.VALUE_MANIFEST_IN not in names
        assert not any(
            name.startswith(("src/code_search_local/runtime/", "src/code_search_local/assets/"))
            for name in names
        )
    return {test_constants.KEY_WHEEL: wheel, test_constants.KEY_SDIST: sdist}


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
@pytest.mark.parametrize("installer", ["uv", "uvx", constants.COMMAND_PIP, "pipx"])
def test_install_outside_checkout(artifacts, artifact, installer, tmp_path):
    source = artifacts[artifact]
    outside = tmp_path / test_constants.PATH_OUTSIDE
    outside.mkdir()
    env = {
        **os.environ,
        test_constants.ENV_UV_TOOL_DIR: str(tmp_path / test_constants.PATH_UV_TOOLS),
        test_constants.ENV_UV_TOOL_BIN_DIR: str(tmp_path / constants.BIN_DIRECTORY),
        test_constants.ENV_PIPX_HOME: str(tmp_path / test_constants.PATH_PIPX),
        test_constants.ENV_PIPX_BIN_DIR: str(tmp_path / constants.BIN_DIRECTORY),
        test_constants.ENV_PIPX_MAN_DIR: str(tmp_path / test_constants.PATH_MAN),
        constants.ENV_PYTHONNOUSERSITE: constants.ENV_ENABLED,
    }
    env.pop(constants.ENV_PYTHONPATH, None)
    env.pop(constants.ENV_VIRTUAL_ENV, None)

    def run(args):
        result = subprocess.run(
            [str(a) for a in args],
            cwd=outside,
            env=env,
            capture_output=True,
            text=True,
            timeout=test_constants.COMMAND_TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        return result.stdout

    uv = uv_executable()
    if installer == test_constants.VALUE_UV:
        run([uv, constants.KEY_TOOL, constants.COMMAND_INSTALL, source])
        command = [tmp_path / constants.BIN_DIRECTORY / constants.APPLICATION_NAME]
        python = [
            tmp_path
            / test_constants.PATH_UV_TOOLS
            / constants.APPLICATION_NAME
            / constants.BIN_DIRECTORY
            / constants.KEY_PYTHON
        ]
    elif installer == test_constants.VALUE_UVX:
        command = [
            Path(sys.executable).parent / test_constants.VALUE_UVX,
            test_constants.OPTION_FROM,
            source,
            constants.APPLICATION_NAME,
        ]
        python = [
            Path(sys.executable).parent / test_constants.VALUE_UVX,
            test_constants.OPTION_FROM,
            source,
            constants.KEY_PYTHON,
        ]
    elif installer == constants.COMMAND_PIP:
        venv = tmp_path / test_constants.PATH_VENV
        run([sys.executable, constants.SHORT_OPTION_M, "venv", venv])
        run(
            [
                venv / constants.BIN_DIRECTORY / constants.KEY_PYTHON,
                constants.SHORT_OPTION_M,
                constants.COMMAND_PIP,
                constants.COMMAND_INSTALL,
                source,
            ]
        )
        command = [venv / constants.BIN_DIRECTORY / constants.APPLICATION_NAME]
        python = [venv / constants.BIN_DIRECTORY / constants.KEY_PYTHON]
    else:
        installed_python = install_pipx_package(run, source, tmp_path)
        command = [tmp_path / constants.BIN_DIRECTORY / constants.APPLICATION_NAME]
        python = [installed_python]
    assert __version__ in run([*command, test_constants.OPTION_VERSION])
    config = json.loads(
        run([*command, constants.COMMAND_DOCTOR, constants.OPTION_BACKEND, constants.BACKEND_ROCM])
    )
    assert config[constants.KEY_SETTINGS][constants.KEY_BACKEND] == constants.BACKEND_ROCM
    assert constants.KEY_STATS in run([*command, test_constants.OPTION_HELP])
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
    assert run([*python, test_constants.SHORT_OPTION_C, probe]).startswith(__version__ + "-")


def test_editable_install_and_metadata_only_runtime(artifacts, tmp_path):
    """Resources work without generated source copies or the original checkout at runtime."""
    with tarfile.open(artifacts[test_constants.KEY_SDIST]) as archive:
        archive.extractall(tmp_path / constants.KEY_SOURCE, filter="data")
    source = next((tmp_path / constants.KEY_SOURCE).iterdir())
    venv = tmp_path / test_constants.PATH_VENV
    python = venv / constants.PATH_BIN_PYTHON
    uv = uv_executable()
    subprocess.run([uv, "venv", venv, constants.OPTION_PYTHON, sys.executable], check=True)
    subprocess.run(
        [
            uv,
            constants.COMMAND_PIP,
            constants.COMMAND_INSTALL,
            constants.OPTION_PYTHON,
            python,
            test_constants.OPTION_EDITABLE,
            source,
        ],
        check=True,
    )
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
        [python, test_constants.SHORT_OPTION_C, probe, tmp_path / test_constants.KEY_STATE],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    runtime = Path(json.loads(result.stdout))
    for name in (constants.PATH_PYPROJECT_TOML, constants.PATH_UV_LOCK):
        assert (runtime / name).read_bytes() == (source / name).read_bytes()
    assert not (source / test_constants.PATH_SRC_CODE_SEARCH_LOCAL_RUNTIME).exists()
    assert not (source / test_constants.PATH_SRC_CODE_SEARCH_LOCAL_ASSETS).exists()
    source.rename(tmp_path / test_constants.PATH_REMOVED_CHECKOUT)
    subprocess.run(
        [
            uv,
            constants.COMMAND_SYNC,
            constants.OPTION_PROJECT,
            runtime,
            constants.OPTION_LOCKED,
            constants.OPTION_NO_DEV,
            constants.OPTION_NO_INSTALL_PROJECT,
            constants.OPTION_EXTRA,
            constants.SERVER_EXTRA,
            constants.OPTION_EXTRA,
            constants.BACKEND_CPU,
            test_constants.OPTION_DRY_RUN,
        ],
        cwd=tmp_path,
        check=True,
    )


def test_hatch_source_workflow_uses_backend_environment(tmp_path):
    if os.environ.get(test_constants.ENV_CODE_SEARCH_PACKAGING) != constants.ENV_ENABLED:
        pytest.skip("Set CODE_SEARCH_PACKAGING=1 for source workflow acceptance")
    source = copy_source_checkout(tmp_path / test_constants.PATH_SOURCE_WITH_SPACES)
    settings = Settings(
        storage=str(tmp_path / test_constants.KEY_STATE), port=free_port(), watch=False
    )
    env = {
        **os.environ,
        test_constants.ENV_HATCH_DATA_DIR: str(tmp_path / test_constants.PATH_HATCH_DATA),
        test_constants.ENV_HATCH_CACHE_DIR: str(tmp_path / test_constants.PATH_HATCH_CACHE),
        test_constants.ENV_HATCH_ENV: constants.KEY_DEFAULT,
        constants.ENV_CODE_SEARCH_STORAGE: settings.storage,
    }
    for name in (
        constants.ENV_VIRTUAL_ENV,
        constants.ENV_PYTHONPATH,
        constants.ENV_UV_PROJECT_ENVIRONMENT,
        test_constants.ENV_HATCH_ENV_TYPE_VIRTUAL_PATH,
        test_constants.ENV_CODE_SEARCH_PORT,
        test_constants.ENV_CODE_SEARCH_DEV_BACKEND,
    ):
        env.pop(name, None)
    hatch = [sys.executable, constants.SHORT_OPTION_M, constants.KEY_HATCH]

    def run(*args):
        result = subprocess.run(
            [*hatch, *args],
            cwd=source,
            env=env,
            text=True,
            capture_output=True,
            timeout=test_constants.COMMAND_TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        return result.stdout.strip()

    # No build is needed to execute the live checkout.
    assert __version__ in run("run", "cpu:cli", test_constants.OPTION_VERSION)
    assert not (source / test_constants.PATH_DIST).exists()
    expected = source / test_constants.PATH_VENVS_CPU
    assert Path(run(constants.KEY_ENV, "find", constants.BACKEND_CPU)) == expected
    assert (
        Path(run(constants.KEY_ENV, "find", constants.BACKEND_CUDA))
        == source / test_constants.PATH_VENVS_CUDA
    )
    assert (
        Path(run(constants.KEY_ENV, "find", constants.BACKEND_ROCM))
        == source / test_constants.PATH_VENVS_ROCM
    )
    assert constants.OPTION_SOURCE in run("run", "setup", test_constants.OPTION_HELP)
    # Building a release can reuse the CPU tooling environment afterwards.
    run("build")
    assert Path(run(constants.KEY_ENV, "find")) == expected
    assert Path(run(constants.KEY_ENV, "find", "hatch-build")) == expected
    run("run", "cpu:sync")
    assert __version__ in run("run", constants.INSTALL_ORIGIN_CLI, test_constants.OPTION_VERSION)
    location = run(
        "run",
        constants.KEY_PYTHON,
        test_constants.SHORT_OPTION_C,
        "import code_search_local; print(code_search_local.__file__)",
    )
    assert Path(location) == source / constants.PATH_SRC_CODE_SEARCH_LOCAL_INIT_PY
    cli = source / test_constants.PATH_SRC_CODE_SEARCH_LOCAL_CLI_PY
    cli.write_text(cli.read_text().replace("Local semantic search", "Editable source sentinel"))
    assert "Editable source sentinel" in run(
        "run", constants.INSTALL_ORIGIN_CLI, test_constants.OPTION_HELP
    )
    for command in (
        [
            expected / constants.PATH_BIN_PYTHON,
            constants.SHORT_OPTION_M,
            constants.PACKAGE_NAME,
            test_constants.OPTION_HELP,
        ],
        [expected / test_constants.PATH_BIN_CODE_SEARCH_LOCAL, test_constants.OPTION_HELP],
    ):
        result = subprocess.run(
            command,
            cwd=source,
            env=env,
            text=True,
            capture_output=True,
            timeout=test_constants.COMMAND_PROBE_TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        assert "Editable source sentinel" in result.stdout
    run("run", "lint")
    run("run", "test", "tests/unit/test_config_cli.py", test_constants.SHORT_OPTION_Q)
    assert [path.parent for path in tmp_path.rglob(test_constants.PATH_PYVENV_CFG_LOWERCASE)] == [
        expected
    ]

    env[test_constants.ENV_CODE_SEARCH_PORT] = str(settings.port)
    with (tmp_path / test_constants.PATH_SOURCE_SERVER_LOG).open(test_constants.FILE_MODE_W) as log:
        process = subprocess.Popen(
            [
                *hatch,
                "run",
                constants.COMMAND_SERVE,
                constants.OPTION_BACKEND,
                constants.BACKEND_CPU,
                test_constants.OPTION_OFFLINE,
                test_constants.OPTION_NO_WATCH,
            ],
            cwd=source,
            env=env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            wait_healthy(process, Client(settings), log)
            snapshot = json.loads(
                run("run", constants.INSTALL_ORIGIN_CLI, constants.KEY_STATS, constants.OPTION_JSON)
            )
            assert snapshot[constants.KEY_ONLINE] is True
            assert snapshot[constants.KEY_PROJECTS] == {}
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=test_constants.SLOW_PROCESS_SHUTDOWN_TIMEOUT_SECONDS)
