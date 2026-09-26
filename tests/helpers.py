"""Shared process helpers for integration tests; no imports from collected test modules."""

import asyncio
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from code_search_local import constants
from tests import constants as test_constants

SYSTEMD_DRIVER = """
from pathlib import Path
import sys
from code_search_local import install
from code_search_local.cli import main
install.SERVICE = sys.argv[1]
install.unit_path = lambda: Path.home() / ".config/systemd/user" / install.SERVICE
main(args=sys.argv[2:], standalone_mode=False)
"""


def copy_source_checkout(destination):
    """Copy live source inputs directly, without building or extracting an artifact."""
    root = Path(__file__).resolve().parents[1]
    destination.mkdir(parents=True)
    for name in (
        "src",
        "scripts",
        "tests",
        constants.KEY_PLUGINS,
        "docs",
        ".claude-plugin",
        constants.PATH_PYPROJECT_TOML,
        constants.PATH_UV_LOCK,
        constants.PATH_README_MD,
        "CLAUDE.md",
        "LICENSE",
        constants.PATH_GITIGNORE,
    ):
        source = root / name
        if source.is_dir():
            shutil.copytree(
                source,
                destination / name,
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.egg-info", constants.KEY_RUNTIME, "assets"
                ),
            )
        else:
            shutil.copy2(source, destination / name)
    return destination


def free_port():
    with socket.socket() as sock:
        sock.bind((constants.LOOPBACK_IPV4, 0))
        return sock.getsockname()[1]


def wait_healthy(process, client, log, timeout=test_constants.PROCESS_STARTUP_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            asyncio.run(client.request(constants.HTTP_GET, constants.HEALTH_ENDPOINT))
            return
        except (OSError, RuntimeError):
            if process.poll() is not None:
                log.flush()
                pytest.fail("Daemon failed: " + Path(log.name).read_text()[-5000:])
            time.sleep(test_constants.HEALTH_POLL_SECONDS)
    pytest.fail("Daemon startup timed out")


def start_test_daemon(settings, log, *extra_arguments):
    """Launch the isolated fake daemon with identical argument and log handling."""
    return subprocess.Popen(
        [
            sys.executable,
            constants.SHORT_OPTION_M,
            "tests.daemon",
            test_constants.OPTION_FAKE,
            constants.OPTION_STORAGE,
            settings.storage,
            constants.OPTION_PORT,
            str(settings.port),
            *extra_arguments,
        ],
        stdout=log,
        stderr=log,
    )


def stop_process(process, timeout=test_constants.PROCESS_SHUTDOWN_TIMEOUT_SECONDS):
    """Reap a test child if it has not already exited."""
    if process.poll() is None:
        process.terminate()
        process.wait(timeout)


def remove_test_service(service):
    """Remove only the explicitly named acceptance-test service."""
    subprocess.run(
        [
            constants.COMMAND_SYSTEMCTL,
            constants.OPTION_USER,
            constants.COMMAND_DISABLE,
            constants.OPTION_NOW,
            service,
        ],
        capture_output=True,
    )
    (Path.home() / test_constants.PATH_CONFIG_SYSTEMD_USER / service).unlink(missing_ok=True)
    subprocess.run(
        [constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_DAEMON_RELOAD],
        capture_output=True,
    )


def index_and_check_backend(client, project, backend):
    job = asyncio.run(
        client.request(
            constants.HTTP_POST,
            constants.INDEX_ENDPOINT,
            data={constants.KEY_DIRECTORY_PATH: str(project), constants.KEY_WAIT: True},
        )
    )
    assert job[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED
    stats = asyncio.run(client.stats())
    assert (
        stats[constants.KEY_PROJECTS][str(project)][constants.KEY_MODEL][constants.KEY_BACKEND]
        == backend
    )
    return stats


def systemd_property(run, service, name, *, value_only=False):
    command = [
        constants.COMMAND_SYSTEMCTL,
        constants.OPTION_USER,
        constants.COMMAND_SHOW,
        service,
        test_constants.SYSTEMD_PROPERTY_OPTION.format(name=name),
    ]
    if value_only:
        command.append(test_constants.OPTION_VALUE)
    return run(command).strip()


def install_pipx_package(run, source, root):
    run(
        [
            sys.executable,
            test_constants.SHORT_OPTION_M,
            test_constants.VALUE_PIPX,
            constants.COMMAND_INSTALL,
            constants.OPTION_PYTHON,
            sys.executable,
            source,
        ]
    )
    return (
        root
        / test_constants.VALUE_PIPX
        / test_constants.PATH_VENVS_LOWERCASE
        / constants.APPLICATION_NAME
        / constants.BIN_DIRECTORY
        / constants.KEY_PYTHON
    )


def search_project(client, project, query):
    return asyncio.run(
        client.request(
            constants.HTTP_POST,
            constants.SEARCH_ENDPOINT,
            data={constants.KEY_PROJECT_PATH: str(project), constants.KEY_QUERY: query},
        )
    )


def run_service_cli(run, python, service, *arguments):
    return run([python, test_constants.SHORT_OPTION_C, SYSTEMD_DRIVER, service, *arguments])


def model_blob_fingerprints(root):
    return {
        str(path): (path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns)
        for path in (root / constants.MODEL_CACHE_DIRECTORY).glob(constants.PATH_MODELS_BLOBS)
        if path.is_file()
    }


def chunk_sample(tmp_path, source):
    from code_search_local.chunking.multi_language_chunker import MultiLanguageChunker

    path = tmp_path / test_constants.PATH_SAMPLE_PY
    path.write_text(source)
    return MultiLanguageChunker(str(tmp_path)).chunk_file(str(path))
