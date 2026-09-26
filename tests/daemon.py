"""Subprocess test harness: fake models and scheduling gates are explicit test inputs."""

import json
import logging
import time
from pathlib import Path

import click
import uvicorn

from code_search_local import constants
from code_search_local.config import Settings
from code_search_local.engine import Engine
from code_search_local.events import Publisher, ipc_address
from code_search_local.models import SentenceModel
from code_search_local.service import create_app, token_for
from tests import constants as test_constants
from tests.fakes import FakeModel


@click.command()
@click.option(
    constants.OPTION_STORAGE,
    required=True,
    help="Directory for this test daemon's indexes, models and state.",
)
@click.option(
    constants.OPTION_PORT, required=True, type=int, help="Loopback HTTP port for the test daemon."
)
@click.option(
    test_constants.OPTION_FAKE,
    is_flag=True,
    help="Use deterministic fake embeddings instead of loading a real model.",
)
@click.option(
    test_constants.OPTION_OFFLINE,
    is_flag=True,
    help="Require cached model files and forbid model downloads.",
)
@click.option(
    constants.OPTION_BACKEND,
    default=constants.BACKEND_CPU,
    show_default=True,
    help="Model execution backend: auto, cpu, cuda, rocm or mps.",
)
@click.option(
    constants.OPTION_MODEL,
    default=constants.DEFAULT_MODEL_ID,
    show_default=True,
    help="Hugging Face embedding model repository ID used without --fake.",
)
@click.option(
    test_constants.OPTION_GATE,
    default=0,
    type=int,
    show_default=True,
    help="Wait for this many running indexing jobs before model creation (120-second timeout); 0 disables the barrier.",
)
@click.option(
    test_constants.OPTION_CRASH_PHASE,
    default=None,
    help="Exit with code 86 at a publication phase: vector, metadata, before-manifest or after-manifest. Omit for normal execution.",
)
def main(storage, port, fake, offline, backend, model, gate, crash_phase):
    logging.basicConfig(level=logging.INFO)
    if not fake:
        # Audit actual artifact-transfer functions, including the bytes written.
        # This instrumentation exists only in the explicit test harness.
        import threading

        import huggingface_hub.file_download as downloads

        audit_lock = threading.Lock()
        original_get = downloads.http_get

        def audited_get(url, temp_file, **kwargs):
            before = temp_file.tell()
            result = original_get(url, temp_file, **kwargs)
            event = {
                test_constants.KEY_BLOB: Path(temp_file.name).name,
                test_constants.KEY_BYTES: temp_file.tell() - before,
            }
            with audit_lock:
                with (Path(storage) / test_constants.PATH_DOWNLOAD_TRANSFERS_JSONL).open(
                    test_constants.FILE_MODE_A
                ) as audit:
                    audit.write(json.dumps(event, sort_keys=True) + "\n")
            return result

        downloads.http_get = audited_get
    if crash_phase:
        import os

        import faiss

        import code_search_local.storage as storage_module

        original_write = faiss.write_index
        original_json = storage_module.atomic_json

        def write_index(*args, **kwargs):
            original_write(*args, **kwargs)
            if crash_phase == test_constants.VALUE_VECTOR:
                os._exit(86)

        def atomic(path, value, **kwargs):
            if (
                path.name == constants.PATH_CURRENT_JSON
                and crash_phase == test_constants.VALUE_BEFORE_MANIFEST
            ):
                os._exit(86)
            original_json(path, value, **kwargs)
            if (
                path.name == constants.PATH_GENERATION_JSON
                and crash_phase == constants.KEY_METADATA
            ):
                os._exit(86)
            if (
                path.name == constants.PATH_CURRENT_JSON
                and crash_phase == test_constants.VALUE_AFTER_MANIFEST
            ):
                os._exit(86)

        faiss.write_index = write_index
        storage_module.atomic_json = atomic
    holder = {}

    def factory(settings, report):
        if gate:
            deadline = time.monotonic() + test_constants.MODEL_GATE_TIMEOUT_SECONDS
            while True:
                jobs = (
                    holder[test_constants.KEY_ENGINE].state.snapshot()[constants.KEY_JOBS].values()
                )
                if (
                    sum(job[constants.KEY_STATUS] == constants.STATUS_RUNNING for job in jobs)
                    >= gate
                ):
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Concurrent client scheduling barrier timed out")
                time.sleep(test_constants.MODEL_GATE_POLL_SECONDS)
        return (FakeModel if fake else SentenceModel)(settings, report)

    settings = Settings(
        storage=storage,
        port=port,
        watch=False,
        backend=backend,
        cpu_fallback=False,
        model=model,
        offline=offline,
    )
    engine = Engine(settings, model_factory=factory, recover=False)
    holder[test_constants.KEY_ENGINE] = engine
    publisher = Publisher(ipc_address(settings.root), engine.state.snapshot)
    engine.state.publish = publisher.publish
    try:
        uvicorn.run(
            create_app(engine, token_for(settings.root, create=True)), host=settings.host, port=port
        )
    finally:
        publisher.close()
        engine.close()


if __name__ == "__main__":
    main()
