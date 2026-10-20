import asyncio
from pathlib import Path

import pytest

from code_search_local import constants
from code_search_local.events import Publisher, Subscriber, ipc_address
from tests import constants as test_constants


async def test_events_detect_gaps_disconnect_and_restart(tmp_path):
    address = ipc_address(tmp_path / test_constants.KEY_STATE)
    current = {
        constants.KEY_DAEMON_ID: "one",
        constants.KEY_SEQUENCE: 0,
        constants.KEY_ONLINE: True,
        constants.KEY_PROJECTS: {},
        constants.KEY_SHARED: {},
        constants.KEY_JOBS: {},
    }
    calls = []

    async def fetch():
        calls.append(1)
        return dict(current)

    publisher = Publisher(address, lambda: current)
    stream = Subscriber(address, fetch).snapshots()
    try:
        assert (await anext(stream))[constants.KEY_SEQUENCE] == 0
        current[constants.KEY_SEQUENCE] = 100
        # Even if an event is dropped during socket setup, the heartbeat resynchronizes.
        publisher.publish(
            {
                constants.KEY_TYPE: "changed",
                constants.KEY_DAEMON_ID: "one",
                constants.KEY_SEQUENCE: 100,
            }
        )
        assert (await asyncio.wait_for(anext(stream), test_constants.PUBSUB_WAIT_TIMEOUT_SECONDS))[
            constants.KEY_SEQUENCE
        ] == 100
        assert len(calls) == 2
        publisher.close()
        disconnected = await asyncio.wait_for(
            anext(stream), test_constants.PUBSUB_WAIT_TIMEOUT_SECONDS
        )
        assert not disconnected[constants.KEY_ONLINE]
        current.update(daemon_id="two", sequence=0)
        publisher = Publisher(address, lambda: current)
        reconnected = await asyncio.wait_for(
            anext(stream), test_constants.PUBSUB_WAIT_TIMEOUT_SECONDS
        )
        assert (
            reconnected[constants.KEY_DAEMON_ID] == test_constants.VALUE_TWO
            and reconnected[constants.KEY_ONLINE]
        )
    finally:
        await stream.aclose()
        publisher.close()
    assert not Path(address.removeprefix(constants.IPC_SCHEME)).exists()


def test_private_short_socket_paths_and_symlink_rejection(tmp_path, monkeypatch):
    long = tmp_path / ("a" * 80)
    monkeypatch.setenv(constants.ENV_XDG_RUNTIME_DIR, str(long))
    assert len(ipc_address(tmp_path).removeprefix(constants.IPC_SCHEME).encode()) <= 100
    short = tmp_path / constants.FILE_MODE_READ
    short.mkdir()
    (short / constants.APPLICATION_NAME).symlink_to(
        tmp_path / constants.KEY_TARGET, target_is_directory=True
    )
    (tmp_path / constants.KEY_TARGET).mkdir()
    monkeypatch.setenv(constants.ENV_XDG_RUNTIME_DIR, str(short))
    # A genuinely short runtime root is necessary to exercise the symlink check.
    if (
        len(str(short / constants.APPLICATION_NAME / test_constants.PATH_0123456789ABCDEF_SOCK))
        <= 100
    ):
        with pytest.raises(PermissionError):
            ipc_address(tmp_path)


def test_publisher_bounds_pending_events_and_reports_bind_errors(tmp_path):
    import queue

    # Test the nonblocking overload policy without racing the consumer thread.
    publisher = Publisher.__new__(Publisher)
    publisher.queue = queue.Queue(1)
    publisher.publish({constants.KEY_SEQUENCE: 1})
    publisher.publish({constants.KEY_SEQUENCE: 2})
    assert publisher.queue.qsize() == 1
    with pytest.raises(Exception):
        Publisher("invalid://socket", lambda: {})


def test_ipc_rejects_symlink_directory(tmp_path, monkeypatch):
    import tempfile

    with tempfile.TemporaryDirectory(prefix="csl-") as directory:
        path = Path(directory)
        target = path / constants.KEY_TARGET
        target.mkdir()
        (path / constants.APPLICATION_NAME).symlink_to(target, target_is_directory=True)
        monkeypatch.setenv(constants.ENV_XDG_RUNTIME_DIR, directory)
        with pytest.raises(PermissionError):
            ipc_address(tmp_path)


async def test_subscriber_marks_snapshot_offline_when_resync_fails(tmp_path):
    address = ipc_address(tmp_path)
    current = {
        constants.KEY_DAEMON_ID: "one",
        constants.KEY_SEQUENCE: 0,
        constants.KEY_ONLINE: True,
    }
    first = True

    async def fetch():
        nonlocal first
        if first:
            first = False
            return dict(current)
        raise RuntimeError("snapshot endpoint unavailable")

    publisher = Publisher(address, lambda: current)
    stream = Subscriber(address, fetch).snapshots()
    try:
        assert (await anext(stream))[constants.KEY_ONLINE]
        current[constants.KEY_SEQUENCE] = 2
        assert not (
            await asyncio.wait_for(anext(stream), test_constants.PUBSUB_WAIT_TIMEOUT_SECONDS)
        )[constants.KEY_ONLINE]
    finally:
        await stream.aclose()
        publisher.close()
