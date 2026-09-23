import asyncio
import subprocess
import sys

import aiohttp
import pytest
from fastmcp import Client as MCPClient

from code_search_local.client import Client
from code_search_local.config import Settings
from code_search_local.events import Subscriber, ipc_address
from tests.helpers import free_port, wait_healthy


@pytest.fixture
def daemon(tmp_path):
    settings = Settings(storage=str(tmp_path / "state"), port=free_port(), watch=False)
    log = (tmp_path / "daemon.log").open("w+")
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
        ],
        stdout=log,
        stderr=log,
    )
    client = Client(settings)
    try:
        wait_healthy(process, client, log, timeout=15)
        yield client, process
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(15)
        log.close()


async def test_http_mcp_two_projects(daemon, tmp_path):
    client, process = daemon
    roots = []
    for name in ("alpha", "beta"):
        root = tmp_path / name
        root.mkdir()
        (root / "main.py").write_text(f'def {name}(): return "{name}"\n')
        roots.append(str(root))
    jobs = await asyncio.gather(
        *(
            client.request("POST", "/api/v1/index", data={"directory_path": root, "wait": True})
            for root in roots
        )
    )
    assert all(job["status"] == "succeeded" for job in jobs)
    stats = await client.stats()
    assert len(stats["projects"]) == 2
    assert stats["shared"]["model_loads"] == 1
    from code_search_local.service import token_for

    async with MCPClient(
        {
            "mcpServers": {
                "code-search-local": {
                    "transport": "http",
                    "url": client.settings.url + "/mcp",
                    "headers": {"Authorization": "Bearer " + token_for(client.settings.root)},
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
        assert "switch_project" not in {tool.name for tool in tools}
        result = await mcp.call_tool("search_code", {"project_path": roots[0], "query": "alpha"})
        assert not result.is_error
        assert "alpha" in str(result)
        resource = await mcp.read_resource("code-search-local://stats")
        assert "model_loads" in str(resource)


async def test_auth_host_origin_and_invalid_requests(daemon):
    client, _ = daemon
    async with aiohttp.ClientSession() as session:
        async with session.get(client.settings.url + "/api/v1/health") as response:
            assert response.status == 401
        async with session.get(
            client.settings.url + "/api/v1/health", headers={"Host": "evil.example"}
        ) as response:
            assert response.status == 403
        async with session.get(
            client.settings.url + "/api/v1/health", headers={"Origin": "https://evil.example"}
        ) as response:
            assert response.status == 403
    with pytest.raises(RuntimeError, match="absolute"):
        await client.request("POST", "/api/v1/index", data={"directory_path": "relative"})
    with pytest.raises(RuntimeError):
        await client.request("POST", "/api/v1/search", data={})


async def test_live_pubsub_receives_update_without_polling(daemon, tmp_path):
    client, _ = daemon
    subscriber = Subscriber(ipc_address(client.settings.root), client.stats)
    stream = subscriber.snapshots()
    initial = await anext(stream)
    root = tmp_path / "live"
    root.mkdir()
    (root / "a.py").write_text("def live(): return 1\n")
    await client.request("POST", "/api/v1/index", data={"directory_path": str(root), "wait": True})
    updated = await asyncio.wait_for(anext(stream), 5)
    assert updated["sequence"] > initial["sequence"]
    assert str(root) in updated["projects"]
    await stream.aclose()
