"""Bounded, sequenced pub-sub notifications over a private Unix socket."""

import asyncio
import hashlib
import os
import queue
import threading
import time
from pathlib import Path


def ipc_address(root: Path) -> str:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/code-search-local-{os.getuid()}"))
    directory = runtime / "code-search-local"
    key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    # sockaddr_un has a small fixed path limit, independent of filesystem limits.
    if len(os.fsencode(directory / (key + ".sock"))) > 100:
        directory = Path(f"/tmp/csl-{os.getuid()}")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        raise PermissionError("IPC directory is owned by another user")
    directory.chmod(0o700)
    return f"ipc://{directory / (key + '.sock')}"


class Publisher:
    def __init__(self, address, snapshot, *, capacity=256):
        self.address, self.snapshot = address, snapshot
        self.queue = queue.Queue(capacity)
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, name="stats-publisher", daemon=True)
        self.thread.start()
        self.ready.wait()
        if self.error:
            raise self.error

    def publish(self, event):
        try:
            self.queue.put_nowait(event)
        except queue.Full:
            # Heartbeats carry the latest sequence. Subscribers resync after any dropped event.
            pass

    def _run(self):
        import zmq

        context = zmq.Context()
        socket = context.socket(zmq.PUB)
        socket.setsockopt(zmq.SNDHWM, 256)
        socket.setsockopt(zmq.LINGER, 0)
        try:
            socket.bind(self.address)
            Path(self.address.removeprefix("ipc://")).chmod(0o600)
            self.ready.set()
            last = time.monotonic()
            while not self.stop.is_set():
                try:
                    event = self.queue.get(timeout=0.2)
                    socket.send_json(event)
                except queue.Empty:
                    pass
                if time.monotonic() - last >= 1:
                    current = self.snapshot()
                    socket.send_json(
                        {
                            "type": "heartbeat",
                            "daemon_id": current["daemon_id"],
                            "sequence": current["sequence"],
                        }
                    )
                    last = time.monotonic()
        except Exception as error:
            self.error = error
            self.ready.set()
        finally:
            socket.close()
            context.term()
            Path(self.address.removeprefix("ipc://")).unlink(missing_ok=True)

    def close(self):
        self.stop.set()
        self.thread.join()


class Subscriber:
    """Subscribe before snapshot; recover gaps and restarts using a new snapshot."""

    def __init__(self, address, fetch):
        self.address, self.fetch = address, fetch

    async def snapshots(self):
        import zmq
        import zmq.asyncio

        context = zmq.asyncio.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.SUBSCRIBE, b"")
        socket.setsockopt(zmq.RCVHWM, 256)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect(self.address)
        try:
            current = await self.fetch()
            yield current
            while True:
                try:
                    event = await asyncio.wait_for(socket.recv_json(), timeout=3)
                except TimeoutError:
                    if current.get("online"):
                        current = {**current, "online": False}
                        yield current
                    continue
                if (
                    event["daemon_id"] != current["daemon_id"]
                    or event["sequence"] > current["sequence"]
                    or not current.get("online")
                ):
                    try:
                        current = await self.fetch()
                    except (OSError, RuntimeError):
                        current = {**current, "online": False}
                    yield current
        finally:
            socket.close()
            context.term()
