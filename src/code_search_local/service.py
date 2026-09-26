"""Authenticated loopback HTTP MCP and administration API."""

import asyncio
import hmac
import json
import secrets
from pathlib import Path

from code_search_local import constants

from .config import canonical_project, loopback_hosts
from .storage import atomic_json


def token_for(root: Path, *, create=False):
    path = root / constants.PATH_AUTH_JSON
    if not path.exists():
        if not create:
            raise RuntimeError("Service is not configured; run code-search-local setup")
        atomic_json(
            path,
            {constants.KEY_TOKEN: secrets.token_urlsafe(constants.AUTH_TOKEN_BYTES)},
            mode=constants.PRIVATE_FILE_MODE,
        )
    return json.loads(path.read_text())[constants.KEY_TOKEN]


class LocalAuth:
    def __init__(self, app, settings, token):
        self.app, self.token = app, token
        self.hosts = set(loopback_hosts(settings.port))
        self.origins = {constants.HTTP_SCHEME + host for host in self.hosts}

    async def __call__(self, scope, receive, send):
        if scope[constants.KEY_TYPE] != constants.TRANSPORT_HTTP:
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse

        headers = {
            key.decode().lower(): value.decode() for key, value in scope[constants.KEY_HEADERS]
        }
        if headers.get(constants.KEY_HOST) not in self.hosts or (
            headers.get(constants.KEY_ORIGIN) and headers[constants.KEY_ORIGIN] not in self.origins
        ):
            return await JSONResponse(
                {constants.KEY_ERROR: "Invalid Host or Origin"},
                status_code=constants.HTTP_FORBIDDEN,
            )(scope, receive, send)
        expected = constants.HTTP_BEARER + self.token
        if not hmac.compare_digest(
            headers.get(constants.KEY_AUTHORIZATION_LOWERCASE, ""), expected
        ):
            return await JSONResponse(
                {constants.KEY_ERROR: constants.TOKEN_UNAUTHORIZED},
                status_code=constants.HTTP_UNAUTHORIZED,
            )(scope, receive, send)
        return await self.app(scope, receive, send)


def create_app(engine, token):
    from fastmcp import FastMCP
    from starlette.responses import JSONResponse

    mcp = FastMCP(
        constants.APPLICATION_NAME,
        instructions=(
            "Use these tools for local code indexing, semantic code search and index diagnostics. "
            "For requests such as 'Index code', 'Index codebase' or 'Update index', call "
            "index_directory for the user's target workspace with incremental=True by default. "
            "Use its returned job_id with get_index_job; report completion only after succeeded, "
            "and report failed/cancelled/interrupted outcomes accurately. Every project argument "
            "must be the absolute workspace root, not a source subdirectory or the service checkout. "
            "Use list_projects to discover registered roots when needed; never guess another "
            "project's path or IDs. For code questions use search_code, then inspect the returned "
            "source locations before explaining or editing code. Indexes and models are shared "
            "by the user service and survive client disconnects. Refresh with index_directory; "
            "use clear_index only for an explicit request to discard an index."
        ),
    )

    @mcp.tool(
        title="Index or update a codebase",
        annotations={
            constants.KEY_READ_ONLY_HINT: False,
            constants.KEY_DESTRUCTIVE_HINT: False,
            constants.KEY_IDEMPOTENT_HINT: False,
        },
    )
    async def index_directory(
        directory_path: str,
        incremental: bool = True,
        file_patterns: list[str] | None = None,
        wait: bool = False,
    ) -> dict:
        """Build or refresh the searchable index for one codebase.

        Call when the user says "Index code", "Index codebase", "Index this project",
        "Update index", "Refresh the index", or "Reindex". Also use when search reports
        a missing index or an incompatible model. Resolve the intended workspace root first.
        Keep incremental=True for ordinary updates; use False for an explicit full rebuild.
        Leave file_patterns unset unless the user requests a restricted set of files: these
        patterns define the whole indexed scope, so previously indexed files outside it are removed.
        This reads source files, updates the local index and enables configured change watching;
        it does not edit source. The shared service may download a missing model on first use.
        With wait=False, retain the returned job_id and poll get_index_job with a short delay
        until succeeded, failed, cancelled or interrupted. A queued/running response is not
        completion. Inspect error on failure; do not resubmit merely because a job is still running.

        Args:
            directory_path: Absolute existing project root, e.g. /home/me/code/api. Use the
                workspace root consistently for subsequent project_path arguments.
            incremental: True reuses unchanged embeddings and handles added/changed/deleted files.
                False explicitly rebuilds the complete index within the selected file scope.
            file_patterns: Optional shell globs matched against project-relative file paths,
                e.g. ["src/*.py", "tests/*.py"]. Omit/null indexes all supported non-ignored files.
            wait: False returns a durable job immediately; poll get_index_job. True waits for
                completion and is suitable for a small project when the client timeout permits.
        """
        return await asyncio.to_thread(
            engine.index,
            directory_path,
            wait=wait,
            incremental=incremental,
            file_patterns=file_patterns,
        )

    @mcp.tool(
        title="Check indexing job progress",
        annotations={constants.KEY_READ_ONLY_HINT: True, constants.KEY_OPEN_WORLD_HINT: False},
    )
    async def get_index_job(project_path: str, job_id: str) -> dict:
        """Check a particular indexing request without submitting another job.

        Call after index_directory returns queued/running, or when asked "Is indexing done?",
        "How far along is indexing?", or "Why did indexing fail?". Use the returned job_id
        with the same project root. If the ID is unknown, get_index_status lists this project's
        jobs. Poll with a short delay while queued/running. Stop on succeeded, failed, cancelled
        or interrupted; report files_processed and any error accurately. Only succeeded means
        the requested index was committed.

        Args:
            project_path: Absolute project root used for the indexing request.
            job_id: Exact job_id returned by index_directory or this project's status; never invent one.
        """
        return engine.job(project_path, job_id)

    @mcp.tool(
        title="Cancel an indexing job",
        annotations={
            constants.KEY_READ_ONLY_HINT: False,
            constants.KEY_DESTRUCTIVE_HINT: False,
            constants.KEY_IDEMPOTENT_HINT: True,
            constants.KEY_OPEN_WORLD_HINT: False,
        },
    )
    async def cancel_index_job(project_path: str, job_id: str) -> dict:
        """Request cancellation of one queued or running indexing job.

        Call for "Stop indexing", "Cancel the index update", or an explicit request to cancel
        a particular job. If no job ID is known, inspect get_index_status for the target project
        first. Cancellation is cooperative: follow get_index_job until terminal before claiming
        it stopped. A job that already succeeded remains succeeded. The last committed index
        and source files are preserved; this does not stop the shared service or other projects.

        Args:
            project_path: Absolute root of the project that owns the job.
            job_id: Exact queued/running job_id from index_directory or get_index_status.
        """
        return engine.cancel(project_path, job_id)

    @mcp.tool(title="Search code by meaning", annotations={constants.KEY_READ_ONLY_HINT: True})
    async def search_code(
        project_path: str,
        query: str,
        k: int = constants.DEFAULT_SEARCH_RESULTS,
        filters: dict[str, str] | None = None,
    ) -> dict:
        """Find relevant functions, classes and code passages in one indexed codebase.

        Call for "Search the code", "Find where authentication is implemented", "Where is this
        behavior handled?", or to locate code before explaining or changing it. Write a focused
        natural-language query, optionally including symbol names. Results include ranked chunks,
        source paths/line ranges and chunk_id; inspect those source locations before making claims
        or edits. Search reads the last committed index, so an in-progress update may not yet be
        reflected. If the project is unregistered, has no index or has a model mismatch, call
        index_directory and wait for success before retrying. For unexpected missing results,
        inspect get_index_status and the selected file scope instead of clearing the index.

        Args:
            project_path: Absolute root of the specific workspace to search; no cross-project search.
            query: Nonempty description of the behavior or symbol to find, e.g. "validate bearer token".
            k: Maximum number of ranked results, from 1 to 100; default 10.
            filters: Optional metadata field-to-shell-glob mapping; all entries must match.
                Example: {"file_path": "*/auth/*", "chunk_type": "function"}. Omit/null for no filtering.
        """
        return await asyncio.to_thread(engine.search, project_path, query, k=k, filters=filters)

    @mcp.tool(
        title="Show index and model statistics",
        annotations={constants.KEY_READ_ONLY_HINT: True, constants.KEY_OPEN_WORLD_HINT: False},
    )
    async def get_index_stats(project_path: str | None = None) -> dict:
        """Report index, cache, change-detection and shared model usage statistics.

        Call for "Show indexing stats", "How many files are indexed?", "When was it indexed?",
        "Are embeddings cached?", "Which model/GPU is used?", or "Were code changes detected?".
        Supply project_path for one workspace; omit it only for an all-project/service overview.
        Returns a snapshot of recorded counts, timestamps, cache/search activity, jobs and shared
        model/backend information. Reading stats does not index files or load a model. Distinguish
        recorded usage from an active model; use get_index_job to follow a specific running job.

        Args:
            project_path: Optional absolute registered project root. Omit/null for all projects;
                shared service/model statistics remain included with a project filter.
        """
        project = canonical_project(project_path, absolute=True) if project_path else None
        return engine.state.snapshot(project)

    @mcp.tool(
        title="Check a project's index status",
        annotations={constants.KEY_READ_ONLY_HINT: True, constants.KEY_OPEN_WORLD_HINT: False},
    )
    async def get_index_status(project_path: str) -> dict:
        """Inspect whether a project's index is ready and which indexing jobs it has.

        Call for "Is this codebase indexed?", "Is the index up to date?", "What's indexing?",
        or to find a job ID before checking/cancelling it. Inspect the committed generation,
        last-indexed time, recorded change counters and queued/running jobs. This reads saved
        state; it does not rescan disk or guarantee that every recent edit has been detected.
        Use index_directory when the user requests a fresh index, get_index_job for a specific
        job, and list_projects if this root is not registered.

        Args:
            project_path: Absolute root of the registered workspace whose index state is requested.
        """
        return engine.state.snapshot(canonical_project(project_path, absolute=True))

    @mcp.tool(
        title="Find code similar to a search result",
        annotations={constants.KEY_READ_ONLY_HINT: True, constants.KEY_OPEN_WORLD_HINT: False},
    )
    async def find_similar_code(
        project_path: str, chunk_id: str, k: int = constants.DEFAULT_SIMILAR_RESULTS
    ) -> dict:
        """Find code passages similar to an existing indexed chunk in the same project.

        Call for "Find similar code", "Where else is this pattern used?", or "Find related
        implementations" after identifying a reference chunk with search_code. Pass its exact
        chunk_id; a symbol name or file path alone is not a chunk ID. Results exclude the reference
        chunk and are ranked by semantic similarity, not proof of identical behavior. Inspect
        returned source before calling code a duplicate. If an update invalidated the ID, search
        again to obtain a current one. Use search_code for a natural-language query without a chunk.

        Args:
            project_path: Absolute root of the project that produced the reference search result.
            chunk_id: Exact chunk_id from a current search_code/find_similar_code result in this project.
            k: Maximum number of other similar chunks, from 1 to 100; default 5.
        """
        return await asyncio.to_thread(engine.similar, project_path, chunk_id, k)

    @mcp.tool(
        title="Clear a project's search index",
        annotations={
            constants.KEY_READ_ONLY_HINT: False,
            constants.KEY_DESTRUCTIVE_HINT: True,
            constants.KEY_OPEN_WORLD_HINT: False,
        },
    )
    async def clear_index(project_path: str) -> dict:
        """Discard one project's searchable index and pause automatic indexing for that project.

        Call only for an explicit request such as "Clear this project's index" or "Delete the
        code index". For "Update index", "Refresh" or "Rebuild", use index_directory instead.
        Check get_index_status first: the project must be idle. Wait for active jobs, or cancel
        them when requested and wait until terminal, before clearing. This empties the committed
        searchable index and disables its watcher until index_directory is called again. Source
        files, shared models, other projects and the registered project record are preserved.
        This does not uninstall the service or securely erase all stored history/cache files.

        Args:
            project_path: Absolute root of the single registered project whose index the user wants cleared.
        """
        return await asyncio.to_thread(engine.clear, project_path)

    @mcp.tool(
        title="List indexed projects",
        annotations={constants.KEY_READ_ONLY_HINT: True, constants.KEY_OPEN_WORLD_HINT: False},
    )
    async def list_projects() -> dict:
        """Discover project roots registered with this shared service.

        Call for "List indexed projects", "Which codebases are registered?", "What repositories
        can I search?", or when the target root is unclear. Returns a mapping from absolute roots
        to recorded index information. Choose the root matching the user's intended workspace
        for subsequent calls; do not substitute a similarly named project. Registration alone
        does not mean indexing succeeded: inspect get_index_status for readiness. This does not
        scan the filesystem for new repositories; register a new workspace with index_directory.
        """
        return engine.state.snapshot()[constants.KEY_PROJECTS]

    @mcp.resource(constants.STATS_RESOURCE_URI)
    async def stats_resource() -> str:
        return json.dumps(engine.state.snapshot())

    @mcp.resource(constants.PROJECT_STATS_RESOURCE_URI)
    async def project_resource(project_id: str) -> str:
        from .storage import project_id as identify

        for project in engine.state.snapshot()[constants.KEY_PROJECTS]:
            if identify(project) == project_id:
                return json.dumps(engine.state.snapshot(project))
        raise ValueError("Unknown project ID")

    async def respond(call):
        try:
            value = await call()
            return JSONResponse(value)
        except (ValueError, KeyError, TypeError, RuntimeError) as error:
            return JSONResponse(
                {constants.KEY_ERROR: str(error)}, status_code=constants.HTTP_BAD_REQUEST
            )

    @mcp.custom_route(constants.MODEL_ENDPOINT, methods=[constants.HTTP_POST])
    async def warmup(request):
        return await respond(
            lambda: asyncio.to_thread(engine.model.info, constants.SHARED_MODEL_OWNER)
        )

    @mcp.custom_route(constants.STATS_ENDPOINT, methods=[constants.HTTP_GET])
    async def stats(request):
        async def call():
            path = request.query_params.get(constants.KEY_PROJECT)
            project = canonical_project(path, absolute=True) if path else None
            return engine.state.snapshot(project)

        return await respond(call)

    @mcp.custom_route(constants.INDEX_ENDPOINT, methods=[constants.HTTP_POST])
    async def index(request):
        async def call():
            data = await request.json()
            directory = data.pop(constants.KEY_DIRECTORY_PATH)
            return await asyncio.to_thread(engine.index, directory, **data)

        return await respond(call)

    @mcp.custom_route(constants.SEARCH_ENDPOINT, methods=[constants.HTTP_POST])
    async def search(request):
        async def call():
            data = await request.json()
            project = data.pop(constants.KEY_PROJECT_PATH)
            query = data.pop(constants.KEY_QUERY)
            return await asyncio.to_thread(engine.search, project, query, **data)

        return await respond(call)

    @mcp.custom_route(
        constants.JOB_ENDPOINT_TEMPLATE, methods=[constants.HTTP_GET, constants.HTTP_DELETE]
    )
    async def job(request):
        async def call():
            project = request.query_params[constants.KEY_PROJECT]
            method = engine.cancel if request.method == constants.HTTP_DELETE else engine.job
            return method(project, request.path_params[constants.KEY_JOB_ID])

        return await respond(call)

    @mcp.custom_route(constants.HEALTH_ENDPOINT, methods=[constants.HTTP_GET])
    async def health(request):
        return JSONResponse(
            {
                constants.KEY_STATUS: constants.STATUS_OK,
                constants.KEY_DAEMON_ID: engine.state.snapshot()[constants.KEY_DAEMON_ID],
            }
        )

    app = mcp.http_app(
        path=constants.MCP_ENDPOINT,
        stateless_http=True,
        allowed_hosts=loopback_hosts(engine.settings.port),
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
        uvicorn.run(app, host=settings.host, port=settings.port, workers=constants.DAEMON_WORKERS)
    finally:
        if publisher:
            publisher.close()
        engine.close()
