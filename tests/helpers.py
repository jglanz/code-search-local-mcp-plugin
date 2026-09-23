"""Shared process helpers for integration tests; no imports from collected test modules."""

import asyncio
import socket
import time
from pathlib import Path

import pytest


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
