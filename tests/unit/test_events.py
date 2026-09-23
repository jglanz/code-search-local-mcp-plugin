import asyncio
from pathlib import Path

import pytest

from code_search_local.events import Publisher, Subscriber, ipc_address


async def test_events_detect_gaps_disconnect_and_restart(tmp_path):
    address = ipc_address(tmp_path / "state")
    current = {
        "daemon_id": "one",
        "sequence": 0,
        "online": True,
        "projects": {},
        "shared": {},
        "jobs": {},
    }
    calls = []

    async def fetch():
        calls.append(1)
        return dict(current)

    publisher = Publisher(address, lambda: current)
    stream = Subscriber(address, fetch).snapshots()
    try:
        assert (await anext(stream))["sequence"] == 0
        current["sequence"] = 100
        # Even if an event is dropped during socket setup, the heartbeat resynchronizes.
        publisher.publish({"type": "changed", "daemon_id": "one", "sequence": 100})
        assert (await asyncio.wait_for(anext(stream), 4))["sequence"] == 100
        assert len(calls) == 2
        publisher.close()
        disconnected = await asyncio.wait_for(anext(stream), 4)
        assert not disconnected["online"]
        current.update(daemon_id="two", sequence=0)
        publisher = Publisher(address, lambda: current)
        reconnected = await asyncio.wait_for(anext(stream), 4)
        assert reconnected["daemon_id"] == "two" and reconnected["online"]
    finally:
        await stream.aclose()
        publisher.close()
    assert not Path(address.removeprefix("ipc://")).exists()


def test_private_short_socket_paths_and_symlink_rejection(tmp_path, monkeypatch):
    long = tmp_path / ("a" * 80)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(long))
    assert len(ipc_address(tmp_path).removeprefix("ipc://").encode()) <= 100
    short = tmp_path / "r"
    short.mkdir()
    (short / "code-search-local").symlink_to(tmp_path / "target", target_is_directory=True)
    (tmp_path / "target").mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(short))
    # A genuinely short runtime root is necessary to exercise the symlink check.
    if len(str(short / "code-search-local" / "0123456789abcdef.sock")) <= 100:
        with pytest.raises(PermissionError):
            ipc_address(tmp_path)


def test_publisher_bounds_pending_events_and_reports_bind_errors(tmp_path):
    import queue

    # Test the nonblocking overload policy without racing the consumer thread.
    publisher = Publisher.__new__(Publisher)
    publisher.queue = queue.Queue(1)
    publisher.publish({"sequence": 1})
    publisher.publish({"sequence": 2})
    assert publisher.queue.qsize() == 1
    with pytest.raises(Exception):
        Publisher("invalid://socket", lambda: {})


def test_ipc_rejects_symlink_directory(tmp_path, monkeypatch):
    import tempfile

    with tempfile.TemporaryDirectory(prefix="csl-") as directory:
        path = Path(directory)
        target = path / "target"
        target.mkdir()
        (path / "code-search-local").symlink_to(target, target_is_directory=True)
        monkeypatch.setenv("XDG_RUNTIME_DIR", directory)
        with pytest.raises(PermissionError):
            ipc_address(tmp_path)


async def test_subscriber_marks_snapshot_offline_when_resync_fails(tmp_path):
    address = ipc_address(tmp_path)
    current = {"daemon_id": "one", "sequence": 0, "online": True}
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
        assert (await anext(stream))["online"]
        current["sequence"] = 2
        assert not (await asyncio.wait_for(anext(stream), 4))["online"]
    finally:
        await stream.aclose()
        publisher.close()
