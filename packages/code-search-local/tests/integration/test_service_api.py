import fastmcp
import httpx2
import pytest

from code_search_local import constants
from code_search_local.config import Settings
from code_search_local.engine import Engine
from code_search_local.service import create_app, token_for
from code_search_local.storage import project_id
from tests import constants as test_constants
from tests.fakes import FakeModel


async def test_rest_and_mcp_contracts(tmp_path, monkeypatch):
    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE), watch=False)
    engine = Engine(settings, model_factory=FakeModel)
    servers = []
    original = fastmcp.FastMCP

    def track(*args, **kwargs):
        server = original(*args, **kwargs)
        servers.append(server)
        return server

    monkeypatch.setattr(fastmcp, "FastMCP", track)
    token = token_for(settings.root, create=True)
    app = create_app(engine, token)
    root = tmp_path / constants.KEY_PROJECT
    root.mkdir()
    (root / test_constants.PATH_CODE_PY).write_text("def method(): return 42\n")
    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app), base_url=settings.url
        ) as client:
            assert (await client.get(constants.HEALTH_ENDPOINT)).status_code == 401
            assert (
                await client.get(constants.HEALTH_ENDPOINT, headers={constants.KEY_HOST: "bad"})
            ).status_code == 403
            client.headers[constants.KEY_AUTHORIZATION] = constants.HTTP_BEARER + token
            assert (await client.post(constants.MODEL_ENDPOINT)).json()[constants.KEY_MODEL]
            assert (await client.get(constants.HEALTH_ENDPOINT)).status_code == 200
            assert (await client.get(constants.STATS_ENDPOINT)).status_code == 200
            response = await client.post(
                constants.INDEX_ENDPOINT,
                json={constants.KEY_DIRECTORY_PATH: str(root), constants.KEY_WAIT: True},
            )
            job = response.json()
            assert job[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED
            assert (
                await client.get(
                    "/api/v1/jobs/" + job[constants.KEY_JOB_ID],
                    params={constants.KEY_PROJECT: str(root)},
                )
            ).json()[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED
            assert (
                await client.delete(
                    "/api/v1/jobs/" + job[constants.KEY_JOB_ID],
                    params={constants.KEY_PROJECT: str(root)},
                )
            ).json()[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED
            assert (
                await client.get(
                    constants.STATS_ENDPOINT, params={constants.KEY_PROJECT: str(root)}
                )
            ).status_code == 200
            result = await client.post(
                constants.SEARCH_ENDPOINT,
                json={
                    constants.KEY_PROJECT_PATH: str(root),
                    constants.KEY_QUERY: constants.SYNTAX_METHOD,
                },
            )
            assert (
                result.json()[constants.KEY_RESULTS][0][constants.KEY_NAME]
                == constants.SYNTAX_METHOD
            )
            assert (await client.post(constants.INDEX_ENDPOINT, json={})).status_code == 400
        async with fastmcp.Client(servers[0]) as client:
            assert "Index codebase" in client.instructions
            assert "absolute workspace root" in client.instructions
            index = await client.call_tool(
                "index_directory",
                {constants.KEY_DIRECTORY_PATH: str(root), constants.KEY_WAIT: True},
            )
            assert not index.is_error
            jobs = engine.state.snapshot()[constants.KEY_JOBS]
            latest = list(jobs)[-1]
            assert not (
                await client.call_tool(
                    "get_index_job",
                    {constants.KEY_PROJECT_PATH: str(root), constants.KEY_JOB_ID: latest},
                )
            ).is_error
            assert not (
                await client.call_tool(
                    "cancel_index_job",
                    {constants.KEY_PROJECT_PATH: str(root), constants.KEY_JOB_ID: latest},
                )
            ).is_error
            assert not (
                await client.call_tool(
                    "search_code",
                    {
                        constants.KEY_PROJECT_PATH: str(root),
                        constants.KEY_QUERY: constants.SYNTAX_METHOD,
                    },
                )
            ).is_error
            for params in ({}, {constants.KEY_PROJECT_PATH: str(root)}):
                assert not (await client.call_tool("get_index_stats", params)).is_error
            assert not (await client.call_tool("list_projects", {})).is_error
            assert not (
                await client.call_tool("get_index_status", {constants.KEY_PROJECT_PATH: str(root)})
            ).is_error
            hit = engine.search(str(root), constants.SYNTAX_METHOD)[constants.KEY_RESULTS][0]
            assert not (
                await client.call_tool(
                    "find_similar_code",
                    {
                        constants.KEY_PROJECT_PATH: str(root),
                        constants.KEY_CHUNK_ID: hit[constants.KEY_CHUNK_ID],
                    },
                )
            ).is_error
            assert not (
                await client.call_tool("clear_index", {constants.KEY_PROJECT_PATH: str(root)})
            ).is_error

            assert await client.read_resource(constants.STATS_RESOURCE_URI)
            assert await client.read_resource("code-search-local://stats/" + project_id(str(root)))
            with pytest.raises(Exception):
                await client.read_resource("code-search-local://stats/unknown")
    finally:
        engine.close()


def test_serve_lifecycle_without_opening_port(tmp_path, monkeypatch):
    from click.testing import CliRunner

    import code_search_local.engine as module
    from code_search_local.cli import main

    original = module.Engine
    monkeypatch.setattr(
        module, "Engine", lambda settings: original(settings, model_factory=FakeModel)
    )

    def invoke_serve():
        return CliRunner().invoke(
            main,
            [
                constants.COMMAND_SERVE,
                constants.OPTION_STORAGE,
                str(tmp_path / test_constants.KEY_STATE),
                test_constants.OPTION_NO_WATCH,
            ],
        )

    calls = []
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    result = invoke_serve()
    assert result.exit_code == 0, result.output
    assert calls[0][test_constants.KEY_WORKERS] == 1

    def fail(*args, **kwargs):
        raise RuntimeError("cannot bind")

    monkeypatch.setattr(uvicorn, "run", fail)
    result = invoke_serve()
    assert result.exit_code == 1


async def test_non_http_scope_delegates():
    from unittest.mock import AsyncMock

    from code_search_local.service import LocalAuth

    application = AsyncMock()
    app = LocalAuth(application, Settings(), constants.KEY_TOKEN)
    await app({constants.KEY_TYPE: "lifespan"}, None, None)
    application.assert_awaited_once()
