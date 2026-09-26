"""Run a real user service directly from a raw checkout with all backend venvs present."""

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from code_search_local import constants
from code_search_local.client import Client
from code_search_local.config import Settings
from tests import constants as test_constants
from tests.helpers import (
    copy_source_checkout,
    free_port,
    index_and_check_backend,
    remove_test_service,
    run_service_cli,
    search_project,
    systemd_property,
)

pytestmark = pytest.mark.packaging
ROOT = Path(__file__).resolve().parents[2]


def test_source_service_keeps_backends_and_picks_up_edits(tmp_path):
    if os.environ.get(test_constants.ENV_CODE_SEARCH_SYSTEMD_TESTS) != constants.ENV_ENABLED:
        pytest.skip("Set CODE_SEARCH_SYSTEMD_TESTS=1 for source-service acceptance")
    source = copy_source_checkout(tmp_path / test_constants.PATH_LIVE_CHECKOUT_WITH_SPACES)
    service = "code-search-local-source-test-" + uuid.uuid4().hex[:12] + constants.PATH_SERVICE
    storage = tmp_path / test_constants.KEY_STATE
    storage.mkdir()
    cache = Path(
        os.environ.get(
            test_constants.ENV_CODE_SEARCH_MODEL_STORAGE,
            ROOT / test_constants.PATH_TEST_ARTIFACTS_REAL_MODEL,
        )
    )
    if (cache / constants.MODEL_CACHE_DIRECTORY).exists():
        (storage / constants.MODEL_CACHE_DIRECTORY).symlink_to(
            (cache / constants.MODEL_CACHE_DIRECTORY).resolve(), target_is_directory=True
        )
    env = {
        **os.environ,
        constants.ENV_CODE_SEARCH_STORAGE: str(storage),
        constants.ENV_XDG_CONFIG_HOME: str(tmp_path / test_constants.PATH_CONFIG),
        constants.ENV_CODEX_HOME: str(tmp_path / constants.HARNESS_CODEX),
        constants.ENV_CLAUDE_CONFIG_DIR: str(tmp_path / constants.HARNESS_CLAUDE),
    }
    for name in (
        constants.ENV_VIRTUAL_ENV,
        constants.ENV_PYTHONPATH,
        constants.ENV_UV_PROJECT_ENVIRONMENT,
    ):
        env.pop(name, None)
    settings = Settings(storage=str(storage), port=free_port())
    client = Client(settings)

    def run(args):
        result = subprocess.run(
            [str(arg) for arg in args],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=test_constants.SYSTEMD_SETUP_TIMEOUT_SECONDS,
        )
        with (tmp_path / test_constants.PATH_COMMANDS_LOG).open(test_constants.FILE_MODE_A) as log:
            log.write(result.stdout + "\n" + result.stderr + "\n")
        assert result.returncode == 0, result.stdout[-4000:] + "\n" + result.stderr[-4000:]
        return result.stdout

    def health():
        deadline = time.monotonic() + test_constants.SERVICE_RESTART_TIMEOUT_SECONDS
        while True:
            try:
                return asyncio.run(client.request(constants.HTTP_GET, constants.HEALTH_ENDPOINT))
            except OSError:
                assert time.monotonic() < deadline, "Source service did not restart"
                time.sleep(test_constants.SERVICE_POLL_SECONDS)

    project = tmp_path / test_constants.PATH_FIXTURE
    project.mkdir()
    (project / test_constants.PATH_FIXTURE_PY).write_text(
        'def source_symbol(): return "source service"\n'
    )
    try:
        for backend in (constants.BACKEND_CPU, constants.BACKEND_CUDA, constants.BACKEND_ROCM):
            output = run_service_cli(
                run,
                sys.executable,
                service,
                "setup",
                constants.OPTION_SOURCE,
                source,
                constants.OPTION_AGENT_HARNESS,
                constants.HARNESS_CLAUDE,
                constants.OPTION_AGENT_HARNESS,
                constants.HARNESS_CODEX,
                constants.OPTION_BACKEND,
                backend,
                test_constants.OPTION_NO_CPU_FALLBACK,
                constants.OPTION_STORAGE,
                storage,
                constants.OPTION_PORT,
                settings.port,
            )
            assert '"mode": "source"' in output
            python = (
                source / test_constants.PATH_VENVS_LOWERCASE / backend / constants.PATH_BIN_PYTHON
            )
            unit = run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, "cat", service])
            assert f'ExecStart="{python}" "-m" "code_search_local" "serve"' in unit
            assert f"WorkingDirectory={source}/" in unit
            pid = systemd_property(
                run, service, test_constants.SYSTEMD_MAIN_PID, value_only=True
            ).strip()
            assert Path(f"/proc/{pid}/cwd").resolve() == source
            assert Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[0] == str(python).encode()
            index_and_check_backend(client, project, backend)
            assert not (storage / constants.RUNTIMES_DIRECTORY).exists()
            assert not (source / test_constants.PATH_DIST).exists()

        # All builds remain usable simultaneously after source setup selects ROCm.
        for backend, suffix in (
            (constants.BACKEND_CPU, "+cpu"),
            (constants.BACKEND_CUDA, "+cu130"),
            (constants.BACKEND_ROCM, "+rocm7.14"),
        ):
            python = (
                source / test_constants.PATH_VENVS_LOWERCASE / backend / constants.PATH_BIN_PYTHON
            )
            info = json.loads(
                run(
                    [
                        python,
                        test_constants.SHORT_OPTION_C,
                        "import json, torch, code_search_local; "
                        "print(json.dumps([torch.__version__, code_search_local.__file__]))",
                    ]
                )
            )
            assert info[0].endswith(suffix)
            assert Path(info[1]) == source / constants.PATH_SRC_CODE_SEARCH_LOCAL_INIT_PY

        # Edit application source, restart the same unit, and observe the change over HTTP.
        service_source = source / test_constants.PATH_SRC_CODE_SEARCH_LOCAL_SERVICE_PY
        before = service_source.read_text()
        after = before.replace(
            "constants.KEY_STATUS: constants.STATUS_OK,",
            "constants.KEY_STATUS: constants.STATUS_OK, 'source_revision': 'edited',",
        )
        assert after != before
        service_source.write_text(after)
        python = source / test_constants.PATH_VENVS_ROCM_BIN_PYTHON
        run_service_cli(run, python, service, constants.KEY_SERVICE, constants.COMMAND_RESTART)
        assert health()[test_constants.KEY_SOURCE_REVISION] == test_constants.VALUE_EDITED
        hits = search_project(client, str(project), "source_symbol")
        assert (
            hits[constants.KEY_RESULTS][0][constants.KEY_NAME] == test_constants.VALUE_SOURCE_SYMBOL
        )
        assert not (source / test_constants.PATH_DIST).exists()
        assert sorted(
            path.parent.name
            for path in (source / test_constants.PATH_VENVS_LOWERCASE).glob(
                test_constants.PATH_PYVENV_CFG
            )
        ) == [
            constants.BACKEND_CPU,
            constants.BACKEND_CUDA,
            constants.BACKEND_ROCM,
        ]
        # Reconfigure the existing ROCm service and add the previously unselected OpenCode.
        before_pid = systemd_property(
            run, service, test_constants.SYSTEMD_MAIN_PID, value_only=True
        ).strip()
        run_service_cli(
            run,
            python,
            service,
            "setup",
            constants.OPTION_SOURCE,
            source,
            constants.OPTION_BACKEND,
            constants.BACKEND_ROCM,
            test_constants.OPTION_CPU_FALLBACK,
            constants.OPTION_AGENT_HARNESS,
            constants.HARNESS_ALL,
            constants.OPTION_STORAGE,
            storage,
            constants.OPTION_PORT,
            settings.port,
        )
        assert (
            systemd_property(run, service, test_constants.SYSTEMD_MAIN_PID, value_only=True).strip()
            != before_pid
        )
        from code_search_local.harnesses import read_document

        for path, key in (
            (tmp_path / test_constants.PATH_CODEX_CONFIG_TOML, constants.KEY_MCP_SERVERS_LOWERCASE),
            (tmp_path / test_constants.PATH_CLAUDE_CLAUDE_JSON, constants.KEY_MCP_SERVERS),
            (tmp_path / test_constants.PATH_CONFIG_OPENCODE_OPENCODE_JSON, constants.KEY_MCP),
        ):
            assert (
                read_document(path)[key][constants.APPLICATION_NAME][constants.KEY_URL]
                == settings.url + constants.MCP_ENDPOINT
            )
        assert (
            json.loads(
                (tmp_path / test_constants.PATH_CONFIG_CODE_SEARCH_LOCAL_CONFIG_JSON).read_text()
            )[constants.KEY_CPU_FALLBACK]
            is True
        )
        assert health()[test_constants.KEY_SOURCE_REVISION] == test_constants.VALUE_EDITED
        run_service_cli(run, python, service, constants.COMMAND_UNINSTALL)
        assert not (Path.home() / test_constants.PATH_CONFIG_SYSTEMD_USER / service).exists()

        assert constants.APPLICATION_NAME not in read_document(
            tmp_path / test_constants.PATH_CODEX_CONFIG_TOML
        ).get(constants.KEY_MCP_SERVERS_LOWERCASE, {})
        assert constants.APPLICATION_NAME not in read_document(
            tmp_path / test_constants.PATH_CLAUDE_CLAUDE_JSON
        ).get(constants.KEY_MCP_SERVERS, {})
        assert constants.APPLICATION_NAME not in read_document(
            tmp_path / test_constants.PATH_CONFIG_OPENCODE_OPENCODE_JSON
        ).get(constants.KEY_MCP, {})
        assert (storage / constants.PATH_STATE_SQLITE3).exists()
        assert python.exists(), "Uninstall must preserve the source environment"
    finally:
        remove_test_service(service)
