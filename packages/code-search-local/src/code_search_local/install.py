"""Persistent backend environments and user-scoped service/client registration."""

import asyncio
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
import tomllib
from dataclasses import asdict, replace
from importlib.metadata import distribution
from pathlib import Path

import click

from code_search_local import constants

from . import __version__
from .config import config_path
from .service import token_for
from .storage import ServiceLock, atomic_json, atomic_text

SERVICE = "code-search-local.service"
STARTUP_TIMEOUT = constants.SERVICE_STARTUP_TIMEOUT_SECONDS


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def probe_service(settings, timeout=constants.HEALTH_PROBE_TIMEOUT_SECONDS):
    """Bound readiness probes independently of long-running indexing requests."""
    from .client import Client

    async def probe():
        return await asyncio.wait_for(
            Client(settings).request(constants.HTTP_GET, constants.HEALTH_ENDPOINT), timeout=timeout
        )

    health = asyncio.run(probe())
    if health.get(constants.KEY_STATUS) != constants.STATUS_OK:
        raise RuntimeError(f"Unexpected service health response: {health!r}")
    return health


def service_state():
    result = run(
        [
            constants.COMMAND_SYSTEMCTL,
            constants.OPTION_USER,
            constants.COMMAND_SHOW,
            SERVICE,
            constants.OPTION_PROPERTY_ACTIVE_STATE_SUB_STATE_EXEC_MAIN_STATUS_NRESTARTS,
        ],
        capture_output=True,
        text=True,
        timeout=constants.SYSTEM_COMMAND_TIMEOUT_SECONDS,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def startup_error(reason, last_error):
    message = (
        f"{reason}. Harness registrations were not updated. "
        f"Last health check: {last_error}. "
        f"Inspect journalctl --user -u {SERVICE}; rerun setup to finish registration."
    )
    try:
        journal = run(
            [
                constants.COMMAND_JOURNALCTL,
                constants.OPTION_USER,
                constants.SHORT_OPTION_U,
                SERVICE,
                constants.SHORT_OPTION_N,
                constants.STARTUP_JOURNAL_LINE_COUNT,
                constants.OPTION_NO_PAGER,
                constants.OPTION_OUTPUT_CAT,
            ],
            capture_output=True,
            text=True,
            timeout=constants.SYSTEM_COMMAND_TIMEOUT_SECONDS,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        journal = ""
    if journal:
        message += "\nRecent service log:\n" + journal
    return RuntimeError(message)


def wait_for_service(settings, timeout=STARTUP_TIMEOUT):
    started = time.monotonic()
    deadline = started + timeout
    next_progress = started
    last_error = "not yet listening"
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise startup_error(
                f"Service did not become healthy within {timeout:g}s; "
                "use --startup-timeout for a longer startup budget",
                last_error,
            ) from None
        try:
            return probe_service(
                settings, timeout=min(constants.HEALTH_PROBE_TIMEOUT_SECONDS, remaining)
            )
        except (OSError, RuntimeError, TimeoutError) as error:
            last_error = str(error) or "health request timed out"
        state = service_state()
        status = "/".join(
            (
                state.get(constants.KEY_ACTIVE_STATE, constants.STATUS_UNKNOWN),
                state.get(constants.KEY_SUB_STATE, constants.STATUS_UNKNOWN),
            )
        )
        if (
            state.get(constants.KEY_ACTIVE_STATE)
            in {constants.STATUS_FAILED, constants.STATUS_INACTIVE}
            or state.get(constants.KEY_SUB_STATE) == constants.STATUS_AUTO_RESTART
        ):
            raise startup_error(
                f"Service exited during startup ({status}, exit status {state.get(constants.KEY_EXEC_MAIN_STATUS, constants.STATUS_UNKNOWN)})",
                last_error,
            ) from None
        now = time.monotonic()
        if now >= next_progress:
            click.echo(
                f"Waiting for {SERVICE} at {settings.url}: {now - started:.0f}s/{timeout:g}s "
                f"({status}; restoring existing indexes may take time).",
                err=True,
            )
            next_progress = now + constants.STARTUP_PROGRESS_INTERVAL_SECONDS
        time.sleep(
            min(constants.STARTUP_POLL_INTERVAL_SECONDS, max(0, deadline - time.monotonic()))
        )


def uv_executable():
    from uv import find_uv_bin

    return find_uv_bin()


def select_runtime(backend):
    if backend != constants.BACKEND_AUTO:
        return constants.BACKEND_CPU if backend == constants.BACKEND_MPS else backend
    if platform.system() == constants.PLATFORM_MACOS:
        return constants.BACKEND_CPU
    if shutil.which(constants.COMMAND_NVIDIA_SMI):
        result = subprocess.run(
            [constants.COMMAND_NVIDIA_SMI, constants.SHORT_OPTION_L], capture_output=True, text=True
        )
        if result.returncode == 0 and constants.NVIDIA_GPU_MARKER in result.stdout:
            return constants.BACKEND_CUDA
    if any(
        path.read_text().strip() == constants.AMD_PCI_VENDOR_ID
        for path in Path(constants.PATH_SYS_CLASS_DRM).glob(constants.PATH_CARD_DEVICE_VENDOR)
    ):
        return constants.BACKEND_ROCM
    return constants.BACKEND_CPU


def unit_path():
    base = Path(os.environ.get(constants.ENV_XDG_CONFIG_HOME, Path.home() / constants.PATH_CONFIG))
    return base / constants.SYSTEMD_DIRECTORY / constants.USER_SCOPE / SERVICE


def systemd_quote(value, *, expand_dollars=True):
    # Only ExecStart expands dollars; directives such as WorkingDirectory do not.
    value = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if expand_dollars:
        value = value.replace("$", "$$")
    return '"' + value + '"'


def installer_environment():
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in (
            constants.ENV_UV_PROJECT_ENVIRONMENT,
            constants.ENV_VIRTUAL_ENV,
            constants.ENV_PYTHONPATH,
        )
    }
    env[constants.ENV_PYTHONNOUSERSITE] = constants.ENV_ENABLED
    return env


def source_checkout(path):
    root = Path(path).expanduser().resolve()
    if "\n" in str(root) or "\r" in str(root):
        raise ValueError("Source checkout paths cannot contain line breaks")
    try:
        metadata = tomllib.loads((root / constants.PATH_PYPROJECT_TOML).read_text())
        valid = (
            metadata.get(constants.KEY_PROJECT, {}).get(constants.KEY_NAME)
            == constants.APPLICATION_NAME
            and (root / constants.PATH_SRC_CODE_SEARCH_LOCAL_INIT_PY).is_file()
            and (root / constants.PATH_UV_LOCK).is_file()
        )
    except (OSError, ValueError):
        valid = False
    if not valid:
        raise ValueError(f"Not a Code Search Local source checkout: {root}")
    return root


def install_source_runtime(source, backend):
    """Sync the live checkout using the backend environment declared in pyproject."""
    metadata = tomllib.loads((source / constants.PATH_PYPROJECT_TOML).read_text())
    try:
        environments = metadata[constants.KEY_TOOL][constants.KEY_HATCH][constants.KEY_ENVS]
        relative = environments[backend].get(
            constants.KEY_PATH, environments[constants.KEY_DEFAULT][constants.KEY_PATH]
        )
    except KeyError:
        raise ValueError(f"Checkout lacks the Hatch {backend} environment configuration") from None
    venv = source / relative
    env = installer_environment()
    env[constants.ENV_UV_PROJECT_ENVIRONMENT] = str(venv)
    run(
        [
            uv_executable(),
            constants.COMMAND_SYNC,
            constants.OPTION_PROJECT,
            source,
            constants.OPTION_LOCKED,
            constants.OPTION_EXTRA,
            constants.SERVER_EXTRA,
            constants.OPTION_EXTRA,
            backend,
            constants.OPTION_PYTHON,
            constants.RUNTIME_PYTHON_VERSION,
            constants.OPTION_REINSTALL_PACKAGE,
            constants.APPLICATION_NAME,
        ],
        env=env,
    )
    return venv / constants.PATH_BIN_PYTHON


def runtime_identity(package_source=None):
    resources = distribution(constants.APPLICATION_NAME).locate_file(
        constants.PATH_CODE_SEARCH_LOCAL_RUNTIME
    )
    identity = hashlib.sha256((resources / constants.PATH_UV_LOCK).read_bytes())
    if package_source:
        identity.update(Path(package_source).read_bytes())
    return constants.RUNTIME_ID_TEMPLATE.format(
        version=__version__, digest=identity.hexdigest()[: constants.RUNTIME_ID_DIGEST_CHARACTERS]
    )


def install_runtime(settings, backend, package_source=None):
    # Hatch installs forced-included resources in site-packages, including for editable installs.
    resources = distribution(constants.APPLICATION_NAME).locate_file(
        constants.PATH_CODE_SEARCH_LOCAL_RUNTIME
    )
    identity = runtime_identity(package_source)
    root = (
        settings.root
        / constants.RUNTIMES_DIRECTORY
        / constants.RUNTIME_DIRECTORY_TEMPLATE.format(
            version=__version__, backend=backend, digest=identity.split("-")[-1]
        )
    )
    python = root / constants.PATH_VENV / constants.BIN_DIRECTORY / constants.KEY_PYTHON
    if (root / constants.PATH_INSTALLED_JSON).exists() and python.exists():
        return python
    root.mkdir(parents=True, exist_ok=True)
    for name in (constants.PATH_PYPROJECT_TOML, constants.PATH_UV_LOCK):
        (root / name).write_bytes((resources / name).read_bytes())
    (root / constants.PATH_README_MD).write_text("Managed code-search-local runtime.\n")
    uv = uv_executable()
    env = installer_environment()
    run(
        [
            uv,
            constants.COMMAND_SYNC,
            constants.OPTION_PROJECT,
            root,
            constants.OPTION_LOCKED,
            constants.OPTION_NO_DEV,
            constants.OPTION_NO_INSTALL_PROJECT,
            constants.OPTION_EXTRA,
            constants.SERVER_EXTRA,
            constants.OPTION_EXTRA,
            backend,
            constants.OPTION_PYTHON,
            constants.RUNTIME_PYTHON_VERSION,
        ],
        env=env,
    )
    source = (
        str(Path(package_source).resolve())
        if package_source
        else constants.PACKAGE_REQUIREMENT_TEMPLATE.format(version=__version__)
    )
    run(
        [
            uv,
            constants.COMMAND_PIP,
            constants.COMMAND_INSTALL,
            constants.OPTION_PYTHON,
            python,
            constants.OPTION_NO_DEPS,
            source,
        ],
        env=env,
    )
    atomic_json(
        root / constants.PATH_INSTALLED_JSON,
        {constants.KEY_VERSION: __version__, constants.KEY_BACKEND: backend},
    )
    return python


def register_clients(settings, selected, *, marketplace=False):
    from .harnesses import register, selection, targets

    if isinstance(selected, str):
        selected = (
            (constants.HARNESS_CLAUDE, constants.HARNESS_CODEX)
            if selected == constants.LEGACY_HARNESS_BOTH
            else (selected,)
        )
    register(settings, targets(selection(selected)), marketplace=marketplace)


def setup(
    settings,
    *,
    agent_harness=(),
    client=None,
    package_source=None,
    source=None,
    marketplace=False,
    startup_timeout=STARTUP_TIMEOUT,
):
    from .harnesses import plugins, read_document, selection, targets
    from .lifecycle import marketplace_entries

    if startup_timeout <= 0:
        raise ValueError("startup_timeout must be positive")
    if client is not None:
        if agent_harness:
            raise ValueError("--client cannot be combined with --agent-harness")
        agent_harness = (
            (constants.HARNESS_CLAUDE, constants.HARNESS_CODEX)
            if client == constants.LEGACY_HARNESS_BOTH
            else (client,)
        )
    agent_harness = selection(agent_harness)
    selected = targets(agent_harness)
    for target in selected:
        for path in target[constants.KEY_CONFIGS]:
            read_document(path)
        plugins(target)
    entries = marketplace_entries(selected) if marketplace else []
    if source is not None:
        if package_source is not None:
            raise ValueError("--source cannot be used with --package-source")
        source = source_checkout(source)
    lock = ServiceLock(config_path().parent, constants.PATH_INSTALL_LOCK)
    try:
        return _setup(
            settings,
            agent_harness=agent_harness,
            selected=selected,
            entries=entries,
            package_source=package_source,
            source=source,
            marketplace=marketplace,
            startup_timeout=startup_timeout,
        )
    finally:
        lock.close()


def _setup(
    settings,
    *,
    agent_harness,
    selected,
    entries,
    package_source=None,
    source=None,
    marketplace=False,
    startup_timeout=STARTUP_TIMEOUT,
):
    from .lifecycle import record_installation, remove_guard

    if platform.system() != constants.PLATFORM_LINUX:
        raise RuntimeError(
            "User systemd setup currently requires Linux; use serve on other platforms"
        )
    preferred = select_runtime(settings.backend)
    candidates = [preferred]
    if settings.backend == constants.BACKEND_AUTO:
        if preferred == constants.BACKEND_CUDA and any(
            path.read_text().strip() == constants.AMD_PCI_VENDOR_ID
            for path in Path(constants.PATH_SYS_CLASS_DRM).glob(constants.PATH_CARD_DEVICE_VENDOR)
        ):
            candidates.append(constants.BACKEND_ROCM)
        if preferred != constants.BACKEND_CPU and settings.allow_fallback:
            candidates.append(constants.BACKEND_CPU)
    choice_path = settings.root / constants.PATH_RUNTIME_CHOICE_JSON
    identity = (
        constants.SOURCE_IDENTITY_PREFIX
        + str(source)
        + ":"
        + hashlib.sha256(
            (source / constants.PATH_PYPROJECT_TOML).read_bytes()
            + (source / constants.PATH_UV_LOCK).read_bytes()
        ).hexdigest()
        if source is not None
        else runtime_identity(package_source)
    )
    saved_choice = json.loads(choice_path.read_text()) if choice_path.exists() else {}
    backend = preferred
    if saved_choice.get(constants.KEY_IDENTITY) == identity and saved_choice.get(
        constants.KEY_SETTINGS
    ) == asdict(settings):
        backend = saved_choice[constants.KEY_BACKEND]
    runtimes = {}

    def runtime_for(selected):
        if selected not in runtimes:
            runtimes[selected] = (
                install_source_runtime(source, selected)
                if source is not None
                else install_runtime(settings, selected, package_source)
            )
        return runtimes[selected]

    python = runtime_for(backend)
    token_for(settings.root, create=True)
    path = unit_path()
    command = " ".join(
        systemd_quote(value)
        for value in (
            python,
            constants.SHORT_OPTION_M,
            constants.PACKAGE_NAME,
            constants.COMMAND_SERVE,
            constants.OPTION_STORAGE,
            settings.root,
        )
    )
    # WorkingDirectory takes a literal path; a trailing slash preserves trailing whitespace.
    working_directory = (
        constants.WORKING_DIRECTORY_TEMPLATE.format(source=str(source).replace("%", "%%"))
        if source is not None
        else ""
    )
    unit = constants.SERVICE_UNIT_TEMPLATE.format(
        command=command,
        environment=systemd_quote(
            constants.XDG_CONFIG_ASSIGNMENT_PREFIX + str(config_path().parent.parent),
            expand_dollars=False,
        ),
        working_directory=working_directory,
    )

    result = {
        constants.KEY_RUNTIME: str(python.parent.parent),
        constants.KEY_BACKEND: backend,
        constants.KEY_SERVICE: str(path),
        constants.KEY_URL: settings.url + constants.MCP_ENDPOINT,
        constants.KEY_MODE: constants.KEY_SOURCE
        if source is not None
        else constants.INSTALL_MODE_PACKAGE,
        constants.KEY_SOURCE: str(source) if source is not None else None,
        constants.KEY_AGENT_HARNESS: list(agent_harness),
        constants.KEY_HARNESS_CONFIGS: {
            target[constants.KEY_NAME]: target[constants.KEY_PRIMARY] for target in selected
        },
        constants.KEY_INSTALLATION_ORIGIN: constants.KEY_MARKETPLACE
        if marketplace
        else constants.INSTALL_ORIGIN_CLI,
    }
    if source is None and path.exists() and path.read_text() == unit and config_path().exists():
        saved = json.loads(config_path().read_text())
        if saved == asdict(settings):
            try:
                probe_service(settings)
            except (OSError, RuntimeError, TimeoutError):
                pass
            else:
                remove_guard(path)
                register_clients(settings, agent_harness, marketplace=marketplace)
                record_installation(result, selected, entries, python)
                return result
    # Validate actual model inference inside the selected environment before replacing a running service.
    candidate = settings.root / constants.PATH_RUNTIME_CANDIDATE_JSON
    original_python = python
    for candidate_backend in candidates:
        python = runtime_for(candidate_backend)
        validation = (
            replace(settings, backend=candidate_backend, cpu_fallback=False)
            if settings.backend == constants.BACKEND_AUTO
            else settings
        )
        atomic_json(candidate, asdict(validation))
        click.echo(f"Validating model inference in the {candidate_backend} runtime...", err=True)
        try:
            run(
                [
                    python,
                    constants.SHORT_OPTION_M,
                    constants.PACKAGE_NAME,
                    constants.COMMAND_DOCTOR,
                    constants.OPTION_SETTINGS_FILE,
                    candidate,
                    constants.OPTION_INFERENCE,
                ],
                **(
                    {constants.KEY_CWD: source, constants.KEY_ENV: installer_environment()}
                    if source is not None
                    else {}
                ),
            )
        except subprocess.CalledProcessError:
            if candidate_backend == candidates[-1]:
                raise
            continue
        backend = candidate_backend
        break
    unit = unit.replace(systemd_quote(original_python), systemd_quote(python))
    result.update(runtime=str(python.parent.parent), backend=backend)
    if path.exists():
        click.echo(f"Stopping {SERVICE} before replacing its configuration...", err=True)
        run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_STOP, SERVICE])
    settings.save()
    atomic_text(path, unit)
    run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_DAEMON_RELOAD])
    run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_ENABLE, SERVICE])
    click.echo(f"Starting {SERVICE} with the updated configuration...", err=True)
    run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_START, SERVICE])
    wait_for_service(settings, startup_timeout)
    atomic_json(
        choice_path,
        {
            constants.KEY_IDENTITY: identity,
            constants.KEY_SETTINGS: asdict(settings),
            constants.KEY_BACKEND: backend,
        },
    )
    remove_guard(path)
    if agent_harness:
        click.echo("Registering MCP connections for " + ", ".join(agent_harness) + "...", err=True)
    register_clients(settings, agent_harness, marketplace=marketplace)
    record_installation(result, selected, entries, python)
    return result


def service_action(action):
    if action == constants.COMMAND_UNINSTALL:
        from .lifecycle import uninstall

        return uninstall()
    else:
        run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, action, SERVICE])
