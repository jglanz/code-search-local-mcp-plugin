"""Persistent backend environments and user-scoped service/client registration."""

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

from . import __version__
from .config import config_path
from .service import token_for
from .storage import ServiceLock, atomic_json, atomic_text

SERVICE = "code-search-local.service"


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def uv_executable():
    from uv import find_uv_bin

    return find_uv_bin()


def select_runtime(backend):
    if backend != "auto":
        return "cpu" if backend == "mps" else backend
    if platform.system() == "Darwin":
        return "cpu"
    if shutil.which("nvidia-smi"):
        result = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
        if result.returncode == 0 and "GPU" in result.stdout:
            return "cuda"
    if any(
        path.read_text().strip() == "0x1002"
        for path in Path("/sys/class/drm").glob("card*/device/vendor")
    ):
        return "rocm"
    return "cpu"


def unit_path():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "systemd" / "user" / SERVICE


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
        if key not in ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV", "PYTHONPATH")
    }
    env["PYTHONNOUSERSITE"] = "1"
    return env


def source_checkout(path):
    root = Path(path).expanduser().resolve()
    if "\n" in str(root) or "\r" in str(root):
        raise ValueError("Source checkout paths cannot contain line breaks")
    try:
        metadata = tomllib.loads((root / "pyproject.toml").read_text())
        valid = (
            metadata.get("project", {}).get("name") == "code-search-local"
            and (root / "src/code_search_local/__init__.py").is_file()
            and (root / "uv.lock").is_file()
        )
    except (OSError, ValueError):
        valid = False
    if not valid:
        raise ValueError(f"Not a Code Search Local source checkout: {root}")
    return root


def install_source_runtime(source, backend):
    """Sync the live checkout using the backend environment declared in pyproject."""
    metadata = tomllib.loads((source / "pyproject.toml").read_text())
    try:
        environments = metadata["tool"]["hatch"]["envs"]
        relative = environments[backend].get("path", environments["default"]["path"])
    except KeyError:
        raise ValueError(f"Checkout lacks the Hatch {backend} environment configuration") from None
    venv = source / relative
    env = installer_environment()
    env["UV_PROJECT_ENVIRONMENT"] = str(venv)
    run(
        [
            uv_executable(),
            "sync",
            "--project",
            source,
            "--locked",
            "--extra",
            "server",
            "--extra",
            backend,
            "--python",
            "3.12",
            "--reinstall-package",
            "code-search-local",
        ],
        env=env,
    )
    return venv / "bin/python"


def runtime_identity(package_source=None):
    resources = distribution("code-search-local").locate_file("code_search_local/runtime")
    identity = hashlib.sha256((resources / "uv.lock").read_bytes())
    if package_source:
        identity.update(Path(package_source).read_bytes())
    return f"{__version__}-{identity.hexdigest()[:12]}"


def install_runtime(settings, backend, package_source=None):
    # Hatch installs forced-included resources in site-packages, including for editable installs.
    resources = distribution("code-search-local").locate_file("code_search_local/runtime")
    identity = runtime_identity(package_source)
    root = settings.root / "runtimes" / f"{__version__}-{backend}-{identity.split('-')[-1]}"
    python = root / ".venv" / "bin" / "python"
    if (root / "installed.json").exists() and python.exists():
        return python
    root.mkdir(parents=True, exist_ok=True)
    for name in ("pyproject.toml", "uv.lock"):
        (root / name).write_bytes((resources / name).read_bytes())
    (root / "README.md").write_text("Managed code-search-local runtime.\n")
    uv = uv_executable()
    env = installer_environment()
    run(
        [
            uv,
            "sync",
            "--project",
            root,
            "--locked",
            "--no-dev",
            "--no-install-project",
            "--extra",
            "server",
            "--extra",
            backend,
            "--python",
            "3.12",
        ],
        env=env,
    )
    source = (
        str(Path(package_source).resolve())
        if package_source
        else f"code-search-local=={__version__}"
    )
    run([uv, "pip", "install", "--python", python, "--no-deps", source], env=env)
    atomic_json(root / "installed.json", {"version": __version__, "backend": backend})
    return python


def register_clients(settings, selected, *, marketplace=False):
    from .harnesses import register, selection, targets

    if isinstance(selected, str):
        selected = ("claude", "codex") if selected == "both" else (selected,)
    register(settings, targets(selection(selected)), marketplace=marketplace)


def setup(
    settings, *, agent_harness=(), client=None, package_source=None, source=None, marketplace=False
):
    from .harnesses import plugins, read_document, selection, targets
    from .lifecycle import marketplace_entries

    if client is not None:
        if agent_harness:
            raise ValueError("--client cannot be combined with --agent-harness")
        agent_harness = ("claude", "codex") if client == "both" else (client,)
    agent_harness = selection(agent_harness)
    selected = targets(agent_harness)
    for target in selected:
        for path in target["configs"]:
            read_document(path)
        plugins(target)
    entries = marketplace_entries(selected) if marketplace else []
    if source is not None:
        if package_source is not None:
            raise ValueError("--source cannot be used with --package-source")
        source = source_checkout(source)
    lock = ServiceLock(config_path().parent, "install.lock")
    try:
        return _setup(
            settings,
            agent_harness=agent_harness,
            selected=selected,
            entries=entries,
            package_source=package_source,
            source=source,
            marketplace=marketplace,
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
):
    from .lifecycle import record_installation, remove_guard

    if platform.system() != "Linux":
        raise RuntimeError(
            "User systemd setup currently requires Linux; use serve on other platforms"
        )
    preferred = select_runtime(settings.backend)
    candidates = [preferred]
    if settings.backend == "auto":
        if preferred == "cuda" and any(
            path.read_text().strip() == "0x1002"
            for path in Path("/sys/class/drm").glob("card*/device/vendor")
        ):
            candidates.append("rocm")
        if preferred != "cpu" and settings.allow_fallback:
            candidates.append("cpu")
    choice_path = settings.root / "runtime-choice.json"
    identity = (
        "source:"
        + str(source)
        + ":"
        + hashlib.sha256(
            (source / "pyproject.toml").read_bytes() + (source / "uv.lock").read_bytes()
        ).hexdigest()
        if source is not None
        else runtime_identity(package_source)
    )
    saved_choice = json.loads(choice_path.read_text()) if choice_path.exists() else {}
    backend = preferred
    if saved_choice.get("identity") == identity and saved_choice.get("settings") == asdict(
        settings
    ):
        backend = saved_choice["backend"]
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
        for value in (python, "-m", "code_search_local", "serve", "--storage", settings.root)
    )
    unit = (
        "[Unit]\nDescription=Code Search Local shared model service\nAfter=network.target\n\n"
        "[Service]\nType=simple\n" + f"ExecStart={command}\n"
        f"Environment={systemd_quote('XDG_CONFIG_HOME=' + str(config_path().parent.parent), expand_dollars=False)}\n"
        + (
            # WorkingDirectory takes one literal path, not an ExecStart-style quoted argument.
            # A trailing slash preserves any trailing whitespace/backslash in the directory name.
            f"WorkingDirectory={str(source).replace('%', '%%')}/\n" if source is not None else ""
        )
        + "Environment=PYTHONNOUSERSITE=1\n"
        "Restart=on-failure\nRestartSec=3\nTimeoutStopSec=120\nUMask=0077\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    import asyncio

    from .client import Client

    result = {
        "runtime": str(python.parent.parent),
        "backend": backend,
        "service": str(path),
        "url": settings.url + "/mcp",
        "mode": "source" if source is not None else "package",
        "source": str(source) if source is not None else None,
        "agent_harness": list(agent_harness),
        "installation_origin": "marketplace" if marketplace else "cli",
    }
    if source is None and path.exists() and path.read_text() == unit and config_path().exists():
        saved = json.loads(config_path().read_text())
        if saved == asdict(settings):
            try:
                asyncio.run(Client(settings).request("GET", "/api/v1/health"))
            except (OSError, RuntimeError):
                pass
            else:
                remove_guard(path)
                register_clients(settings, agent_harness, marketplace=marketplace)
                record_installation(result, selected, entries, python)
                return result
    # Validate actual model inference inside the selected environment before replacing a running service.
    candidate = settings.root / "runtime-candidate.json"
    original_python = python
    for candidate_backend in candidates:
        python = runtime_for(candidate_backend)
        validation = (
            replace(settings, backend=candidate_backend, cpu_fallback=False)
            if settings.backend == "auto"
            else settings
        )
        atomic_json(candidate, asdict(validation))
        try:
            run(
                [
                    python,
                    "-m",
                    "code_search_local",
                    "doctor",
                    "--settings-file",
                    candidate,
                    "--inference",
                ],
                **({"cwd": source, "env": installer_environment()} if source is not None else {}),
            )
        except subprocess.CalledProcessError:
            if candidate_backend == candidates[-1]:
                raise
            continue
        backend = candidate_backend
        break
    unit = unit.replace(systemd_quote(original_python), systemd_quote(python))
    result.update(runtime=str(python.parent.parent), backend=backend)
    settings.save()
    atomic_text(path, unit)
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", SERVICE])
    run(["systemctl", "--user", "restart", SERVICE])
    deadline = time.monotonic() + 30
    while True:
        try:
            asyncio.run(Client(settings).request("GET", "/api/v1/health"))
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Service did not become healthy; inspect journalctl --user -u code-search-local"
                ) from None
            time.sleep(0.25)
    atomic_json(
        choice_path, {"identity": identity, "settings": asdict(settings), "backend": backend}
    )
    remove_guard(path)
    register_clients(settings, agent_harness, marketplace=marketplace)
    record_installation(result, selected, entries, python)
    return result


def service_action(action):
    if action == "uninstall":
        from .lifecycle import uninstall

        return uninstall()
    else:
        run(["systemctl", "--user", action, SERVICE])
