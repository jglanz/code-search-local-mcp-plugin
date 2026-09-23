"""Click entry points, intentionally lightweight until a server command is invoked."""

import asyncio
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import click

from . import __version__
from .config import BACKENDS, Settings, canonical_project


def output(value):
    click.echo(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))


@click.group()
@click.version_option(__version__)
def main():
    """Local semantic search with a shared CPU, CUDA or ROCm service."""


def backend_options(command):
    command = click.option("--gpu-index", type=click.IntRange(min=0), default=None)(command)
    command = click.option("--cpu-fallback/--no-cpu-fallback", default=None)(command)
    return click.option("--backend", type=click.Choice(BACKENDS), default=None)(command)


def settings_options(command):
    command = backend_options(command)
    command = click.option("--port", type=click.IntRange(1, 65535), default=None)(command)
    command = click.option("--storage", type=click.Path(path_type=Path), default=None)(command)
    command = click.option("--model", default=None)(command)
    command = click.option("--revision", default=None)(command)
    return command


def load_settings(**kwargs):
    if kwargs.get("storage") is not None:
        kwargs["storage"] = str(kwargs["storage"])
    try:
        return Settings.load(**kwargs)
    except (ValueError, TypeError) as error:
        raise click.ClickException(str(error)) from error


@main.command()
@settings_options
@click.option("--watch/--no-watch", default=None)
@click.option("--offline/--online", default=None)
def serve(**kwargs):
    """Run the shared HTTP service in the foreground (normally managed by systemd)."""
    from .service import serve as run_service

    try:
        run_service(load_settings(**kwargs))
    except (ValueError, RuntimeError) as error:
        raise click.ClickException(str(error)) from error


@main.command()
@settings_options
@click.option("--client", type=click.Choice(["claude", "codex", "both"]), required=True)
@click.option(
    "--package-source",
    type=click.Path(exists=True, dir_okay=False),
    help="Install a locally built wheel instead of the published release.",
)
def setup(client, package_source, **kwargs):
    """Install a persistent backend runtime, user service and HTTP MCP connection."""
    import subprocess

    from .install import setup as install

    try:
        output(install(load_settings(**kwargs), client=client, package_source=package_source))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise click.ClickException(str(error)) from error


@main.group()
def service():
    """Manage the user's shared service. Uninstall preserves indexes and model files."""


for _action in ("start", "stop", "restart", "status", "uninstall"):

    def _make_action(action):
        @service.command(name=action)
        def command():
            import subprocess

            from .install import service_action

            try:
                service_action(action)
            except (OSError, subprocess.CalledProcessError) as error:
                raise click.ClickException(str(error)) from error

        return command

    _make_action(_action)


@main.command()
@click.option("--project", type=click.Path(path_type=Path))
@click.option("--live", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
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
    "project", type=click.Path(exists=True, file_okay=False, path_type=Path), default="."
)
@click.option("--wait/--no-wait", default=True)
@click.option("--incremental/--rebuild", default=True)
@click.option("--pattern", multiple=True)
def index(project, wait, incremental, pattern):
    """Request indexing through the shared service."""
    request(
        "POST",
        "/api/v1/index",
        data={
            "directory_path": canonical_project(project),
            "wait": wait,
            "incremental": incremental,
            "file_patterns": list(pattern) or None,
        },
    )


@main.command()
@click.argument("query")
@click.option("--project", type=click.Path(path_type=Path), default=".")
@click.option("-k", type=click.IntRange(1, 100), default=10)
def search(query, project, k):
    """Search one project's committed index."""
    request(
        "POST",
        "/api/v1/search",
        data={"project_path": canonical_project(project), "query": query, "k": k},
    )


@main.command()
@click.argument("job_id")
@click.option("--project", type=click.Path(path_type=Path), default=".")
@click.option("--cancel", is_flag=True)
def job(job_id, project, cancel):
    """Inspect or cancel a durable indexing job."""
    request(
        "DELETE" if cancel else "GET",
        f"/api/v1/jobs/{job_id}",
        params={"project": canonical_project(project)},
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
    request("POST", "/api/v1/model")


@main.command()
@settings_options
@click.option("--settings-file", type=click.Path(exists=True, path_type=Path), hidden=True)
@click.option(
    "--inference",
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
    result = {"version": __version__, "settings": asdict(settings)}
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
                vector = model.encode(["def validate_backend(): return True"], "document")
                result.update(model=model.info, shape=list(vector.shape), counters=counters)
            finally:
                model.close()
        except Exception as error:
            raise click.ClickException(str(error)) from error
    output(result)


if __name__ == "__main__":
    main()
