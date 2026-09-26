"""Bounded, sequenced pub-sub notifications over a private Unix socket."""

import asyncio
import hashlib
import os
import queue
import threading
import time
from pathlib import Path

from code_search_local import constants


def ipc_address(root: Path) -> str:
    runtime = Path(
        os.environ.get(
            constants.ENV_XDG_RUNTIME_DIR,
            constants.IPC_RUNTIME_DIRECTORY_TEMPLATE.format(uid=os.getuid()),
        )
    )
    directory = runtime / constants.APPLICATION_NAME
    key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[
        : constants.IPC_ADDRESS_DIGEST_CHARACTERS
    ]
    # sockaddr_un has a small fixed path limit, independent of filesystem limits.
    if len(os.fsencode(directory / (key + constants.PATH_SOCK))) > constants.IPC_MAX_PATH_BYTES:
        directory = Path(constants.IPC_SHORT_DIRECTORY_TEMPLATE.format(uid=os.getuid()))
    directory.mkdir(parents=True, exist_ok=True, mode=constants.PRIVATE_DIRECTORY_MODE)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        raise PermissionError("IPC directory is owned by another user")
    directory.chmod(constants.PRIVATE_DIRECTORY_MODE)
    return constants.IPC_SCHEME + str(directory / (key + constants.PATH_SOCK))


class Publisher:
    def __init__(self, address, snapshot, *, capacity=constants.PUBSUB_QUEUE_CAPACITY):
        self.address, self.snapshot = address, snapshot
        self.queue = queue.Queue(capacity)
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(
            target=self._run, name=constants.PUBLISHER_THREAD_NAME, daemon=True
        )
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
        socket.setsockopt(zmq.SNDHWM, constants.PUBSUB_QUEUE_CAPACITY)
        socket.setsockopt(zmq.LINGER, constants.SOCKET_LINGER_MILLISECONDS)
        try:
            socket.bind(self.address)
            Path(self.address.removeprefix(constants.IPC_SCHEME)).chmod(constants.PRIVATE_FILE_MODE)
            self.ready.set()
            last = time.monotonic()
            while not self.stop.is_set():
                try:
                    event = self.queue.get(timeout=constants.PUBSUB_QUEUE_TIMEOUT_SECONDS)
                    socket.send_json(event)
                except queue.Empty:
                    pass
                if time.monotonic() - last >= constants.PUBSUB_HEARTBEAT_INTERVAL_SECONDS:
                    current = self.snapshot()
                    socket.send_json(
                        {
                            constants.KEY_TYPE: constants.EVENT_HEARTBEAT,
                            constants.KEY_DAEMON_ID: current[constants.KEY_DAEMON_ID],
                            constants.KEY_SEQUENCE: current[constants.KEY_SEQUENCE],
                        }
                    )
                    last = time.monotonic()
        except Exception as error:
            self.error = error
            self.ready.set()
        finally:
            socket.close()
            context.term()
            Path(self.address.removeprefix(constants.IPC_SCHEME)).unlink(missing_ok=True)

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
        socket.setsockopt(zmq.RCVHWM, constants.PUBSUB_QUEUE_CAPACITY)
        socket.setsockopt(zmq.LINGER, constants.SOCKET_LINGER_MILLISECONDS)
        socket.connect(self.address)
        try:
            current = await self.fetch()
            yield current
            while True:
                try:
                    event = await asyncio.wait_for(
                        socket.recv_json(), timeout=constants.PUBSUB_RECEIVE_TIMEOUT_SECONDS
                    )
                except TimeoutError:
                    if current.get(constants.KEY_ONLINE):
                        current = {**current, constants.KEY_ONLINE: False}
                        yield current
                    continue
                if (
                    event[constants.KEY_DAEMON_ID] != current[constants.KEY_DAEMON_ID]
                    or event[constants.KEY_SEQUENCE] > current[constants.KEY_SEQUENCE]
                    or not current.get(constants.KEY_ONLINE)
                ):
                    try:
                        current = await self.fetch()
                    except (OSError, RuntimeError):
                        current = {**current, constants.KEY_ONLINE: False}
                    yield current
        finally:
            socket.close()
            context.term()
