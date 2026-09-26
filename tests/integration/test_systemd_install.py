"""Opted-in Linux acceptance test; installs and removes one uniquely named user unit."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from code_search_local import __version__, constants
from code_search_local.client import Client
from code_search_local.config import Settings
from code_search_local.install import uv_executable
from tests import constants as test_constants
from tests.helpers import SYSTEMD_DRIVER as DRIVER
from tests.helpers import (
    free_port,
    index_and_check_backend,
    install_pipx_package,
    remove_test_service,
    search_project,
    systemd_property,
)

pytestmark = pytest.mark.packaging
ROOT = Path(__file__).resolve().parents[2]


def test_managed_backends_and_both_client_registrations(tmp_path):
    if os.environ.get(test_constants.ENV_CODE_SEARCH_SYSTEMD_TESTS) != constants.ENV_ENABLED:
        pytest.skip(
            "Set CODE_SEARCH_SYSTEMD_TESTS=1 to exercise real user systemd and installed runtimes"
        )
    wheel = ROOT / test_constants.PATH_DIST / f"code_search_local-{__version__}-py3-none-any.whl"
    assert wheel.is_file(), "Build the current release wheel before running acceptance"
    service = "code-search-local-test-" + uuid.uuid4().hex[:12] + constants.PATH_SERVICE
    outside = tmp_path / test_constants.PATH_OUTSIDE
    outside.mkdir()
    storage = tmp_path / test_constants.KEY_STATE
    config = tmp_path / test_constants.PATH_CONFIG
    env = {
        **os.environ,
        constants.ENV_CODE_SEARCH_STORAGE: str(storage),
        constants.ENV_XDG_CONFIG_HOME: str(config),
        constants.ENV_CODEX_HOME: str(tmp_path / constants.HARNESS_CODEX),
        constants.ENV_CLAUDE_CONFIG_DIR: str(tmp_path / constants.HARNESS_CLAUDE),
        test_constants.ENV_PIPX_HOME: str(tmp_path / test_constants.PATH_PIPX),
        test_constants.ENV_PIPX_BIN_DIR: str(tmp_path / constants.BIN_DIRECTORY),
        test_constants.ENV_PIPX_MAN_DIR: str(tmp_path / test_constants.PATH_MAN),
        test_constants.ENV_UV_CACHE_DIR: str(tmp_path / test_constants.PATH_DISPOSABLE_CACHE),
    }
    # The package wheel and model cache are local; downloads were independently validated in the cold-cache lane.
    source_cache = ROOT / test_constants.PATH_TEST_ARTIFACTS_REAL_MODEL_MODELS
    if source_cache.exists():
        shutil.copytree(source_cache, storage / constants.MODEL_CACHE_DIRECTORY, symlinks=True)
        for pointer in (storage / constants.MODEL_CACHE_DIRECTORY).glob(test_constants.PATH_JSON):
            data = json.loads(pointer.read_text())
            old = Path(data[constants.KEY_SNAPSHOT]).resolve()
            data[constants.KEY_SNAPSHOT] = str(
                storage / constants.MODEL_CACHE_DIRECTORY / old.relative_to(source_cache)
            )
            pointer.write_text(json.dumps(data))
    env.pop(constants.ENV_PYTHONPATH, None)
    env.pop(constants.ENV_VIRTUAL_ENV, None)
    seed = os.environ.get(test_constants.ENV_CODE_SEARCH_TEST_UV_CACHE)
    if seed:
        shutil.copytree(
            seed,
            tmp_path / test_constants.PATH_DISPOSABLE_CACHE,
            symlinks=True,
            copy_function=os.link,
        )
    (tmp_path / constants.HARNESS_CODEX).mkdir()
    (tmp_path / test_constants.PATH_CODEX_CONFIG_TOML).write_text(
        '# keep this comment\nmodel = "custom"\n'
    )
    (tmp_path / constants.HARNESS_CLAUDE).mkdir()
    (tmp_path / test_constants.PATH_CLAUDE_CLAUDE_JSON).write_text('{"unrelatedSetting": "keep"}')

    def run(args, timeout=test_constants.SYSTEMD_SETUP_TIMEOUT_SECONDS):
        result = subprocess.run(
            [str(a) for a in args],
            cwd=outside,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        (tmp_path / test_constants.PATH_COMMANDS_LOG).open(test_constants.FILE_MODE_A).write(
            json.dumps([str(a) for a in args]) + "\n" + result.stdout + "\n" + result.stderr + "\n"
        )
        assert result.returncode == 0, result.stdout[-4000:] + "\n" + result.stderr[-4000:]
        return result.stdout

    try:
        installed_python = install_pipx_package(run, wheel, tmp_path)
        pipx_python = installed_python
        pip_venv = tmp_path / test_constants.PATH_PIP_VENV
        run([sys.executable, constants.SHORT_OPTION_M, "venv", pip_venv])
        pip_python = pip_venv / constants.PATH_BIN_PYTHON
        run(
            [
                pip_python,
                constants.SHORT_OPTION_M,
                constants.COMMAND_PIP,
                constants.COMMAND_INSTALL,
                wheel,
            ]
        )
        uvx_python = [
            uv_executable(),
            constants.KEY_TOOL,
            "run",
            test_constants.OPTION_FROM,
            wheel,
            constants.KEY_PYTHON,
        ]
        port = free_port()
        common = [
            "setup",
            constants.OPTION_STORAGE,
            storage,
            constants.OPTION_PORT,
            str(port),
            constants.OPTION_PACKAGE_SOURCE,
            wheel,
            constants.OPTION_AGENT_HARNESS,
            constants.HARNESS_CLAUDE,
            constants.OPTION_AGENT_HARNESS,
            constants.HARNESS_CODEX,
            test_constants.OPTION_NO_CPU_FALLBACK,
        ]
        client = Client(Settings(storage=str(storage), port=port))
        project = tmp_path / test_constants.PATH_FIXTURE
        project.mkdir()
        (project / test_constants.PATH_FIXTURE_PY).write_text(
            'def persistent_symbol(): return "persistent"\n'
        )
        for backend, origin in (
            (constants.BACKEND_CPU, [pipx_python]),
            (constants.BACKEND_CUDA, [pip_python]),
            (constants.BACKEND_ROCM, uvx_python),
        ):
            run(
                [
                    *origin,
                    test_constants.SHORT_OPTION_C,
                    DRIVER,
                    service,
                    *common,
                    constants.OPTION_BACKEND,
                    backend,
                ]
            )
            index_and_check_backend(client, project, backend)
            assert (
                run(
                    [constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, "is-active", service]
                ).strip()
                == test_constants.VALUE_ACTIVE
            )
            unit = run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, "cat", service])
            assert str(storage / constants.RUNTIMES_DIRECTORY) in unit
            assert str(tmp_path / test_constants.PATH_DISPOSABLE_CACHE) not in unit
            # Both registered clients resolve to exactly this shared endpoint.
            import tomlkit

            codex = tomlkit.parse(
                (tmp_path / constants.HARNESS_CODEX / constants.PATH_CONFIG_TOML).read_text()
            )
            assert (
                codex[constants.KEY_MCP_SERVERS_LOWERCASE][constants.APPLICATION_NAME][
                    constants.KEY_URL
                ]
                == f"http://127.0.0.1:{port}/mcp"
            )
            assert codex[constants.KEY_MODEL] == test_constants.VALUE_CUSTOM
            assert (
                (tmp_path / test_constants.PATH_CODEX_CONFIG_TOML)
                .read_text()
                .startswith("# keep this comment")
            )
            claude = json.loads((tmp_path / test_constants.PATH_CLAUDE_CLAUDE_JSON).read_text())
            assert claude[test_constants.KEY_UNRELATED_SETTING] == test_constants.KEY_KEEP
            assert (
                claude[constants.KEY_MCP_SERVERS][constants.APPLICATION_NAME][constants.KEY_URL]
                == f"http://127.0.0.1:{port}/mcp"
            )
        before = systemd_property(run, service, test_constants.SYSTEMD_EXEC_START, value_only=False)
        run(
            [
                pipx_python,
                test_constants.SHORT_OPTION_C,
                DRIVER,
                service,
                *common,
                constants.OPTION_BACKEND,
                constants.BACKEND_ROCM,
            ]
        )
        assert (
            systemd_property(run, service, test_constants.SYSTEMD_EXEC_START, value_only=False)
            == before
        )
        # Build a genuine next-version wheel and exercise the immutable runtime upgrade path.
        source = tmp_path / test_constants.PATH_UPGRADE_SOURCE
        source.mkdir()
        for name in (
            constants.PATH_PYPROJECT_TOML,
            constants.PATH_UV_LOCK,
            constants.PATH_README_MD,
            "LICENSE",
        ):
            shutil.copy2(ROOT / name, source / name)
        for name in ("src", "scripts", constants.KEY_PLUGINS, ".claude-plugin"):
            shutil.copytree(
                ROOT / name,
                source / name,
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.egg-info", constants.KEY_RUNTIME, "assets"
                ),
            )
        next_version = (
            __version__.rsplit(constants.KEY_PROJECT_ROOT, 1)[0]
            + constants.KEY_PROJECT_ROOT
            + str(int(__version__.split(constants.KEY_PROJECT_ROOT)[-1]) + 1)
        )
        version = source / constants.PATH_SRC_CODE_SEARCH_LOCAL_INIT_PY
        version.write_text(version.read_text().replace(__version__, next_version))
        run([uv_executable(), "lock", constants.OPTION_PROJECT, source])
        run(
            [
                sys.executable,
                constants.SHORT_OPTION_M,
                "build",
                test_constants.OPTION_WHEEL,
                test_constants.OPTION_OUTDIR,
                tmp_path / test_constants.PATH_UPGRADE_DIST,
                source,
            ]
        )
        upgrade = next((tmp_path / test_constants.PATH_UPGRADE_DIST).glob(test_constants.PATH_WHL))
        run(
            [
                pip_python,
                constants.SHORT_OPTION_M,
                constants.COMMAND_PIP,
                constants.COMMAND_INSTALL,
                test_constants.OPTION_UPGRADE,
                upgrade,
            ]
        )
        upgraded = [upgrade if str(arg) == str(wheel) else arg for arg in common]
        run(
            [
                pip_python,
                test_constants.SHORT_OPTION_C,
                DRIVER,
                service,
                *upgraded,
                constants.OPTION_BACKEND,
                constants.BACKEND_ROCM,
            ]
        )
        assert f"{next_version}-rocm" in run(
            [constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, "cat", service]
        )
        hits = search_project(client, str(project), "persistent_symbol")
        assert (
            hits[constants.KEY_RESULTS][0][constants.KEY_NAME]
            == test_constants.VALUE_PERSISTENT_SYMBOL
        )
        shutil.rmtree(tmp_path / test_constants.PATH_DISPOSABLE_CACHE)
        run(
            [constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_RESTART, service]
        )
        assert (
            run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, "is-active", service]).strip()
            == test_constants.VALUE_ACTIVE
        )
        deadline = time.monotonic() + test_constants.SERVICE_RESTART_TIMEOUT_SECONDS
        while True:
            try:
                asyncio.run(client.request(constants.HTTP_GET, constants.HEALTH_ENDPOINT))
                break
            except OSError:
                assert time.monotonic() < deadline, "Service did not restart after cache deletion"
                time.sleep(test_constants.SERVICE_POLL_SECONDS)
        hits = search_project(client, str(project), "persistent_symbol")
        assert (
            hits[constants.KEY_RESULTS][0][constants.KEY_NAME]
            == test_constants.VALUE_PERSISTENT_SYMBOL
        )
        run(
            [
                pip_python,
                test_constants.SHORT_OPTION_C,
                DRIVER,
                service,
                constants.KEY_SERVICE,
                constants.COMMAND_UNINSTALL,
            ]
        )
        assert storage.exists() and (storage / constants.MODEL_CACHE_DIRECTORY).exists()
    finally:
        remove_test_service(service)
