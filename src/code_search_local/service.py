"""Authenticated loopback HTTP MCP and administration API."""

import asyncio
import hmac
import json
import secrets
from pathlib import Path

from .config import canonical_project
from .storage import atomic_json


def token_for(root: Path, *, create=False):
    path = root / "auth.json"
    if not path.exists():
        if not create:
            raise RuntimeError("Service is not configured; run code-search-local setup")
        atomic_json(path, {"token": secrets.token_urlsafe(32)}, mode=0o600)
    return json.loads(path.read_text())["token"]


class LocalAuth:
    def __init__(self, app, settings, token):
        self.app, self.token = app, token
        self.hosts = {
            f"127.0.0.1:{settings.port}",
            f"localhost:{settings.port}",
            f"[::1]:{settings.port}",
        }
        self.origins = {"http://" + host for host in self.hosts}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse

        headers = {key.decode().lower(): value.decode() for key, value in scope["headers"]}
        if headers.get("host") not in self.hosts or (
            headers.get("origin") and headers["origin"] not in self.origins
        ):
            return await JSONResponse({"error": "Invalid Host or Origin"}, status_code=403)(
                scope, receive, send
            )
        expected = "Bearer " + self.token
        if not hmac.compare_digest(headers.get("authorization", ""), expected):
            return await JSONResponse({"error": "Unauthorized"}, status_code=401)(
                scope, receive, send
            )
        return await self.app(scope, receive, send)


def create_app(engine, token):
    from fastmcp import FastMCP
    from starlette.responses import JSONResponse

    mcp = FastMCP(
        "code-search-local",
        instructions=(
            "Local semantic search for multiple projects. Always pass the absolute workspace root as "
            "project_path. index_directory returns a durable job; poll get_index_job until succeeded. "
            "Indexes and models are shared by the user service and survive client disconnects."
        ),
    )

    @mcp.tool
    async def index_directory(
        directory_path: str,
        incremental: bool = True,
        file_patterns: list[str] | None = None,
        wait: bool = False,
    ) -> dict:
        """Index an absolute project root. Returns a durable job ID; wait=True waits for completion."""
        return await asyncio.to_thread(
            engine.index,
            directory_path,
            wait=wait,
            incremental=incremental,
            file_patterns=file_patterns,
        )

    @mcp.tool
    async def get_index_job(project_path: str, job_id: str) -> dict:
        """Read an indexing job's status and progress, scoped to its absolute project root."""
        return engine.job(project_path, job_id)

    @mcp.tool
    async def cancel_index_job(project_path: str, job_id: str) -> dict:
        """Cancel a queued or running job without discarding the last committed index."""
        return engine.cancel(project_path, job_id)

    @mcp.tool
    async def search_code(
        project_path: str, query: str, k: int = 10, filters: dict[str, str] | None = None
    ) -> dict:
        """Search one project's committed index. Optional filters match metadata with shell globs."""
        return await asyncio.to_thread(engine.search, project_path, query, k=k, filters=filters)

    @mcp.tool
    async def get_index_stats(project_path: str | None = None) -> dict:
        """Read per-project cache, index, change and search statistics plus shared model statistics."""
        project = canonical_project(project_path, absolute=True) if project_path else None
        return engine.state.snapshot(project)

    @mcp.tool
    async def get_index_status(project_path: str) -> dict:
        """Inspect this project's committed index and any active indexing jobs."""
        return engine.state.snapshot(canonical_project(project_path, absolute=True))

    @mcp.tool
    async def find_similar_code(project_path: str, chunk_id: str, k: int = 5) -> dict:
        """Find chunks similar to an indexed chunk within the same absolute project root."""
        return await asyncio.to_thread(engine.similar, project_path, chunk_id, k)

    @mcp.tool
    async def clear_index(project_path: str) -> dict:
        """Clear an idle project's index and pause its watcher until indexing is requested again."""
        return await asyncio.to_thread(engine.clear, project_path)

    @mcp.tool
    async def list_projects() -> dict:
        """List registered project roots and committed index information."""
        return engine.state.snapshot()["projects"]

    @mcp.resource("code-search-local://stats")
    async def stats_resource() -> str:
        return json.dumps(engine.state.snapshot())

    @mcp.resource("code-search-local://stats/{project_id}")
    async def project_resource(project_id: str) -> str:
        from .storage import project_id as identify

        for project in engine.state.snapshot()["projects"]:
            if identify(project) == project_id:
                return json.dumps(engine.state.snapshot(project))
        raise ValueError("Unknown project ID")

    async def respond(call):
        try:
            value = await call()
            return JSONResponse(value)
        except (ValueError, KeyError, TypeError, RuntimeError) as error:
            return JSONResponse({"error": str(error)}, status_code=400)

    @mcp.custom_route("/api/v1/model", methods=["POST"])
    async def warmup(request):
        return await respond(lambda: asyncio.to_thread(engine.model.info, "__shared__"))

    @mcp.custom_route("/api/v1/stats", methods=["GET"])
    async def stats(request):
        async def call():
            path = request.query_params.get("project")
            project = canonical_project(path, absolute=True) if path else None
            return engine.state.snapshot(project)

        return await respond(call)

    @mcp.custom_route("/api/v1/index", methods=["POST"])
    async def index(request):
        async def call():
            data = await request.json()
            directory = data.pop("directory_path")
            return await asyncio.to_thread(engine.index, directory, **data)

        return await respond(call)

    @mcp.custom_route("/api/v1/search", methods=["POST"])
    async def search(request):
        async def call():
            data = await request.json()
            project = data.pop("project_path")
            query = data.pop("query")
            return await asyncio.to_thread(engine.search, project, query, **data)

        return await respond(call)

    @mcp.custom_route("/api/v1/jobs/{job_id}", methods=["GET", "DELETE"])
    async def job(request):
        async def call():
            project = request.query_params["project"]
            method = engine.cancel if request.method == "DELETE" else engine.job
            return method(project, request.path_params["job_id"])

        return await respond(call)

    @mcp.custom_route("/api/v1/health", methods=["GET"])
    async def health(request):
        return JSONResponse({"status": "ok", "daemon_id": engine.state.snapshot()["daemon_id"]})

    app = mcp.http_app(
        path="/mcp",
        stateless_http=True,
        allowed_hosts=[
            f"127.0.0.1:{engine.settings.port}",
            f"localhost:{engine.settings.port}",
            f"[::1]:{engine.settings.port}",
        ],
    )
    return LocalAuth(app, engine.settings, token)


def serve(settings):
    import uvicorn

    from .engine import Engine
    from .events import Publisher, ipc_address

    engine = Engine(settings)
    publisher = None
    try:
        publisher = Publisher(ipc_address(settings.root), engine.state.snapshot)
        engine.state.publish = publisher.publish
        app = create_app(engine, token_for(settings.root, create=True))
        uvicorn.run(app, host=settings.host, port=settings.port, workers=1)
    finally:
        if publisher:
            publisher.close()
        engine.close()
