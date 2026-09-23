"""Subprocess test harness: fake models and scheduling gates are explicit test inputs."""

import json
import logging
import time
from pathlib import Path

import click
import uvicorn

from code_search_local.config import Settings
from code_search_local.engine import Engine
from code_search_local.events import Publisher, ipc_address
from code_search_local.models import SentenceModel
from code_search_local.service import create_app, token_for
from tests.fakes import FakeModel


@click.command()
@click.option("--storage", required=True)
@click.option("--port", required=True, type=int)
@click.option("--fake", is_flag=True)
@click.option("--offline", is_flag=True)
@click.option("--backend", default="cpu")
@click.option("--model", default="google/embeddinggemma-300m")
@click.option("--gate", default=0, type=int)
@click.option("--crash-phase", default=None)
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
            event = {"blob": Path(temp_file.name).name, "bytes": temp_file.tell() - before}
            with audit_lock:
                with (Path(storage) / "download-transfers.jsonl").open("a") as audit:
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
            if crash_phase == "vector":
                os._exit(86)

        def atomic(path, value, **kwargs):
            if path.name == "current.json" and crash_phase == "before-manifest":
                os._exit(86)
            original_json(path, value, **kwargs)
            if path.name == "generation.json" and crash_phase == "metadata":
                os._exit(86)
            if path.name == "current.json" and crash_phase == "after-manifest":
                os._exit(86)

        faiss.write_index = write_index
        storage_module.atomic_json = atomic
    holder = {}

    def factory(settings, report):
        if gate:
            deadline = time.monotonic() + 120
            while True:
                jobs = holder["engine"].state.snapshot()["jobs"].values()
                if sum(job["status"] == "running" for job in jobs) >= gate:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Concurrent client scheduling barrier timed out")
                time.sleep(0.02)
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
    holder["engine"] = engine
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
