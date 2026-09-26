import asyncio

import aiohttp
import pytest
from fastmcp import Client as MCPClient

from code_search_local import constants
from code_search_local.client import Client
from code_search_local.config import Settings
from code_search_local.events import Subscriber, ipc_address
from tests import constants as test_constants
from tests.helpers import free_port, start_test_daemon, stop_process, wait_healthy


@pytest.fixture
def daemon(tmp_path):
    settings = Settings(
        storage=str(tmp_path / test_constants.KEY_STATE), port=free_port(), watch=False
    )
    log = (tmp_path / test_constants.PATH_DAEMON_LOG).open(test_constants.FILE_MODE_W)
    process = start_test_daemon(settings, log)
    client = Client(settings)
    try:
        wait_healthy(
            process, client, log, timeout=test_constants.FAST_DAEMON_STARTUP_TIMEOUT_SECONDS
        )
        yield client, process
    finally:
        stop_process(process, timeout=test_constants.PROCESS_SHUTDOWN_TIMEOUT_SECONDS)
        log.close()


async def test_http_mcp_two_projects(daemon, tmp_path):
    client, process = daemon
    roots = []
    for name in ("alpha", "beta"):
        root = tmp_path / name
        root.mkdir()
        (root / test_constants.PATH_MAIN_PY).write_text(f'def {name}(): return "{name}"\n')
        roots.append(str(root))
    jobs = await asyncio.gather(
        *(
            client.request(
                constants.HTTP_POST,
                constants.INDEX_ENDPOINT,
                data={constants.KEY_DIRECTORY_PATH: root, constants.KEY_WAIT: True},
            )
            for root in roots
        )
    )
    assert all(job[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED for job in jobs)
    stats = await client.stats()
    assert len(stats[constants.KEY_PROJECTS]) == 2
    assert stats[constants.KEY_SHARED][test_constants.KEY_MODEL_LOADS] == 1
    from code_search_local.service import token_for

    async with MCPClient(
        {
            constants.KEY_MCP_SERVERS: {
                constants.APPLICATION_NAME: {
                    test_constants.KEY_TRANSPORT: constants.TRANSPORT_HTTP,
                    constants.KEY_URL: client.settings.url + constants.MCP_ENDPOINT,
                    constants.KEY_HEADERS: {
                        constants.KEY_AUTHORIZATION: constants.HTTP_BEARER
                        + token_for(client.settings.root)
                    },
                }
            }
        }
    ) as mcp:
        tools = await mcp.list_tools()
        assert {tool.name for tool in tools} >= {
            "index_directory",
            "get_index_job",
            "search_code",
            "get_index_stats",
        }
        assert test_constants.VALUE_SWITCH_PROJECT not in {tool.name for tool in tools}
        by_name = {tool.name: tool for tool in tools}
        intents = {
            test_constants.KEY_INDEX_DIRECTORY: (
                "Index code",
                "Index codebase",
                "Update index",
                "get_index_job",
            ),
            test_constants.KEY_GET_INDEX_JOB: (
                "Is indexing done?",
                constants.KEY_FILES_PROCESSED,
                constants.STATUS_INTERRUPTED,
            ),
            test_constants.KEY_CANCEL_INDEX_JOB: (
                "Stop indexing",
                "Cancel the index update",
                "cooperative",
            ),
            test_constants.KEY_SEARCH_CODE: (
                "Search the code",
                "source locations",
                "index_directory",
            ),
            test_constants.KEY_GET_INDEX_STATS: ("Show indexing stats", "Which model/GPU is used?"),
            test_constants.KEY_GET_INDEX_STATUS: (
                "Is this codebase indexed?",
                "does not rescan disk",
            ),
            test_constants.KEY_FIND_SIMILAR_CODE: (
                "Find similar code",
                "exact",
                constants.KEY_CHUNK_ID,
            ),
            test_constants.KEY_CLEAR_INDEX: ("explicit request", "index_directory", "must be idle"),
            test_constants.KEY_LIST_PROJECTS: (
                "List indexed projects",
                "does not",
                "scan the filesystem",
            ),
        }
        assert set(by_name) == set(intents)
        for name, phrases in intents.items():
            tool = by_name[name]
            description = " ".join(tool.description.split())
            assert all(phrase in description for phrase in phrases), name
            assert tool.title, name
            for field, schema in tool.input_schema.get(test_constants.KEY_PROPERTIES, {}).items():
                assert schema.get(test_constants.KEY_DESCRIPTION), (name, field)
            if name not in {"index_directory", "cancel_index_job", "clear_index"}:
                assert tool.annotations.read_only_hint is True
        assert by_name[test_constants.KEY_CLEAR_INDEX].annotations.destructive_hint is True
        index_schema = by_name[test_constants.KEY_INDEX_DIRECTORY].input_schema
        assert (
            index_schema[test_constants.KEY_PROPERTIES][constants.KEY_INCREMENTAL][
                constants.KEY_DEFAULT
            ]
            is True
        )
        assert (
            index_schema[test_constants.KEY_PROPERTIES][constants.KEY_WAIT][constants.KEY_DEFAULT]
            is False
        )
        assert index_schema[test_constants.KEY_REQUIRED] == [constants.KEY_DIRECTORY_PATH]
        assert constants.KEY_PROJECT_PATH not in by_name[
            test_constants.KEY_GET_INDEX_STATS
        ].input_schema.get(test_constants.KEY_REQUIRED, [])
        result = await mcp.call_tool(
            "search_code", {constants.KEY_PROJECT_PATH: roots[0], constants.KEY_QUERY: "alpha"}
        )
        assert not result.is_error
        assert test_constants.VALUE_ALPHA in str(result)
        resource = await mcp.read_resource(constants.STATS_RESOURCE_URI)
        assert test_constants.KEY_MODEL_LOADS in str(resource)


async def test_auth_host_origin_and_invalid_requests(daemon):
    client, _ = daemon
    async with aiohttp.ClientSession() as session:
        async with session.get(client.settings.url + constants.HEALTH_ENDPOINT) as response:
            assert response.status == 401
        async with session.get(
            client.settings.url + constants.HEALTH_ENDPOINT,
            headers={test_constants.KEY_HOST: "evil.example"},
        ) as response:
            assert response.status == 403
        async with session.get(
            client.settings.url + constants.HEALTH_ENDPOINT,
            headers={test_constants.KEY_ORIGIN: "https://evil.example"},
        ) as response:
            assert response.status == 403
    with pytest.raises(RuntimeError, match="absolute"):
        await client.request(
            constants.HTTP_POST,
            constants.INDEX_ENDPOINT,
            data={constants.KEY_DIRECTORY_PATH: "relative"},
        )
    with pytest.raises(RuntimeError):
        await client.request(constants.HTTP_POST, constants.SEARCH_ENDPOINT, data={})


async def test_live_pubsub_receives_update_without_polling(daemon, tmp_path):
    client, _ = daemon
    subscriber = Subscriber(ipc_address(client.settings.root), client.stats)
    stream = subscriber.snapshots()
    initial = await anext(stream)
    root = tmp_path / test_constants.PATH_LIVE
    root.mkdir()
    (root / test_constants.PATH_A_PY).write_text("def live(): return 1\n")
    await client.request(
        constants.HTTP_POST,
        constants.INDEX_ENDPOINT,
        data={constants.KEY_DIRECTORY_PATH: str(root), constants.KEY_WAIT: True},
    )
    updated = await asyncio.wait_for(anext(stream), test_constants.EVENT_WAIT_TIMEOUT_SECONDS)
    assert updated[constants.KEY_SEQUENCE] > initial[constants.KEY_SEQUENCE]
    assert str(root) in updated[constants.KEY_PROJECTS]
    await stream.aclose()
