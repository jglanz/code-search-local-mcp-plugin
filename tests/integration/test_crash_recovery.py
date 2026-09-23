import asyncio
import subprocess
import sys

import pytest

from code_search_local.client import Client
from code_search_local.config import Settings
from code_search_local.engine import Engine
from tests.fakes import FakeModel
from tests.helpers import free_port, wait_healthy


@pytest.mark.parametrize("phase", ["vector", "metadata", "before-manifest", "after-manifest"])
def test_process_termination_during_commit(tmp_path, phase):
    settings = Settings(storage=str(tmp_path / "state"), port=free_port(), watch=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "old.py").write_text("def old(): return 1\n")
    first = Engine(settings, model_factory=FakeModel)
    first.index(str(root))
    first.close()
    (root / "new.py").write_text("def added(): return 2\n")
    log = (tmp_path / "crash.log").open("w+")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.daemon",
            "--fake",
            "--storage",
            settings.storage,
            "--port",
            str(settings.port),
            "--crash-phase",
            phase,
        ],
        stdout=log,
        stderr=log,
    )
    client = Client(settings)
    try:
        wait_healthy(process, client, log, timeout=15)
        with pytest.raises(OSError):
            asyncio.run(
                client.request(
                    "POST", "/api/v1/index", data={"directory_path": str(root), "wait": True}
                )
            )
        assert process.wait(10) == 86
        recovered = Engine(settings, model_factory=FakeModel, recover=False)
        try:
            results = recovered.search(str(root), "function")["results"]
            assert len(results) == (2 if phase == "after-manifest" else 1)
            assert len(results) == recovered.state.snapshot()["projects"][str(root)]["chunks"]
            assert recovered.index(str(root))["status"] == "succeeded"
            assert len(recovered.search(str(root), "function")["results"]) == 2
        finally:
            recovered.close()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(10)
        log.close()
