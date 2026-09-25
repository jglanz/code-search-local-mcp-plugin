"""Shared process helpers for integration tests; no imports from collected test modules."""

import asyncio
import shutil
import socket
import time
from pathlib import Path

import pytest

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
        "plugins",
        "docs",
        ".claude-plugin",
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "CLAUDE.md",
        "LICENSE",
        ".gitignore",
    ):
        source = root / name
        if source.is_dir():
            shutil.copytree(
                source,
                destination / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", "runtime", "assets"),
            )
        else:
            shutil.copy2(source, destination / name)
    return destination


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_healthy(process, client, log, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            asyncio.run(client.request("GET", "/api/v1/health"))
            return
        except (OSError, RuntimeError):
            if process.poll() is not None:
                log.flush()
                pytest.fail("Daemon failed: " + Path(log.name).read_text()[-5000:])
            time.sleep(0.05)
    pytest.fail("Daemon startup timed out")
