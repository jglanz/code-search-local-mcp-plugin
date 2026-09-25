import fastmcp
import httpx2
import pytest

from code_search_local.config import Settings
from code_search_local.engine import Engine
from code_search_local.service import create_app, token_for
from code_search_local.storage import project_id
from tests.fakes import FakeModel


async def test_rest_and_mcp_contracts(tmp_path, monkeypatch):
    settings = Settings(storage=str(tmp_path / "state"), watch=False)
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
    root = tmp_path / "project"
    root.mkdir()
    (root / "code.py").write_text("def method(): return 42\n")
    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app), base_url=settings.url
        ) as client:
            assert (await client.get("/api/v1/health")).status_code == 401
            assert (await client.get("/api/v1/health", headers={"host": "bad"})).status_code == 403
            client.headers["Authorization"] = "Bearer " + token
            assert (await client.post("/api/v1/model")).json()["model"]
            assert (await client.get("/api/v1/health")).status_code == 200
            assert (await client.get("/api/v1/stats")).status_code == 200
            response = await client.post(
                "/api/v1/index", json={"directory_path": str(root), "wait": True}
            )
            job = response.json()
            assert job["status"] == "succeeded"
            assert (
                await client.get("/api/v1/jobs/" + job["job_id"], params={"project": str(root)})
            ).json()["status"] == "succeeded"
            assert (
                await client.delete("/api/v1/jobs/" + job["job_id"], params={"project": str(root)})
            ).json()["status"] == "succeeded"
            assert (
                await client.get("/api/v1/stats", params={"project": str(root)})
            ).status_code == 200
            result = await client.post(
                "/api/v1/search", json={"project_path": str(root), "query": "method"}
            )
            assert result.json()["results"][0]["name"] == "method"
            assert (await client.post("/api/v1/index", json={})).status_code == 400
        async with fastmcp.Client(servers[0]) as client:
            assert "Index codebase" in client.instructions
            assert "absolute workspace root" in client.instructions
            index = await client.call_tool(
                "index_directory", {"directory_path": str(root), "wait": True}
            )
            assert not index.is_error
            jobs = engine.state.snapshot()["jobs"]
            latest = list(jobs)[-1]
            assert not (
                await client.call_tool(
                    "get_index_job", {"project_path": str(root), "job_id": latest}
                )
            ).is_error
            assert not (
                await client.call_tool(
                    "cancel_index_job", {"project_path": str(root), "job_id": latest}
                )
            ).is_error
            assert not (
                await client.call_tool(
                    "search_code", {"project_path": str(root), "query": "method"}
                )
            ).is_error
            for params in ({}, {"project_path": str(root)}):
                assert not (await client.call_tool("get_index_stats", params)).is_error
            assert not (await client.call_tool("list_projects", {})).is_error
            assert not (
                await client.call_tool("get_index_status", {"project_path": str(root)})
            ).is_error
            hit = engine.search(str(root), "method")["results"][0]
            assert not (
                await client.call_tool(
                    "find_similar_code", {"project_path": str(root), "chunk_id": hit["chunk_id"]}
                )
            ).is_error
            assert not (await client.call_tool("clear_index", {"project_path": str(root)})).is_error

            assert await client.read_resource("code-search-local://stats")
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
    calls = []
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    result = CliRunner().invoke(main, ["serve", "--storage", str(tmp_path / "state"), "--no-watch"])
    assert result.exit_code == 0, result.output
    assert calls[0]["workers"] == 1

    def fail(*args, **kwargs):
        raise RuntimeError("cannot bind")

    monkeypatch.setattr(uvicorn, "run", fail)
    result = CliRunner().invoke(main, ["serve", "--storage", str(tmp_path / "state"), "--no-watch"])
    assert result.exit_code == 1


async def test_non_http_scope_delegates():
    from unittest.mock import AsyncMock

    from code_search_local.service import LocalAuth

    application = AsyncMock()
    app = LocalAuth(application, Settings(), "token")
    await app({"type": "lifespan"}, None, None)
    application.assert_awaited_once()
