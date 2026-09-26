"""Click entry points, intentionally lightweight until a server command is invoked."""

import asyncio
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import click

from code_search_local import constants

from . import __version__
from .config import BACKENDS, Settings, canonical_project


def output(value):
    click.echo(json.dumps(value, indent=constants.JSON_INDENT, sort_keys=True, allow_nan=False))


@click.group()
@click.version_option(__version__)
def main():
    """Local semantic search with a shared CPU, CUDA or ROCm service."""


def configuration_option(command, option, *, help, **parameters):
    """Apply an optional override without discarding saved configuration by default."""
    return click.option(option, default=None, help=help, **parameters)(command)


def backend_options(command):
    command = configuration_option(
        command,
        constants.OPTION_GPU_INDEX,
        type=click.IntRange(min=0),
        help="Override the configured zero-based CUDA or ROCm device index.",
    )
    command = configuration_option(
        command,
        constants.OPTION_CPU_FALLBACK_NO_CPU_FALLBACK,
        help="Allow or forbid CPU fallback if the accelerator is unavailable or fails. Unless configured otherwise, enabled for auto and disabled for explicit backends.",
    )
    return configuration_option(
        command,
        constants.OPTION_BACKEND,
        type=click.Choice(BACKENDS),
        help="Override the configured model backend; auto detects available acceleration.",
    )


def settings_options(command):
    command = backend_options(command)
    command = configuration_option(
        command,
        constants.OPTION_PORT,
        type=click.IntRange(constants.MIN_SERVICE_PORT, constants.MAX_SERVICE_PORT),
        help="Override the configured loopback HTTP service port.",
    )
    command = configuration_option(
        command,
        constants.OPTION_STORAGE,
        type=click.Path(path_type=Path),
        help="Override the directory for indexes, model files, statistics and service state.",
    )
    command = configuration_option(
        command,
        constants.OPTION_MODEL,
        help="Override the Hugging Face embedding model repository ID (for example, google/embeddinggemma-300m).",
    )
    command = configuration_option(
        command,
        constants.OPTION_REVISION,
        help="Override the model revision with a Hugging Face branch, tag or commit ID.",
    )
    return command


def load_settings(**kwargs):
    if kwargs.get(constants.KEY_STORAGE) is not None:
        kwargs[constants.KEY_STORAGE] = str(kwargs[constants.KEY_STORAGE])
    try:
        return Settings.load(**kwargs)
    except (ValueError, TypeError) as error:
        raise click.ClickException(str(error)) from error


@main.command()
@settings_options
@click.option(
    constants.OPTION_WATCH_NO_WATCH,
    default=None,
    help="Enable or disable automatic reindexing when project files change; defaults to configuration.",
)
@click.option(
    constants.OPTION_OFFLINE_ONLINE,
    default=None,
    help="Require cached model files or allow missing model downloads; defaults to configuration.",
)
def serve(**kwargs):
    """Run the shared HTTP service in the foreground (normally managed by systemd)."""
    from .service import serve as run_service

    try:
        run_service(load_settings(**kwargs))
    except (ValueError, RuntimeError) as error:
        raise click.ClickException(str(error)) from error


@main.command()
@settings_options
@click.option(
    constants.OPTION_CLIENT,
    type=click.Choice(
        [constants.HARNESS_CLAUDE, constants.HARNESS_CODEX, constants.LEGACY_HARNESS_BOTH]
    ),
    hidden=True,
    help="Legacy harness selection; use --agent-harness instead. Cannot combine the two options.",
)
@click.option(
    constants.OPTION_AGENT_HARNESS,
    multiple=True,
    type=click.Choice(
        [
            constants.HARNESS_NONE,
            constants.HARNESS_CODEX,
            constants.HARNESS_CLAUDE,
            constants.HARNESS_OPENCODE,
            constants.HARNESS_ALL,
        ]
    ),
    help="Replace this tool's registrations in selected harnesses; repeat for several or use all. "
    "Default: none (service only). Cannot combine none with another selection.",
)
@click.option(
    constants.OPTION_MARKETPLACE,
    is_flag=True,
    help="Keep the calling marketplace plugin and remove the service when it is uninstalled.",
)
@click.option(
    constants.OPTION_PACKAGE_SOURCE,
    type=click.Path(exists=True, dir_okay=False),
    help="Install a locally built wheel instead of the published release; cannot combine with --source.",
)
@click.option(
    constants.OPTION_SOURCE,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Run the service from this checkout and its .venvs/<backend> editable environment; "
    "cannot combine with --package-source.",
)
@click.option(
    constants.OPTION_STARTUP_TIMEOUT,
    type=click.IntRange(min=1),
    default=constants.SERVICE_STARTUP_TIMEOUT_SECONDS,
    show_default=True,
    help="Seconds to wait for the started service to become healthy before registering harnesses; "
    "allow longer when restoring large indexes.",
)
def setup(client, agent_harness, marketplace, package_source, source, startup_timeout, **kwargs):
    """Install a user service and client connections from a release or source checkout."""
    import subprocess

    from .install import setup as install

    if source is not None and package_source is not None:
        raise click.UsageError("--source cannot be used with --package-source")
    from .harnesses import selection

    if client is not None and agent_harness:
        raise click.UsageError("--client cannot be combined with --agent-harness")
    try:
        if client is not None:
            agent_harness = (
                (constants.HARNESS_CLAUDE, constants.HARNESS_CODEX)
                if client == constants.LEGACY_HARNESS_BOTH
                else (client,)
            )
        agent_harness = selection(agent_harness)
    except ValueError as error:
        raise click.UsageError(str(error)) from error
    try:
        output(
            install(
                load_settings(**kwargs),
                agent_harness=agent_harness,
                marketplace=marketplace,
                package_source=package_source,
                source=source,
                startup_timeout=startup_timeout,
            )
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise click.ClickException(str(error)) from error


@main.group()
def service():
    """Manage the user's shared service. Uninstall preserves indexes and model files."""


for _action in (
    constants.COMMAND_START,
    constants.COMMAND_STOP,
    constants.COMMAND_RESTART,
    constants.KEY_STATUS,
    constants.COMMAND_UNINSTALL,
):

    def _make_action(action):
        @service.command(name=action)
        def command():
            import subprocess

            from .install import service_action

            try:
                service_action(action)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                raise click.ClickException(str(error)) from error

        return command

    _make_action(_action)


@main.command()
def uninstall():
    """Stop/remove the user service and unregister Code Search Local from agent harnesses."""
    import subprocess

    from .lifecycle import uninstall as remove

    try:
        output(remove())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise click.ClickException(str(error)) from error


@main.command(hidden=True)
def marketplace_check():
    """Reconcile native plugin removal (invoked by the installed systemd watcher)."""
    from .lifecycle import marketplace_check as check

    output(check())


@main.command()
@click.option(
    constants.OPTION_PROJECT,
    type=click.Path(path_type=Path),
    help="Limit statistics to this relative or absolute project root; omit for all projects.",
)
@click.option(
    constants.OPTION_LIVE,
    is_flag=True,
    help="Show a full-screen TUI updated through local pub-sub events; cannot combine with --json.",
)
@click.option(
    constants.OPTION_JSON,
    constants.CLI_DESTINATION_JSON,
    is_flag=True,
    help="Write the statistics snapshot as JSON to stdout instead of a TUI report; cannot combine with --live.",
)
def stats(project, live, as_json):
    """Report all projects, or one canonical project root; --live follows IPC events."""
    if live and as_json:
        raise click.UsageError("--json cannot be used with --live")
    from .client import Client
    from .storage import offline_stats

    settings = load_settings()
    project = canonical_project(project) if project else None
    client = Client(settings)

    async def fetch():
        try:
            return await client.stats(project)
        except OSError:
            return offline_stats(settings.root, project)

    try:
        snapshot = asyncio.run(fetch())
        if as_json:
            output(snapshot)
        else:
            from .tui import StatsApp

            subscriber = None
            if live:
                from .events import Subscriber, ipc_address

                subscriber = Subscriber(ipc_address(settings.root), fetch)
            StatsApp(snapshot, subscriber).run(inline=not live, inline_no_clear=not live)
    except (OSError, KeyError, RuntimeError, sqlite3.Error) as error:
        raise click.ClickException(str(error)) from error


@main.command()
@click.argument(
    constants.KEY_PROJECT,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=constants.KEY_PROJECT_ROOT,
)
@click.option(
    constants.OPTION_WAIT_NO_WAIT,
    default=True,
    show_default=True,
    help="Wait for indexing to finish, or return the job immediately with --no-wait.",
)
@click.option(
    constants.OPTION_INCREMENTAL_REBUILD,
    default=True,
    show_default=True,
    help="Reuse unchanged indexed files, or reparse all matching files with --rebuild. "
    "Cached embeddings may still be reused.",
)
@click.option(
    constants.OPTION_PATTERN,
    multiple=True,
    help="Include files matching this project-relative glob (for example, '*.py'); repeat for alternatives. "
    "Omit to include all supported files.",
)
def index(project, wait, incremental, pattern):
    """Request indexing through the shared service."""
    request(
        constants.HTTP_POST,
        constants.INDEX_ENDPOINT,
        data={
            constants.KEY_DIRECTORY_PATH: canonical_project(project),
            constants.KEY_WAIT: wait,
            constants.KEY_INCREMENTAL: incremental,
            constants.KEY_FILE_PATTERNS: list(pattern) or None,
        },
    )


@main.command()
@click.argument(constants.KEY_QUERY)
@click.option(
    constants.OPTION_PROJECT,
    type=click.Path(path_type=Path),
    default=constants.KEY_PROJECT_ROOT,
    show_default=True,
    help="Search the index for this relative or absolute project root; defaults to the current directory.",
)
@click.option(
    constants.SHORT_OPTION_K,
    constants.OPTION_MAX_RESULTS,
    constants.KEY_K,
    type=click.IntRange(1, constants.MAX_SEARCH_RESULTS),
    default=constants.DEFAULT_SEARCH_RESULTS,
    show_default=True,
    help="Maximum number of matching code chunks to return.",
)
def search(query, project, k):
    """Search one project's committed index."""
    request(
        constants.HTTP_POST,
        constants.SEARCH_ENDPOINT,
        data={
            constants.KEY_PROJECT_PATH: canonical_project(project),
            constants.KEY_QUERY: query,
            constants.KEY_K: k,
        },
    )


@main.command()
@click.argument(constants.KEY_JOB_ID)
@click.option(
    constants.OPTION_PROJECT,
    type=click.Path(path_type=Path),
    default=constants.KEY_PROJECT_ROOT,
    show_default=True,
    help="Relative or absolute root of the project that owns the job; defaults to the current directory.",
)
@click.option(
    constants.OPTION_CANCEL,
    is_flag=True,
    help="Request cancellation of this indexing job instead of inspecting it.",
)
def job(job_id, project, cancel):
    """Inspect or cancel a durable indexing job."""
    request(
        constants.HTTP_DELETE if cancel else constants.HTTP_GET,
        constants.JOB_ENDPOINT_TEMPLATE.format(job_id=job_id),
        params={constants.KEY_PROJECT: canonical_project(project)},
    )


def request(method, path, **kwargs):
    from .client import Client

    try:
        output(asyncio.run(Client(load_settings()).request(method, path, **kwargs)))
    except (OSError, ValueError, RuntimeError) as error:
        raise click.ClickException(str(error)) from error


@main.command()
def warmup():
    """Acquire and load the model in the shared daemon."""
    request(constants.HTTP_POST, constants.MODEL_ENDPOINT)


@main.command()
@settings_options
@click.option(
    constants.OPTION_SETTINGS_FILE,
    type=click.Path(exists=True, path_type=Path),
    hidden=True,
    help="Load settings from this JSON file instead of saved configuration, environment variables or option overrides.",
)
@click.option(
    constants.OPTION_INFERENCE,
    is_flag=True,
    help="Load the configured model and execute a real embedding on the selected device.",
)
def doctor(settings_file, inference, **kwargs):
    """Show configuration and optionally validate backend inference."""
    settings = (
        Settings(**json.loads(settings_file.read_text()))
        if settings_file
        else load_settings(**kwargs)
    )
    result = {constants.KEY_VERSION: __version__, constants.KEY_SETTINGS: asdict(settings)}
    if inference:
        from .chunking.available_languages import prefetch_languages
        from .models import SentenceModel

        try:
            prefetch_languages()
            counters = {}

            def report(**values):
                for key, value in values.items():
                    counters[key] = counters.get(key, 0) + value

            model = SentenceModel(settings, report)
            try:
                vector = model.encode(
                    ["def validate_backend(): return True"], constants.KEY_DOCUMENT
                )
                result.update(model=model.info, shape=list(vector.shape), counters=counters)
            finally:
                model.close()
        except Exception as error:
            raise click.ClickException(str(error)) from error
    output(result)


if __name__ == "__main__":
    main()
