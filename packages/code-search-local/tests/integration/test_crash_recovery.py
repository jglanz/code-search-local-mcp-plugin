import asyncio

import pytest

from code_search_local import constants
from code_search_local.client import Client
from code_search_local.config import Settings
from code_search_local.engine import Engine
from tests import constants as test_constants
from tests.fakes import FakeModel
from tests.helpers import free_port, start_test_daemon, stop_process, wait_healthy


@pytest.mark.parametrize(
    "phase", ["vector", constants.KEY_METADATA, "before-manifest", "after-manifest"]
)
def test_process_termination_during_commit(tmp_path, phase):
    settings = Settings(
        storage=str(tmp_path / test_constants.KEY_STATE), port=free_port(), watch=False
    )
    root = tmp_path / constants.KEY_PROJECT
    root.mkdir()
    (root / test_constants.PATH_OLD_PY).write_text("def old(): return 1\n")
    first = Engine(settings, model_factory=FakeModel)
    first.index(str(root))
    first.close()
    (root / test_constants.PATH_NEW_PY).write_text("def added(): return 2\n")
    log = (tmp_path / test_constants.PATH_CRASH_LOG).open(test_constants.FILE_MODE_W)
    process = start_test_daemon(settings, log, test_constants.OPTION_CRASH_PHASE, phase)
    client = Client(settings)
    try:
        wait_healthy(
            process, client, log, timeout=test_constants.FAST_DAEMON_STARTUP_TIMEOUT_SECONDS
        )
        with pytest.raises(OSError):
            asyncio.run(
                client.request(
                    constants.HTTP_POST,
                    constants.INDEX_ENDPOINT,
                    data={constants.KEY_DIRECTORY_PATH: str(root), constants.KEY_WAIT: True},
                )
            )
        assert process.wait(test_constants.CRASH_EXIT_TIMEOUT_SECONDS) == 86
        recovered = Engine(settings, model_factory=FakeModel, recover=False)
        try:
            results = recovered.search(str(root), constants.KEY_FUNCTION)[constants.KEY_RESULTS]
            assert len(results) == (2 if phase == test_constants.VALUE_AFTER_MANIFEST else 1)
            assert (
                len(results)
                == recovered.state.snapshot()[constants.KEY_PROJECTS][str(root)][
                    constants.KEY_CHUNKS
                ]
            )
            assert recovered.index(str(root))[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED
            assert (
                len(recovered.search(str(root), constants.KEY_FUNCTION)[constants.KEY_RESULTS]) == 2
            )
        finally:
            recovered.close()
    finally:
        stop_process(process, timeout=test_constants.CRASH_EXIT_TIMEOUT_SECONDS)
        log.close()
